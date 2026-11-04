import argparse
import json
import re

import pytest
import yaml
from conftest import FakeGateway
from signal_engine.evals import ground_truth as gt, seeds
from signal_engine.store import Store
from test_evals_gt import build, truth_dict

EXTRA = " Every motor insurer is affected."


def brief_writer(body):
    ids = re.findall(r'"id": "([0-9a-f]{16})"', body["messages"][0]["content"])
    cites = " ".join(f"[i:{i}]" for i in ids)
    return {"body_md": f"# Brief\n## Problem\nHandlers report the same problem {cites}.\n## Who is affected\n- Several accounts report it {cites}\n"
                       f"## Evidence\n- Handlers describe the problem [i:{ids[0]}]\n"}


def defect_writer(body):
    brief = json.loads(body["messages"][1]["content"])["brief"]
    return {"body_md": brief + EXTRA, "changed_span": EXTRA}


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "ground_truth.yaml"
    p.write_text(yaml.safe_dump(truth_dict()), encoding="utf-8")
    monkeypatch.setattr(seeds, "GT_PATH", p)
    store = Store(tmp_path / "run.sqlite").init()
    build(store)
    store.close()
    made = []

    def gateway(s, profile, cache, run_id, max_usd):
        made.append(profile)
        return FakeGateway(s, {"brief": brief_writer, "generate": defect_writer}, tmp=tmp_path / "cache", run_id=run_id)
    monkeypatch.setattr(seeds, "Gateway", gateway)
    return argparse.Namespace(n=12, profile="demo", db=str(tmp_path / "run.sqlite"), cache_dir=str(tmp_path / "cache"), max_usd=1.75,
                              out=str(tmp_path / "labels" / "seed"), scratch=str(tmp_path / "scr"))


def load(a, judge):
    return [json.loads(ln) for ln in (open(f"{a.out}/{judge}.jsonl", encoding="utf-8").read().splitlines())]


def test_theme_splits_are_disjoint_and_deterministic():
    s = seeds.theme_splits(["a", "b", "c", "d", "e", "f"])
    assert s == seeds.theme_splits(["f", "e", "d", "c", "b", "a"])
    assert sorted(s.values()).count("dev") == 2 and sorted(s.values()).count("held_out") == 4   # 30% of 6, rounded
    assert seeds.theme_splits(["only"]) == {"only": "held_out"}


def test_seed_sets_have_half_pass_half_fail_per_judge(env, capsys):
    assert seeds.main(env) == 0
    for judge in ("signal", "duplicate", "faithfulness"):
        rows = load(env, judge)
        assert len(rows) == 12 and sum(r["verdict"] == "pass" for r in rows) == 6, judge
        assert {r["origin"] for r in rows} == {"synthetic_seed"} and {r["blind"] for r in rows} == {False}
        assert {r["split"] for r in rows} <= {"dev", "held_out"} and all(r["evidence"] for r in rows)
        assert len({r["label_id"] for r in rows}) == 12
    out = capsys.readouterr().out
    assert "signal: 12 items" in out and "faithfulness: 12 items" in out


def test_signal_fails_come_from_noise_and_passes_from_signal_themes(env):
    seeds.main(env)
    rows = load(env, "signal")
    fail_text = " ".join(q["quote"] for r in rows if r["verdict"] == "fail" for q in r["evidence"]["quotes"])
    pass_text = " ".join(q["quote"] for r in rows if r["verdict"] == "pass" for q in r["evidence"]["quotes"])
    assert "words about the problem" in fail_text and "quote words one two three" in pass_text


def test_duplicate_fails_pair_shipped_theme_and_passes_are_real_themes(env):
    seeds.main(env)
    rows = load(env, "duplicate")
    assert {r["evidence"]["problem_statement"] for r in rows if r["verdict"] == "fail"} <= {"problem s1", "problem s2"}
    assert not {r["evidence"]["problem_statement"] for r in rows if r["verdict"] == "pass"} & {"problem s1", "problem s2"}


def test_faithfulness_fails_apply_one_recorded_defect_and_passes_are_unchanged(env):
    seeds.main(env)
    rows = load(env, "faithfulness")
    passes, fails = [r for r in rows if r["verdict"] == "pass"], [r for r in rows if r["verdict"] == "fail"]
    assert {r["meta"]["defect"] for r in passes} == {None}
    assert [r["meta"]["defect"] for r in fails] == list(seeds.DEFECTS)   # six kinds, one each
    for p, f in zip(passes, fails):
        assert f["meta"]["changed_span"] == EXTRA and f["evidence"]["brief"] == p["evidence"]["brief"] + EXTRA
        assert f["split"] == p["split"] and f["evidence"]["fact_sheet"] == p["evidence"]["fact_sheet"]
        assert "[i:" in p["evidence"]["brief"] and p["evidence"]["cited_insights"]


def test_seed_needs_ground_truth_and_a_store(env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(seeds, "GT_PATH", tmp_path / "missing.yaml")
    assert seeds.main(env) == 2 and "need ground truth" in capsys.readouterr().out
