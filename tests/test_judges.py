import pytest

from signal_engine import config
from signal_engine.contracts import Brief
from signal_engine.judges import run, tag_disagreements
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
    assert all(v["judge_version_id"] == f"{v['prompt_version']}+z-ai/glm-5" for v in versions)
    body = gw.calls[0][2]
    assert body["temperature"] == 0 and list(body["response_format"]["json_schema"]["schema"]["properties"]) == ["critique", "verdict"]


def test_duplicate_fail_on_tagged_opportunity_is_a_disagreement_and_keeps_the_tag(tmp_store, fake_gateway):
    setup(tmp_store)
    run(make_ctx(fake_gateway({"judge": canned}), tmp_store))
    (d,) = tag_disagreements(tmp_store, "r1")
    assert d["opportunity_id"] == "O4" and d["tag"] == "shipped" and "already covered" in d["critique"]
    assert tmp_store.select("opportunity", {"opportunity_id": "O4"})[0]["tag"] == "shipped"
    assert tag_disagreements(tmp_store, "other") == []


def test_judge_family_differs_from_writer_and_extractor():
    stages = config.load("models")["profiles"]["demo"]["stages"]

    def fam(s):
        return {m.split("/")[0] for m in (stages[s]["model"], stages[s].get("fallback")) if m}

    assert fam("judge") and not fam("judge") & (fam("brief") | fam("extract"))


@pytest.mark.parametrize("name", ["signal", "faithfulness", "duplicate"])
def test_judge_prompts_share_the_template(name):
    body, pv = load_prompt("judge", name)
    assert pv.startswith(f"{name}@1+") and f"({name})" in body and "few-shot" not in body.lower()
    assert [t for t in ("<role>", "<definition>", "<evidence>", "<task>", "<output>") if t not in body] == []
