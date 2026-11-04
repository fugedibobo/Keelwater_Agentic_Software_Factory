"""Board actions: one annotation and one audit_event per action in one transaction, labels per evals.md 5.4, undo.

Status and squad moves go through the #1 helpers (transition, reassign, undo); text and tag edits and outtake decisions
write their own audit_event with a `restore` block so the same 10-second undo reverses them.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .. import config
from ..contracts import Annotation, Label
from ..store import UNDO_WINDOW_S, now_iso, sha256, transition, reassign, undo as store_undo
from . import read

NEEDS_NOTE = {"already_shipped", "already_on_roadmap", "evidence_wrong"}  # evals.md 5.4: a reference or note is required
REJECT_LABEL = {"not_product_signal": ("signal", "fail"), "already_shipped": ("duplicate", "fail"),
                "already_on_roadmap": ("duplicate", "fail"), "evidence_wrong": ("faithfulness", "fail")}


class Invalid(Exception):
    """Bad input (HTTP 422)."""


class Missing(LookupError):
    """Unknown target (HTTP 404)."""


class Board:
    def __init__(self, store, labels_dir, reports_dir=None):
        self.store, self.labels_dir, self.reports_dir = store, Path(labels_dir), reports_dir


def person(actor):
    a = (actor or "").strip()
    if not a or a.lower() == "system":
        raise PermissionError("X-Actor must be a person")
    if len(a) > 64:
        raise Invalid("X-Actor too long")
    return a


def split_of(key):
    return "dev" if int(sha256(key), 16) % 100 < 30 else "held_out"  # evals.md 5.5 (sha256 of the opportunity id, mod 100)


def _jsonl(b, actor, *lines):
    # shortcut: append-only file per actor, no locking across processes; fine for one local server.
    b.labels_dir.mkdir(parents=True, exist_ok=True)
    with (b.labels_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", actor) + ".jsonl")).open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, sort_keys=True, default=str) + "\n")


def _set(store, table, key_col, key, values):
    """UPDATE without commit (Store.update commits), so the caller's transaction stays whole."""
    store.db.execute(f"UPDATE {table} SET {','.join(c + '=?' for c in values)} WHERE {key_col}=?", [*values.values(), key])


def _ins(store, table, model):
    """INSERT a validated model without commit (Store.insert commits), so the caller's transaction stays whole."""
    data = model.model_dump(mode="json")
    store.db.execute(f"INSERT INTO {table} ({','.join(data)}) VALUES ({','.join('?' * len(data))})", [int(v) if isinstance(v, bool) else v for v in data.values()])


def _opp(store, oid):
    rows = store.select("opportunity", {"opportunity_id": oid})
    if not rows:
        raise Missing(f"unknown opportunity {oid}")
    return rows[0]


def _brief_id(store, oid):
    r = store.db.execute("SELECT brief_id FROM brief WHERE opportunity_id=? ORDER BY rowid DESC LIMIT 1", (oid,)).fetchone()
    return r[0] if r else None


def _labels(store, oid, actor, stamp, specs):
    out = []
    for judge, verdict in specs:
        tt, tid = ("brief", _brief_id(store, oid)) if judge == "faithfulness" else ("opportunity", oid)
        if tid:
            out.append(Label(label_id=uuid4().hex, judge=judge, target_type=tt, target_id=tid, verdict=verdict, critique="from board action",
                             origin="live_reviewer", blind=False, split=split_of(oid), actor=actor, created_at=stamp))
    return out


def _write(b, actor, annotation, labels, run):
    """Insert annotation and labels, then run() (which writes the audit_event); one transaction, one jsonl record."""
    store = b.store
    with store.lock, store.db:
        _ins(store, "annotation", annotation)
        for l in labels:
            _ins(store, "label", l)
        eid = run()
    _jsonl(b, actor, {"kind": "annotation", "audit_event_id": eid, **annotation.model_dump(mode="json")},
           *({"kind": "label", "audit_event_id": eid, **l.model_dump(mode="json")} for l in labels))
    return eid


def _ann(oid, actor, action, stamp, reason=None, note=None, target_type="opportunity"):
    return Annotation(annotation_id=uuid4().hex, target_type=target_type, target_id=oid, actor=actor, action=action, reason_code=reason,
                      note=note or None, created_at=stamp)


def _result(b, eid, oid):
    return {"audit_event_id": eid, "opportunity": _opp(b.store, oid), "undo_window_s": UNDO_WINDOW_S}


def decide(b, oid, actor, action, to_status, reason=None, note=None, label_specs=(), merged_into=None):
    actor = person(actor)
    _opp(b.store, oid)
    if reason in NEEDS_NOTE and not note:
        raise Invalid(f"reason {reason} needs a reference or note")
    stamp = now_iso()
    ann, labels = _ann(oid, actor, action, stamp, reason, note), _labels(b.store, oid, actor, stamp, label_specs)

    def run():
        if merged_into:
            _set(b.store, "opportunity", "opportunity_id", oid, {"merged_into": merged_into})
        return transition(b.store, oid, to_status, actor, "person", {"annotation_id": ann.annotation_id, "label_ids": [l.label_id for l in labels],
                                                                       "reason_code": reason, "note": note, "action": action})
    try:
        eid = _write(b, actor, ann, labels, run)
    except ValueError as e:  # illegal status move: the whole transaction rolled back
        raise Conflict(str(e)) from e
    return _result(b, eid, oid)


class Conflict(ValueError):
    """Illegal move or stale undo (HTTP 409)."""


def accept(b, oid, actor, confirmed):
    if not confirmed:
        raise Invalid("accept needs confirmed: true")
    return decide(b, oid, actor, "accept", "accepted", label_specs=[("signal", "pass"), ("duplicate", "pass")])


def merge(b, oid, actor, target_id):
    if target_id == oid:
        raise Invalid("cannot merge into itself")
    _opp(b.store, target_id)
    return decide(b, oid, actor, "merge", "merged", merged_into=target_id, note=f"merged into {target_id}")


def reject(b, oid, actor, reason, note):
    reason = str(reason)
    specs = [REJECT_LABEL[reason]] if reason in REJECT_LABEL else []
    return decide(b, oid, actor, "reject", "rejected", reason=reason, note=note, label_specs=specs)


def park(b, oid, actor, note):
    return decide(b, oid, actor, "park", "parked", note=note)


def do_reassign(b, oid, actor, squad):
    actor = person(actor)
    _opp(b.store, oid)
    if squad not in config.squads():
        raise Invalid(f"unknown squad {squad}")
    ann = _ann(oid, actor, "reassign", now_iso(), note=f"to {squad}")
    return _result(b, _write(b, actor, ann, [], lambda: reassign(b.store, oid, squad, actor, "person", {"annotation_id": ann.annotation_id})), oid)


def _own(b, target_type, tid, actor, action, table, key_col, before, after, note=None, reason=None, labels=(), label_oid=None):
    """An action outside the transition helper: update + annotation + audit_event with a restore block for undo."""
    actor = person(actor)
    stamp = now_iso()
    ann = _ann(tid, actor, action, stamp, reason, note, target_type)
    labels = _labels(b.store, label_oid, actor, stamp, labels) if label_oid else []
    details = {"annotation_id": ann.annotation_id, "label_ids": [l.label_id for l in labels], "note": note,
               "restore": {"table": table, "key_col": key_col, "key": tid, "before": before, "after": after}}

    def run():
        _set(b.store, table, key_col, tid, after)
        return b.store.append_audit(actor, "person", f"{target_type}.{action}", target_type, tid, details)
    return _write(b, actor, ann, labels, run)


def edit(b, oid, actor, title, problem, original_wrong):
    o = _opp(b.store, oid)
    if not title.strip() or not problem.strip():
        raise Invalid("title and problem statement are required")
    eid = _own(b, "opportunity", oid, actor, "edit", "opportunity", "opportunity_id", {"title": o["title"], "problem_statement": o["problem_statement"]},
               {"title": title, "problem_statement": problem}, note="original was wrong" if original_wrong else "original was fine",
               labels=[("faithfulness", "fail")] if original_wrong else [], label_oid=oid)
    return _result(b, eid, oid)


def tag(b, oid, actor, confirm, note=None):
    o = _opp(b.store, oid)
    if o["tag"] == "none" or o["tag_state"] != "proposed":
        raise Conflict("no proposed tag to " + ("confirm" if confirm else "remove"))
    state = "confirmed" if confirm else "removed"
    eid = _own(b, "opportunity", oid, actor, "confirm_tag" if confirm else "remove_tag", "opportunity", "opportunity_id",
               {"tag_state": "proposed"}, {"tag_state": state}, note=note)
    return _result(b, eid, oid)


def outtake(b, out_id, actor, decision, note):
    rows = b.store.select("outtake", {"outtake_id": out_id})
    if not rows:
        raise Missing(f"unknown outtake {out_id}")
    if rows[0]["status"] != "draft":
        raise Conflict(f"outtake is already {rows[0]['status']}")
    eid = _own(b, "outtake", out_id, actor, "accept" if decision == "accepted" else "reject", "outtake", "outtake_id", {"status": "draft"}, {"status": decision}, note=note)
    return {"audit_event_id": eid, "outtake": b.store.select("outtake", {"outtake_id": out_id})[0], "undo_window_s": UNDO_WINDOW_S}


def undo(b, event_id, actor, now=None):
    actor = person(actor)
    store = b.store
    ev = store.db.execute("SELECT * FROM audit_event WHERE event_id=?", (event_id,)).fetchone()
    if ev is None:
        raise Conflict("nothing to undo for that event")
    details = json.loads(ev["details_json"])
    if "restore" not in details:
        try:
            eid = store_undo(store, event_id, actor, now)
        except PermissionError:
            raise
        except ValueError as e:
            raise Conflict(str(e)) from e
        extra = {"merged_into": None} if details.get("to_status") == "merged" else {}
        with store.lock, store.db:  # shortcut: cleanup after the helper's commit, not in its transaction; fold into store.undo when #1 allows
            if extra:
                _set(store, "opportunity", "opportunity_id", ev["target_id"], extra)
            store.db.executemany("DELETE FROM label WHERE label_id=?", [(i,) for i in details.get("label_ids", [])])
    else:
        r, now = details["restore"], now or datetime.now(timezone.utc)
        if ev["actor"] != actor:
            raise PermissionError("only the actor who acted can undo")
        if not 0 <= (now - datetime.fromisoformat(ev["at"])).total_seconds() <= UNDO_WINDOW_S:
            raise Conflict("undo window of 10 seconds has passed")
        with store.lock, store.db:
            if store.db.execute("SELECT 1 FROM annotation WHERE undo_of=?", (event_id,)).fetchone():
                raise Conflict("already undone")
            cur = store.select(r["table"], {r["key_col"]: r["key"]})
            if not cur or any(cur[0][k] != v for k, v in r["after"].items()):
                raise Conflict("changed since that action")
            _set(store, r["table"], r["key_col"], r["key"], r["before"])
            store.db.executemany("DELETE FROM label WHERE label_id=?", [(i,) for i in details.get("label_ids", [])])
            stamp = now.isoformat()
            _ins(store, "annotation", Annotation(annotation_id=uuid4().hex, target_type=ev["target_type"], target_id=ev["target_id"], actor=actor,
                                                  action="undo", undo_of=event_id, created_at=stamp))
            eid = store.append_audit(actor, "person", "undo", ev["target_type"], ev["target_id"], {"undo_of": event_id}, at=stamp)
    _jsonl(b, actor, {"kind": "undo", "undo_of": event_id, "audit_event_id": eid, "label_ids": details.get("label_ids", [])})
    return {"audit_event_id": eid, "undone": event_id}


def add_label(b, actor, body):
    actor = person(actor)
    store = b.store
    if body.target_type == "brief":
        if not store.select("brief", {"brief_id": body.target_id}):
            raise Missing(f"unknown brief {body.target_id}")
        if body.judge.value == "duplicate":
            raise Invalid("the duplicate judge labels opportunities, not briefs")
        key, weight = body.target_id, 1.0
        opp = store.select("brief", {"brief_id": body.target_id})[0]["opportunity_id"]
        key = opp
    elif body.target_type == "noise_audit":
        t = store.db.execute("SELECT audit_weight FROM triage WHERE snippet_id=? AND decision='drop' AND audit_weight IS NOT NULL", (body.target_id,)).fetchone()
        if t is None:
            raise Missing(f"unknown noise-audit item {body.target_id}")
        if body.judge.value != "signal":
            raise Invalid("noise-audit items take the signal judge")
        key, weight = body.target_id, t[0]
    else:
        raise Invalid("target_type must be brief or noise_audit")
    if store.db.execute("SELECT 1 FROM label WHERE actor=? AND target_type=? AND target_id=? AND judge=?", (actor, body.target_type, body.target_id, body.judge.value)).fetchone():
        raise Conflict("already labelled")
    stamp = now_iso()
    label = Label(label_id=uuid4().hex, judge=body.judge, target_type=body.target_type, target_id=body.target_id, verdict=body.verdict, critique=body.critique,
                  origin="live_reviewer", blind=True, split=split_of(key), weight=weight, actor=actor, created_at=stamp)
    with store.lock, store.db:
        _ins(store, "label", label)
        eid = store.append_audit(actor, "person", "label.add", body.target_type, body.target_id,
                                 {"label_id": label.label_id, "judge": body.judge.value, "verdict": body.verdict.value, "blind": True})
    _jsonl(b, actor, {"kind": "label", "audit_event_id": eid, **label.model_dump(mode="json")})
    revealed = read.judge_critique(store, body.target_type, body.target_id, body.judge.value) if body.target_type == "brief" else None
    return {"audit_event_id": eid, "label_id": label.label_id, "revealed": revealed}
