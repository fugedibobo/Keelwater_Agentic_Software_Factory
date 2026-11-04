"""Adversarial-review findings 4a, 4b, 6 and 7 (issue #13): each test reproduces the reported scenario."""

import json
import sqlite3
from pathlib import Path

import pytest

from test_board_api import H, board, counts, status  # noqa: F401  (board is a fixture)
from signal_engine import config
from signal_engine.board import actions, cli as board_cli
from signal_engine.evals import labels
from signal_engine.store import Store, canonical, sha256


# ---- 4a: only configured people are persons ----
def test_4a_unlisted_actor_is_refused(board):
    c, s, lab = board
    before = counts(s)
    for actor in ("bot", "someone.else", "../../evil"):
        assert c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers={"X-Actor": actor}).status_code == 403
    assert counts(s) == before and status(s, "o1")["status"] == "proposed" and not lab.exists()
    assert c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers=H).status_code == 200
    assert c.get("/api/me").json()["actor"] in config.people()  # the page must send an accepted actor


# ---- 4b: undo is one transaction; the jsonl record cannot be lost ----
def test_4b_failed_merge_undo_leaves_the_merge_intact(board, monkeypatch):
    c, s, lab = board
    eid = c.post("/api/opportunities/o1/merge", json={"target_id": "o2"}, headers=H).json()["audit_event_id"]
    real = actions._set
    monkeypatch.setattr(actions, "_set", lambda st, t, k, key, v: (_ for _ in ()).throw(RuntimeError("boom")) if "merged_into" in v else real(st, t, k, key, v))
    with pytest.raises(RuntimeError):
        actions.undo(actions.Board(s, lab), eid, "priya.n")
    o = status(s, "o1")
    assert (o["status"], o["merged_into"]) == ("merged", "o2") and not s.select("annotation", {"undo_of": eid})


def test_4b_failed_accept_undo_keeps_status_and_labels_together(board):
    c, s, lab = board
    eid = c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers=H).json()["audit_event_id"]
    s.db.execute("CREATE TRIGGER no_label_delete BEFORE DELETE ON label BEGIN SELECT RAISE(ABORT, 'boom'); END")
    s.db.commit()
    with pytest.raises(sqlite3.DatabaseError):
        actions.undo(actions.Board(s, lab), eid, "priya.n")
    assert status(s, "o1")["status"] == "accepted" and len(s.select("label")) == 2


def test_4b_file_failure_does_not_lose_the_record(board, monkeypatch):
    c, s, lab = board
    real = actions._append
    monkeypatch.setattr(actions, "_append", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    assert c.post("/api/opportunities/o1/accept", json={"confirmed": True}, headers=H).status_code == 200
    assert not (lab / "priya.n.jsonl").exists() and s.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 3
    monkeypatch.setattr(actions, "_append", real)
    b = actions.Board(s, lab)
    actions.flush(b)
    actions.flush(b)  # idempotent
    lines = (lab / "priya.n.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and s.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


# ---- 6: no replacement path for audit_event ----
def test_6_audit_event_cannot_be_replaced(tmp_store):
    s = tmp_store
    s.append_audit("p", "person", "accept", "opportunity", "o", {"x": 1})
    last = s.append_audit("p", "person", "edit", "opportunity", "o", {"x": 2})
    row = dict(s.db.execute("SELECT * FROM audit_event WHERE event_id=?", (last,)).fetchone())
    row["details_json"] = canonical({"x": 999})
    row.pop("hash")
    row["hash"] = sha256(row["prev_hash"] + canonical(row))
    with pytest.raises(sqlite3.DatabaseError):
        s.db.execute("INSERT OR REPLACE INTO audit_event VALUES (:event_id,:at,:actor,:actor_kind,:action,:target_type,:target_id,:details_json,:prev_hash,:hash)", row)
    with pytest.raises(ValueError):
        s.insert("audit_event", row, replace=True)
    assert s.db.execute("SELECT details_json FROM audit_event WHERE event_id=?", (last,)).fetchone()[0] == canonical({"x": 2})
    assert s.verify_audit_chain()
    s.db.execute("DROP TRIGGER audit_no_update")  # tampering by other means is still caught
    s.db.execute("UPDATE audit_event SET details_json='{}' WHERE event_id=?", (last,))
    assert not s.verify_audit_chain()


# ---- 7: no local paths in audit data or the static export ----
def test_7_label_import_records_a_relative_identifier(tmp_store):
    d = config.ROOT / "labels" / "human"
    (d).mkdir(parents=True, exist_ok=True)
    f = d / "zz_review_b.jsonl"
    f.write_text(json.dumps({"kind": "label", "label_id": "zl1", "judge": "signal", "target_type": "brief", "target_id": "B1", "verdict": "pass",
                             "critique": "x", "origin": "live_reviewer", "blind": True, "split": "dev", "weight": 1.0, "actor": "pm1",
                             "created_at": "2026-11-03T00:00:00+00:00"}) + "\n", encoding="utf-8")
    try:
        labels.import_path(tmp_store, d)
    finally:
        f.unlink()
    (tid,) = [r[0] for r in tmp_store.db.execute("SELECT target_id FROM audit_event WHERE action='labels.import'")]
    assert tid == "labels/human" and str(config.ROOT) not in tid


def test_7_static_export_scrubs_existing_absolute_paths(board, tmp_path):
    c, s, _ = board
    s.append_audit("system", "system", "labels.import", "labels", str(config.ROOT / "labels" / "human"), {"files": 1})
    s.append_audit("system", "system", "labels.import", "labels", str(config.ROOT).replace("\\", "/") + "/x", {"files": 1})
    s.db.commit()
    out = tmp_path / "site"
    board_cli.main(["static", "--db", str(s.path), "--out", str(out)])
    html = (out / "index.html").read_text(encoding="utf-8")
    assert str(config.ROOT) not in html and str(config.ROOT).replace("\\", "/") not in html and str(config.ROOT).replace("\\", "\\\\") not in html
    assert "labels/human" in html


def test_7_static_export_strips_any_absolute_path(board, tmp_path):
    c, s, _ = board
    paths = [r"C:\Users\someone\other-worktree\labels\human", "D:/external/labels/human", r"\\fileserver\share\labels\human",
             "/home/bob/labels/human", "/Users/bob/labels/human", "/tmp/zz_labels"]
    for p in paths:
        s.append_audit("system", "system", "labels.import", "labels", p, {"files": 1, "from": p})
    s.db.commit()
    out = tmp_path / "site"
    board_cli.main(["static", "--db", str(s.path), "--out", str(out)])
    html = (out / "index.html").read_text(encoding="utf-8")
    for leak in ("someone", "other-worktree", "external", "fileserver", "/home/bob", "/Users/bob", "zz_labels"):
        assert leak not in html, leak
