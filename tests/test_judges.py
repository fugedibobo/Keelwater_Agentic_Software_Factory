import copy
from types import SimpleNamespace

import pytest

from signal_engine import config
from signal_engine.contracts import Brief, Judgement
from signal_engine.evals.common import judged_verdicts
from signal_engine.evals.ground_truth import brief_metrics
from signal_engine.judges import family, run, tag_disagreements
from signal_engine.prompts import load_prompt
from test_brief import good_body, make_ctx, seed


def canned(body):
    prompt = body["messages"][0]["content"]
    fail = "(duplicate)" in prompt and "Tagged problem" in prompt
    return {"critique": "Checked the item; " + ("it is already covered." if fail else "it holds."), "verdict": "fail" if fail else "pass"}


def setup(store):
    ids = seed(store, [("O4", 3.0, "shipped")])
    store.db.execute("UPDATE opportunity SET problem_statement='Tagged problem' WHERE opportunity_id='O4'")
    store.db.commit()
    store.insert("brief", Brief(brief_id="B1", opportunity_id="O1", run_id="r1", body_md=good_body(ids), citations_json=list(ids.values()),
                                check_status="passed", prompt_version="writer@1+x", model="m"))


def test_three_judges_write_verdicts_and_uncalibrated_versions(tmp_store, fake_gateway):
    setup(tmp_store)
    gw = fake_gateway({"judge": canned})
    run(make_ctx(gw, tmp_store))
    got = {(j["judge"], j["target_type"], j["target_id"]): j for j in tmp_store.select("judgement")}
    assert set(got) == {("signal", "opportunity", "O1"), ("faithfulness", "brief", "B1"), ("duplicate", "brief", "B1"),
                        ("duplicate", "opportunity", "O4")}
    assert all(j["critique"] and j["call_id"] for j in got.values())
    versions = tmp_store.select("judge_version")
    assert {v["state"] for v in versions} == {"uncalibrated"} and len(versions) == 3
    assert all(v["judge_version_id"] == f"{v['prompt_version']}+z-ai/glm-5.3" for v in versions)
    body = gw.calls[0][2]
    assert body["temperature"] == 0 and list(body["response_format"]["json_schema"]["schema"]["properties"]) == ["critique", "verdict"]


def test_duplicate_fail_on_tagged_opportunity_is_a_disagreement_and_keeps_the_tag(tmp_store, fake_gateway):
    setup(tmp_store)
    run(make_ctx(fake_gateway({"judge": canned}), tmp_store))
    (d,) = tag_disagreements(tmp_store, "r1")
    assert d["opportunity_id"] == "O4" and d["tag"] == "shipped" and "already covered" in d["critique"]
    assert tmp_store.select("opportunity", {"opportunity_id": "O4"})[0]["tag"] == "shipped"
    assert tag_disagreements(tmp_store, "other") == []


def test_judge_primary_family_differs_from_writer_and_extractor():
    # the fallbacks share DeepSeek on purpose; the not_independent rule covers that case
    stages = config.load("models")["profiles"]["demo"]["stages"]
    assert family(stages["judge"]["model"]) not in {family(stages[s]["model"]) for s in ("brief", "handoff", "extract")}
    assert family(stages["judge"]["model"]) == "z-ai" and family(stages["brief"]["fallback"]) == "deepseek"


def test_family_is_the_vendor_prefix_of_openrouter_and_bedrock_ids():
    assert [family(m) for m in ("deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3", "deepseek.v3.2", "qwen/qwen3.8-max-0902")] == ["deepseek", "z-ai", "deepseek", "qwen"]


def deepseek_judge():
    models = copy.deepcopy(config.load("models"))
    models["profiles"]["demo"]["stages"]["judge"]["model"] = "deepseek/deepseek-v4.1-flash"  # the judge fell back to DeepSeek
    return models


def test_brief_written_by_the_judges_family_is_not_graded_and_makes_no_judge_call(tmp_store, fake_gateway):
    setup(tmp_store)
    tmp_store.db.execute("UPDATE brief SET model='deepseek/deepseek-v4.1-flash' WHERE brief_id='B1'")
    tmp_store.db.commit()
    gw = fake_gateway({"judge": canned}, models=deepseek_judge())
    run(make_ctx(gw, tmp_store))
    got = {(j["judge"], j["target_type"], j["target_id"]): j for j in tmp_store.select("judgement")}
    for k in (("faithfulness", "brief", "B1"), ("duplicate", "brief", "B1")):
        assert got[k]["verdict"] == "not_independent" and got[k]["call_id"] is None
        assert "same model family (deepseek)" in got[k]["critique"]
    assert got[("signal", "opportunity", "O1")]["verdict"] == "pass"  # opportunity judges grade Qwen text and stay
    assert len(gw.calls) == 2  # signal O1 and duplicate O4 only; no model call for either brief judgement


def test_brief_written_by_qwen_is_graded_normally_by_glm(tmp_store, fake_gateway):
    setup(tmp_store)
    tmp_store.db.execute("UPDATE brief SET model='qwen/qwen3.8-max-0902' WHERE brief_id='B1'")
    tmp_store.db.commit()
    gw = fake_gateway({"judge": canned})
    run(make_ctx(gw, tmp_store))
    got = {(j["judge"], j["target_type"], j["target_id"]): j for j in tmp_store.select("judgement")}
    assert got[("faithfulness", "brief", "B1")]["verdict"] == "pass" and got[("faithfulness", "brief", "B1")]["call_id"]
    assert len(gw.calls) == 4 and "not_independent" not in {j["verdict"] for j in got.values()}


def test_not_independent_rows_are_left_out_of_pass_counts_and_agreement(tmp_store):
    for i, v in enumerate(("pass", "pass", "fail", "not_independent", "not_independent")):
        tmp_store.insert("judgement", Judgement(judgement_id=f"j{i}", run_id="r1", judge_version_id="faithfulness@1+m", judge="faithfulness",
                                                target_type="brief", target_id=f"B{i}", verdict=v, critique="c"))
    a = SimpleNamespace(store=tmp_store, run_id="r1", briefs={})
    assert brief_metrics(a)["faithfulness_pass_rate"] == pytest.approx(2 / 3)
    assert judged_verdicts(tmp_store) == {("B0", "faithfulness"): "pass", ("B1", "faithfulness"): "pass", ("B2", "faithfulness"): "fail"}
    assert len(tmp_store.select("judgement")) == 5  # still stored and shown


@pytest.mark.parametrize("name", ["signal", "faithfulness", "duplicate"])
def test_judge_prompts_share_the_template(name):
    body, pv = load_prompt("judge", name)
    assert pv.startswith(f"{name}@1+") and f"({name})" in body and "few-shot" not in body.lower()
    assert [t for t in ("<role>", "<definition>", "<evidence>", "<task>", "<output>") if t not in body] == []
