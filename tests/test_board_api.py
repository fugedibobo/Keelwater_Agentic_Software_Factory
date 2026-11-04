"""Board API: actions write one annotation and one audit_event each, undo, 409, 403, labels stay blind until saved."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import seed_store  # noqa: E402

from signal_engine.board import actions  # noqa: E402
from signal_engine.board.app import create_app  # noqa: E402

H = {"X-Actor": "priya.n"}


@pytest.fixture
def board(tmp_path):
    db = seed_store.seed_copy(tmp_path / "demo", tmp_path.parent)
    app = create_app(db, tmp_path / "labels", tmp_path / "demo" / "reports" / "eval")
    yield TestClient(app), app.state.store, tmp_path / "labels"
    app.state.store.close()


def counts(store):
    return {t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("annotation", "audit_event", "label")}


def status(store, oid):
    return store.select("opportunity", {"opportunity_id": oid})[0]


def test_every_write_adds_exactly_one_annotation_and_one_audit_event(board):
    c, s, _ = board
    steps = [
        ("o1/accept", {"confirmed": True}), ("o2/reject", {"reason_code": "low_value"}), ("o5/park", {"note": "later"}),
        ("o1/reassign", {"squad": "suppliers_comms"}), ("o3/edit", {"title": "New title", "problem_statement": "New text here."}),
        ("o5/confirm_tag", {}), ("o2/merge", {"target_id": "o1"}),
    ]
    for path, body in steps:
        before = counts(s)
        r = c.post(f"/api/opportunities/{path}", json=body, headers=H)
        if path == "o2/merge":  # o2 was already rejected above, so the status machine says 409 and nothing is written
            assert r.status_code == 409 and counts(s) == before
            continue
        assert r.status_code == 200, (path, r.text)
        after = counts(s)
        assert after["annotation"] == before["annotation"] + 1 and after["audit_event"] == before["audit_event"] + 1, path
    assert status(s, "o1")["status"] == "accepted" and status(s, "o1")["squad"] == "suppliers_comms"
    assert status(s, "o5")["status"] == "parked" and status(s, "o3")["title"] == "New title"
    assert s.verify_audit_chain()


def test_accept_needs_confirmation_and_a_legal_move(board):
    c, s, lab = board
    assert c.post("/api/opportunities/o1/accept", json={"confirmed": False}, headers=H).status_code == 422
    r = c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers=H)
    assert r.json()["opportunity"]["status"] == "accepted"
    again = c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers=H)
    assert again.status_code == 409
    assert c.post("/api/opportunities/nope/accept", json={"confirmed": True}, headers=H).status_code == 404
    lines = [json.loads(l) for l in (lab / "priya.n.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {l["kind"] for l in lines} == {"annotation", "label"} and sum(l["kind"] == "annotation" for l in lines) == 1
    labels = s.select("label")
    assert {(l["judge"], l["verdict"], l["blind"], l["origin"]) for l in labels} == {("signal", "pass", 0, "live_reviewer"), ("duplicate", "pass", 0, "live_reviewer")}


@pytest.mark.parametrize("actor", ["", "system", "  ", "SYSTEM"])
def test_actor_must_be_a_person(board, actor):
    c, s, _ = board
    before = counts(s)
    hdr = {"X-Actor": actor}
    for path, body in (("/api/opportunities/o1/accept", {"confirmed": True}), ("/api/opportunities/o1/park", {}), ("/api/undo", {"audit_event_id": "x"}),
                       ("/api/labels", {"target_type": "noise_audit", "target_id": "x", "judge": "signal", "verdict": "fail"})):
        assert c.post(path, json=body, headers=hdr).status_code == 403
    assert counts(s) == before and status(s, "o1")["status"] == "proposed"
    assert c.post("/api/opportunities/o1/accept", json={"confirmed": True}).status_code == 403  # header missing


def test_reject_rules_and_labels(board):
    c, s, _ = board
    assert c.post("/api/opportunities/o1/reject", json={"reason_code": "other"}, headers=H).status_code == 422
    assert c.post("/api/opportunities/o1/reject", json={"reason_code": "already_shipped"}, headers=H).status_code == 422  # reference required
    assert counts(s)["annotation"] == 1  # only the seeded one
    r = c.post("/api/opportunities/o1/reject", json={"reason_code": "not_product_signal"}, headers=H)
    assert r.status_code == 200
    assert [(l["judge"], l["verdict"]) for l in s.select("label")] == [("signal", "fail")]
    ann = s.select("annotation", {"action": "reject"})[0]
    assert ann["reason_code"] == "not_product_signal" and ann["actor"] == "priya.n"
    assert c.post("/api/opportunities/o2/reject", json={"reason_code": "evidence_wrong", "note": "quote 3 is not there"}, headers=H).status_code == 200
    assert ("faithfulness", "fail") in [(l["judge"], l["verdict"]) for l in s.select("label")]


def test_undo_restores_status_squad_text_tags_and_labels(board):
    c, s, _ = board
    eid = c.post("/api/opportunities/o1/reject", json={"reason_code": "not_product_signal"}, headers=H).json()["audit_event_id"]
    assert c.post("/api/undo", json={"audit_event_id": eid}, headers=H).status_code == 200
    assert status(s, "o1")["status"] == "proposed" and s.select("label") == []
    assert s.select("annotation", {"action": "undo"})[0]["undo_of"] == eid
    assert c.post("/api/undo", json={"audit_event_id": eid}, headers=H).status_code == 409  # already undone
    assert c.post("/api/opportunities/o1/reject", json={"reason_code": "low_value"}, headers=H).status_code == 200  # usable again

    e2 = c.post("/api/opportunities/o2/reassign", json={"squad": "platform_access"}, headers=H).json()["audit_event_id"]
    assert c.post("/api/undo", json={"audit_event_id": e2}, headers={"X-Actor": "someone.else"}).status_code == 403
    assert c.post("/api/undo", json={"audit_event_id": e2}, headers=H).status_code == 200 and status(s, "o2")["squad"] == "insight_reporting"

    e3 = c.post("/api/opportunities/o3/edit", json={"title": "X", "problem_statement": "Y", "original_wrong": True}, headers=H).json()["audit_event_id"]
    assert status(s, "o3")["title"] == "X" and ("faithfulness", "fail") in [(l["judge"], l["verdict"]) for l in s.select("label")]
    assert c.post("/api/undo", json={"audit_event_id": e3}, headers=H).status_code == 200
    assert status(s, "o3")["title"] == "Payment approval confusion" and not any(l["target_type"] == "brief" for l in s.select("label"))

    e4 = c.post("/api/opportunities/o5/remove_tag", json={"note": "different problem"}, headers=H).json()["audit_event_id"]
    assert status(s, "o5")["tag_state"] == "removed"
    assert c.post("/api/undo", json={"audit_event_id": e4}, headers=H).status_code == 200 and status(s, "o5")["tag_state"] == "proposed"
    assert c.post("/api/opportunities/o1/confirm_tag", json={}, headers=H).status_code == 409  # o1 has no tag


def test_undo_window_is_ten_seconds(board):
    c, s, lab = board
    eid = c.post("/api/opportunities/o1/park", json={}, headers=H).json()["audit_event_id"]
    late = datetime.now(timezone.utc) + timedelta(seconds=11)
    b = actions.Board(s, lab)
    with pytest.raises(actions.Conflict):
        actions.undo(b, eid, "priya.n", now=late)
    e2 = c.post("/api/opportunities/o2/edit", json={"title": "A", "problem_statement": "B"}, headers=H).json()["audit_event_id"]
    with pytest.raises(actions.Conflict):
        actions.undo(b, e2, "priya.n", now=late)
    assert status(s, "o1")["status"] == "parked" and status(s, "o2")["title"] == "A"


def test_merge_needs_target_and_undo_clears_it(board):
    c, s, _ = board
    assert c.post("/api/opportunities/o1/merge", json={}, headers=H).status_code == 422
    assert c.post("/api/opportunities/o1/merge", json={"target_id": "o1"}, headers=H).status_code == 422
    assert c.post("/api/opportunities/o1/merge", json={"target_id": "zzz"}, headers=H).status_code == 404
    r = c.post("/api/opportunities/o1/merge", json={"target_id": "o2"}, headers=H)
    assert status(s, "o1")["status"] == "merged" and status(s, "o1")["merged_into"] == "o2"
    c.post("/api/undo", json={"audit_event_id": r.json()["audit_event_id"]}, headers=H)
    assert status(s, "o1")["status"] == "proposed" and status(s, "o1")["merged_into"] is None


def test_reassign_needs_a_known_squad_and_split_is_not_built(board):
    c, s, _ = board
    assert c.post("/api/opportunities/o1/reassign", json={"squad": "made_up"}, headers=H).status_code == 422
    assert c.post("/api/opportunities/o1/reassign", json={}, headers=H).status_code == 422
    assert c.post("/api/opportunities/o1/split", json={"insight_ids": ["a"]}, headers=H).status_code == 501


def test_outtake_accept_reject_and_undo(board):
    c, s, _ = board
    r = c.post("/api/outtakes/out0/accept", json={"note": "ok"}, headers=H)
    assert r.status_code == 200 and s.select("outtake", {"outtake_id": "out0"})[0]["status"] == "accepted"
    assert c.post("/api/outtakes/out0/reject", json={}, headers=H).status_code == 409
    assert c.post("/api/outtakes/out1/reject", json={"note": "wrong tone"}, headers=H).status_code == 200
    assert c.post("/api/undo", json={"audit_event_id": r.json()["audit_event_id"]}, headers=H).status_code == 200
    assert s.select("outtake", {"outtake_id": "out0"})[0]["status"] == "draft"
    assert c.post("/api/outtakes/nope/accept", json={}, headers=H).status_code == 404


def test_label_panel_is_blind_until_saved(board):
    c, s, lab = board
    q = c.get("/api/labels/queue").json()
    assert len(q["briefs"]) == 3 and len(q["noise"]) == 40
    text = json.dumps(q)
    assert "verdict" not in text and "critique" not in text  # the judge's view is never in the queue
    brief = next(b for b in q["briefs"] if b["title"] == "Audit-trail export is slow")
    r = c.post("/api/labels", json={"target_type": "brief", "target_id": brief["target_id"], "judge": "faithfulness", "verdict": "pass"}, headers=H)
    assert r.status_code == 200 and r.json()["revealed"]["verdict"] == "fail" and "faithfulness critique" in r.json()["revealed"]["critique"]
    row = s.select("label")[0]
    assert (row["blind"], row["origin"], row["split"] in ("dev", "held_out"), row["actor"]) == (1, "live_reviewer", True, "priya.n")
    assert c.post("/api/labels", json={"target_type": "brief", "target_id": brief["target_id"], "judge": "faithfulness", "verdict": "pass"}, headers=H).status_code == 409
    assert all(not (b["target_id"] == brief["target_id"] and "faithfulness" in b["judges"]) for b in c.get("/api/labels/queue").json()["briefs"])
    n = q["noise"][0]
    assert c.post("/api/labels", json={"target_type": "noise_audit", "target_id": n["snippet_id"], "judge": "signal", "verdict": "pass"}, headers=H).json()["revealed"] is None
    assert s.select("label")[1]["weight"] == n["audit_weight"]
    assert c.post("/api/labels", json={"target_type": "brief", "target_id": "nope", "judge": "signal", "verdict": "pass"}, headers=H).status_code == 404
    assert (lab / "priya.n.jsonl").read_text(encoding="utf-8").count('"kind": "label"') == 2
    assert counts(s)["audit_event"] == 2 + 2  # two seeded events plus one per label


def test_actor_name_cannot_escape_the_labels_folder(board):
    c, s, lab = board
    assert c.post("/api/opportunities/o1/park", json={}, headers={"X-Actor": "../../evil"}).status_code == 403  # not on the allow-list
    assert not lab.exists() or all(p.parent == lab for p in lab.iterdir())


def test_reads_and_audit_filters(board):
    c, s, _ = board
    assert c.get("/api/me").json()["actor"]
    top = c.get("/api/opportunities", params={"status": "proposed"}).json()
    assert [o["opportunity_id"] for o in top] == ["o1", "o2", "o5"]
    assert c.get("/api/opportunities/o1").json()["accounts"]
    assert c.get("/api/opportunities/zzz").status_code == 404
    a = c.get("/api/audit", params={"table": "audit_event", "actor": "priya.n"}).json()
    assert a["total"] == 1 and a["chain"]["ok"]
    m = c.get("/api/audit", params={"table": "model_call", "stage": "brief", "cached": "1"}).json()
    assert m["total"] > 0 and all(r["stage"] == "brief" and r["cached"] for r in m["rows"])
    assert c.get("/api/pipeline").json()["total"]["raw"] > 0
    assert "not evaluated" not in c.get("/").text and c.get("/").status_code == 200
    assert c.get("/raw/zzz").status_code == 404
