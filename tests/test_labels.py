import json
from datetime import date
from pathlib import Path

import pytest
from signal_engine import contracts as c, pipeline
from signal_engine.evals import labels
from signal_engine.store import Store, transition

T0 = "2026-10-30T09:00:00+00:00"


def ann(aid, target, action, actor="pm1", at=T0, event=None, **kw):
    return {"kind": "annotation", "audit_event_id": event or f"ev-{aid}", "annotation_id": aid, "target_type": "opportunity", "target_id": target,
            "actor": actor, "action": action, "reason_code": kw.get("reason"), "note": kw.get("note"), "undo_of": None, "created_at": at}


def write(path, *records):
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def opp(store, oid, status="new", **kw):
    store.insert("opportunity", c.Opportunity(opportunity_id=oid, title=oid, problem_statement="p", bucket="documents_evidence",
                                              first_seen_as_of=date(2026, 10, 1), **kw))
    if status != "new":
        transition(store, oid, "proposed", "brief", "system")
        if status != "proposed":
            transition(store, oid, status, "pm0", "person")


def label(lid, target="B1", target_type="brief", **kw):
    return {"kind": "label", "label_id": lid, "judge": "faithfulness", "target_type": target_type, "target_id": target, "verdict": "fail",
            "critique": "x", "origin": "live_reviewer", "blind": True, "split": "dev", "weight": 1.0, "actor": "pm1", "created_at": T0, **kw}


def test_import_loads_rows_counts_missing_targets_and_is_idempotent(tmp_store, tmp_path):
    opp(tmp_store, "O1")
    write(tmp_path / "pm1.jsonl", ann("a1", "O1", "accept"), ann("a2", "GONE", "park"), label("l1", target="NOBRIEF"))
    (tmp_path / "pm1.jsonl").write_text((tmp_path / "pm1.jsonl").read_text(encoding="utf-8") + "not json\n", encoding="utf-8")
    got = labels.import_path(tmp_store, tmp_path)
    assert (got["annotations"], got["labels"], got["missing_targets"], got["bad_lines"], got["files"]) == (2, 1, 2, 1, 1)
    assert {a["annotation_id"] for a in tmp_store.select("annotation")} == {"a1", "a2"}   # the missing target is kept
    assert tmp_store.select("label")[0]["target_id"] == "NOBRIEF"
    again = labels.import_path(tmp_store, tmp_path)
    assert (again["annotations"], again["labels"]) == (0, 0) and len(tmp_store.select("annotation")) == 2
    assert tmp_store.verify_audit_chain()


def test_undone_action_and_its_labels_are_not_imported(tmp_store, tmp_path):
    opp(tmp_store, "O1")
    write(tmp_path / "pm1.jsonl", ann("a1", "O1", "reject", reason="not_product_signal"), label("l1", target="O1"),
          {"kind": "undo", "undo_of": "ev-a1", "audit_event_id": "ev-u", "label_ids": ["l1"]})
    got = labels.import_path(tmp_store, tmp_path)
    assert got["undos"] == 1 and got["labels"] == 0
    assert labels.apply(tmp_store, "review") == {"applied": 0, "cancelled": 1, "missing": 0, "skipped": 0}
    assert tmp_store.select("opportunity")[0]["status"] == "new"


def test_review_actions_apply_with_original_actor_and_time(tmp_store, tmp_path):
    for o in ("O1", "O2", "O3", "O4"):
        opp(tmp_store, o, "proposed")
    write(tmp_path / "x.jsonl", ann("a1", "O1", "accept", actor="alice", at="2026-10-30T09:00:00+00:00"),
          ann("a2", "O2", "reject", actor="bob", at="2026-10-30T10:00:00+00:00", reason="low_value"),
          ann("a3", "O3", "park", actor="carol", at="2026-10-30T11:00:00+00:00", note="later"),
          ann("a4", "O4", "reassign", actor="dan", at="2026-10-30T12:00:00+00:00", note="to handling_payments"))
    labels.import_path(tmp_store, tmp_path)
    got = labels.apply(tmp_store, "review")
    assert got["applied"] == 4
    status = {o["opportunity_id"]: (o["status"], o["squad"]) for o in tmp_store.select("opportunity")}
    assert status["O1"][0] == "accepted" and status["O2"][0] == "rejected" and status["O3"][0] == "parked" and status["O4"][1] == "handling_payments"
    ev = {e["target_id"]: e for e in tmp_store.select("audit_event") if e["action"] in ("opportunity.transition", "opportunity.reassign") and e["actor"] != "brief"}
    assert (ev["O1"]["actor"], ev["O1"]["actor_kind"], ev["O1"]["at"]) == ("alice", "person", "2026-10-30T09:00:00+00:00")
    assert ev["O4"]["at"] == "2026-10-30T12:00:00+00:00"
    assert labels.apply(tmp_store, "review")["applied"] == 0   # replaying the same phase changes nothing
    assert tmp_store.verify_audit_chain()


def test_merge_after_cluster_and_tags_after_tag(tmp_store, tmp_path):
    opp(tmp_store, "O1")
    opp(tmp_store, "O2")
    opp(tmp_store, "O3", tag="shipped", tag_ref="shortcut:1", tag_state="proposed")
    opp(tmp_store, "O4", tag="on_roadmap", tag_ref="notion:x", tag_state="proposed")
    write(tmp_path / "x.jsonl", ann("m1", "O1", "merge", note="merged into O2"), ann("t1", "O3", "confirm_tag"), ann("t2", "O4", "remove_tag"),
          ann("m2", "O2", "accept"))
    labels.import_path(tmp_store, tmp_path)
    assert labels.apply(tmp_store, "after_cluster")["applied"] == 1
    o1 = tmp_store.select("opportunity", {"opportunity_id": "O1"})[0]
    assert (o1["status"], o1["merged_into"]) == ("merged", "O2")
    assert labels.apply(tmp_store, "after_tag")["applied"] == 2
    tags = {o["opportunity_id"]: o["tag_state"] for o in tmp_store.select("opportunity")}
    assert tags["O3"] == "confirmed" and tags["O4"] == "removed"
    assert tmp_store.select("opportunity", {"opportunity_id": "O2"})[0]["status"] == "new"   # accept waits for the review phase
    assert labels.apply(tmp_store, "other") is None


def test_hooks_and_review_stage_are_wired_to_this_module(tmp_store, tmp_path, monkeypatch):
    assert pipeline.resolve(pipeline.STAGES["review"]) is labels.apply
    assert [pipeline.resolve(s) for s in pipeline.HOOKS["run_start"] + pipeline.HOOKS["after_cluster"] + pipeline.HOOKS["after_tag"]] == [
        labels.import_human, labels.apply, labels.apply]
    opp(tmp_store, "O1", "proposed")
    write(tmp_path / "x.jsonl", ann("a1", "O1", "accept"))
    monkeypatch.setattr(labels, "HUMAN_DIR", tmp_path)
    ctx = pipeline.RunContext(tmp_store, None, "r1", date(2026, 11, 3), Path("."), 42, "all", "replay", Path("."), {}, None)
    ctx.stage = "run_start"
    labels.import_human(ctx)
    ctx.stage = "review"
    labels.apply(ctx)
    assert tmp_store.select("opportunity")[0]["status"] == "accepted"


def test_export_per_judge_and_phoenix(tmp_store, tmp_path, capsys, monkeypatch):
    seed = tmp_path / "seed"
    seed.mkdir()
    write(seed / "signal.jsonl", {"judge": "signal", "verdict": "pass", "evidence": {"title": "t"}, "origin": "synthetic_seed"})
    tmp_store.insert("label", c.Label(label_id="l1", judge="signal", target_type="brief", target_id="B1", verdict="pass", origin="live_reviewer",
                                      blind=True, split="dev", actor="pm", created_at=T0))
    out = tmp_path / "out"
    paths = dict((p.name, n) for p, n in labels.export(tmp_store, None, out, seed))
    assert paths == {"faithfulness.jsonl": 0, "signal.jsonl": 2, "duplicate.jsonl": 0}
    rows = [json.loads(ln) for ln in (out / "signal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["dataset"] for r in rows} == {"seed", "store"}
    assert labels.main(["export", "--phoenix"]) == 0
    assert "Phoenix datasets: designed, not built in v1" in capsys.readouterr().out
