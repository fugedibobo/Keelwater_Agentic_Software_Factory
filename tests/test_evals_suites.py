"""Stability and judges suites end to end on small stores; the replay itself is stubbed because the pipeline has its own tests."""

import json
from pathlib import Path

import pytest
import yaml
from conftest import FakeGateway
from signal_engine import contracts as c
from signal_engine.evals import cli, common, ground_truth as gt, judges_suite as js, labels, stability
from signal_engine.store import Store
from test_evals_gt import GROUPS, build, truth_dict


def args(tmp_path, *extra):
    return cli.parser().parse_args(["--report-dir", str(tmp_path / "rep"), "--scratch", str(tmp_path / "scr"), "--seeds", str(tmp_path / "seed"), *extra])


# ---- stability ----------------------------------------------------------------------------------------------------

def snap(opps, shares):
    return {"opps": {o: (t, frozenset(ids)) for o, (t, ids) in opps.items()}, "shares": shares}


def test_stability_conditions_on_snapshots():
    before = snap({"O1": ("rt-a", {"i1", "i2"})}, {})
    good = snap({"O1": ("rt-a", {"i1", "i2", "i3"})}, {"rt-a": {"O1": 1.0}})
    assert stability.check(before, good)[1] == {"ids_kept": True, "no_fork": True, "memberships_grow": True}
    lost = snap({"O9": ("rt-a", {"i1", "i2", "i3"})}, {"rt-a": {"O9": 1.0}})
    assert stability.check(before, lost)[1]["ids_kept"] is False
    forked = snap({"O1": ("rt-a", {"i1", "i2"}), "O9": ("rt-a", {"i3"})}, {"rt-a": {"O1": 0.5, "O9": 0.5}})
    assert stability.check(before, forked)[1]["no_fork"] is False
    shrunk = snap({"O1": ("rt-a", {"i1"})}, {"rt-a": {"O1": 1.0}})
    assert stability.check(before, shrunk)[1]["memberships_grow"] is False
    relabelled = snap({"O1": ("rt-b", {"i1", "i2"})}, {"rt-b": {"O1": 1.0}})
    assert stability.check(before, relabelled)[1]["ids_kept"] is False


def fake_replay(monkeypatch, september, october, extra=()):
    """Replace the pipeline replay: the sep call builds a store from `september`, the oct call runs october(store, {mention key: insight id})."""
    calls = []

    def replay(a, seed=42, batch="all", as_of=None, db=None):
        calls.append((batch, as_of))
        store = Store(db).init()
        if batch == "sep":
            build(store, september, extra=extra)
        else:
            by_key = {s["text"].split()[0]: i["insight_id"] for s in store.select("snippet") for i in store.select("insight") if i["snippet_id"] == s["snippet_id"]}
            october(store, by_key)
        store.close()
        return 0, "", {"run_id": f"run-{batch}", "manifest": {"cache_keys": [f"stage/{batch}"]}}
    monkeypatch.setattr(common, "replay", replay)
    return calls


@pytest.fixture
def truth_file(tmp_path, monkeypatch):
    p = tmp_path / "ground_truth.yaml"
    p.write_text(yaml.safe_dump(truth_dict()), encoding="utf-8")
    monkeypatch.setattr(gt, "GT_PATH", p)


def test_stability_suite_passes_when_ids_hold_and_memberships_grow(tmp_path, monkeypatch, truth_file):
    def october(store, ids):  # a3 joins OA
        store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id="OA", insight_id=ids["a3"], similarity=0.9))
    calls = fake_replay(monkeypatch, {"OA": ["a1", "a2"], "OB1": ["b1", "b2"]}, october, extra=("a3",))
    passed, out, path = stability.run_suite(args(tmp_path))
    assert passed, out
    assert calls == [("sep", "01/10/2026"), ("oct", "03/11/2026")]
    rep = json.loads(path.read_text(encoding="utf-8"))
    assert rep["suite"] == "stability" and rep["gates"] == {"ids_kept": True, "memberships_grow": True, "no_fork": True} and rep["cache_keys"] == ["stage/oct"]


def test_stability_suite_fails_when_a_theme_forks(tmp_path, monkeypatch, truth_file):
    fake_replay(monkeypatch, GROUPS, lambda store, ids: None)   # rt-b is split 2 and 2 across OB1 and OB2
    passed, out, _ = stability.run_suite(args(tmp_path))
    assert not passed and any("no forks      FAIL" in ln for ln in out)


def test_suites_report_missing_ground_truth(tmp_path, monkeypatch):
    monkeypatch.setattr(gt, "GT_PATH", tmp_path / "nope.yaml")
    passed, out, path = stability.run_suite(args(tmp_path))
    assert not passed and "ground truth missing" in out[0] and path is None


# ---- judges -------------------------------------------------------------------------------------------------------

def canned(body):
    return {"critique": "checked", "verdict": "pass" if "GOOD" in body["messages"][0]["content"] else "fail"}


@pytest.fixture
def judge_env(tmp_path, monkeypatch):
    store = Store(tmp_path / "k.sqlite").init()
    monkeypatch.setattr(js, "Gateway", lambda s, profile, cache, run_id, max_usd: FakeGateway(s, {"judge": canned}, tmp=tmp_path / "cache", run_id=run_id))
    monkeypatch.setattr(labels, "HUMAN_DIR", tmp_path / "human")
    seeds = tmp_path / "seed"
    seeds.mkdir()
    rows = []
    for n, (verdict, split, word) in enumerate([("pass", "dev", "GOOD"), ("pass", "dev", "GOOD"), ("pass", "held_out", "GOOD"), ("fail", "dev", "BAD"),
                                                ("fail", "held_out", "BAD"), ("fail", "held_out", "GOOD")]):  # the last is a judge miss
        rows.append({"kind": "label", "judge": "signal", "target_type": "seed", "target_id": f"seed-signal-{n}", "verdict": verdict, "origin": "synthetic_seed",
                     "blind": False, "split": split, "weight": 1.0, "created_at": "2026-11-03T00:00:00+00:00", "evidence": {"quote": word}})
    (seeds / "signal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    gw = FakeGateway(store, {}, tmp=tmp_path / "cache", run_id="r1")
    return store, {j: js.version_id(gw, j) for j in common.JUDGES}


def real_pm_labels(store, jv, n_ok_pass, n_ok_fail, n=50):
    """n human passes on brief B1 (judge passes it) and n human fails on B2 (judge fails it); the judge errs on the last ones."""
    for b, verdict in (("B1", "pass"), ("B2", "fail")):
        store.insert("judgement", c.Judgement(judgement_id=f"j-{b}", run_id="r1", judge_version_id=jv["faithfulness"], judge="faithfulness",
                                              target_type="brief", target_id=b, verdict=verdict, critique="c"))
    for i in range(n):
        for b, human, ok in (("B1", "pass", i < n_ok_pass), ("B2", "fail", i < n_ok_fail)):
            # an erring judge is modelled by a label on the other brief: its verdict there is the opposite
            target = b if ok else ("B2" if b == "B1" else "B1")
            store.insert("label", c.Label(label_id=f"{b}-{i}", judge="faithfulness", target_type="brief", target_id=target, verdict=human, origin="real_pm",
                                          blind=True, split="held_out", actor=f"pm{i}", created_at=f"2026-11-02T10:{i:02d}:00"))


def test_judges_suite_seed_rows_and_never_trusted_without_real_pm(tmp_path, judge_env):
    store, jv = judge_env
    store.close()
    passed, out, path = js.run_suite(args(tmp_path, "--db", str(tmp_path / "k.sqlite"), "--qualify"))
    assert passed, out
    text = "\n".join(out)
    assert "signal" in text and "synthetic_seed" in text and "(never certifies)" in text
    rep = json.loads(path.read_text(encoding="utf-8"))
    row = next(r for r in rep["detail"]["rows"] if r["judge"] == "signal" and r["origin"] == "synthetic_seed")
    assert row["dev"]["labels"] == 3 and row["dev"]["tpr"] == 1.0 and row["dev"]["tnr"] == 1.0   # dev: 2 pass, 1 fail, all judged right
    assert row["held_out"]["tpr"] == 1.0 and row["held_out"]["tnr"] == 0.5                       # held_out: one fail missed by the judge
    s = Store(tmp_path / "k.sqlite")
    assert {v["state"] for v in s.select("judge_version")} == {"calibrating"}   # qualified, but seeds never grant trust
    assert any(e["action"] == "judge.state" for e in s.select("audit_event")) is True
    assert any("calibrating: 0 of 50 per class" in ln for ln in out if "real_pm" in ln)


def test_judges_qualify_grants_trust_only_to_blind_real_pm_labels_at_44_of_50(tmp_path, judge_env):
    store, jv = judge_env
    real_pm_labels(store, jv, 44, 44)
    store.close()
    passed, out, path = js.run_suite(args(tmp_path, "--db", str(tmp_path / "k.sqlite"), "--qualify"))
    s = Store(tmp_path / "k.sqlite")
    v = s.select("judge_version", {"judge_version_id": jv["faithfulness"]})[0]
    assert v["state"] == "trusted" and v["n_pass"] == 50 and v["n_fail"] == 50 and v["tpr_lower"] >= 0.75 and v["tnr_lower"] >= 0.75
    assert any(e["action"] == "judge.state" and e["target_id"] == jv["faithfulness"] and e["details_json"]["to"] == "trusted" for e in s.select("audit_event"))
    assert passed and any("state change: faithfulness uncalibrated -> trusted" in ln for ln in out)


def test_judges_qualify_43_of_50_stays_calibrating(tmp_path, judge_env):
    store, jv = judge_env
    real_pm_labels(store, jv, 43, 50)
    store.close()
    js.run_suite(args(tmp_path, "--db", str(tmp_path / "k.sqlite"), "--qualify"))
    v = Store(tmp_path / "k.sqlite").select("judge_version", {"judge_version_id": jv["faithfulness"]})[0]
    assert v["state"] == "calibrating" and v["tpr_lower"] < 0.75


def test_judges_without_a_judge_verdict_fail_the_suite(tmp_path, judge_env, monkeypatch):
    store, jv = judge_env
    store.close()
    monkeypatch.setattr(js, "Gateway", lambda s, profile, cache, run_id, max_usd: FakeGateway(s, {"judge": lambda b: (_ for _ in ()).throw(js.GatewayError("miss"))},
                                                                                              tmp=tmp_path / "cache2", run_id=run_id))
    passed, out, _ = js.run_suite(args(tmp_path, "--db", str(tmp_path / "k.sqlite")))
    assert not passed and any("6 labels or seed items had no judge verdict" in ln for ln in out)


def test_eval_cli_exit_code_and_missing_store(tmp_path, capsys):
    assert cli.main(["--suite", "judges", "--qualify", "--db", str(tmp_path / "none.sqlite"), "--report-dir", str(tmp_path)]) == 1
    assert "no store at" in capsys.readouterr().out
