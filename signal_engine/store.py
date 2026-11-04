"""SQLite store, content-hash ids, hash-chained audit log, status machine and output hash."""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from .contracts import HUMAN_GATES, OUTPUT_HASH_EXCLUDE, OUTPUT_TABLES, TABLES, TRANSITIONS

DEFAULT_DB = ".local/keelwater.sqlite"
UNDO_WINDOW_S = 10
# Columns holding JSON text; decoded on select.
JSON_COLUMNS = {"embedding", "centroid", "prompt_versions", "model_ids", "evidence_snapshot"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(value):
    return hashlib.sha256((value if isinstance(value, bytes) else str(value).encode("utf-8"))).hexdigest()


def content_id(*keys):
    """First 16 hex of sha256 over a record's content keys."""
    return sha256(canonical(list(keys)))[:16]


# One helper per id kind, so every stage derives ids the same way.
def raw_id(source, source_id):
    return content_id("raw", source, source_id)


def snippet_id(raw, start_ms, text):
    return content_id("snippet", raw, start_ms, text)


def insight_id(snippet, quote):
    return content_id("insight", snippet, quote)


def opportunity_id(seed_insight_id):
    return content_id("opportunity", seed_insight_id)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_json_col(col):
    return col.endswith("_json") or col in JSON_COLUMNS


def _enc(col, v):
    if isinstance(v, bool):
        return int(v)
    if _is_json_col(col) and not isinstance(v, str):
        return canonical(v)
    return v


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # shortcut: one connection shared across gateway threads under a lock, move to a pool with Postgres.
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()

    def init(self):
        self.db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        self.db.commit()
        return self

    @classmethod
    def fresh(cls, path=DEFAULT_DB):
        """Delete and recreate the store file."""
        path = Path(path)
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        return cls(path).init()

    def close(self):
        self.db.close()

    def insert(self, table, row, replace=False):
        if replace and table == "audit_event":
            raise ValueError("audit_event is append-only: no replace")
        data = row.model_dump(mode="json") if isinstance(row, BaseModel) else dict(row)
        if isinstance(row, BaseModel):
            TABLES[table].model_validate(data)
        cols = list(data)
        sql = f"INSERT {'OR REPLACE ' if replace else ''}INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        with self.lock, self.db:
            self.db.execute(sql, [_enc(c, data[c]) for c in cols])

    def select(self, table, where=None, order_by=None):
        where = where or {}
        sql = f"SELECT * FROM {table}" + (" WHERE " + " AND ".join(f"{k}=?" for k in where) if where else "")
        sql += f" ORDER BY {order_by or 'rowid'}"
        with self.lock:
            rows = self.db.execute(sql, list(where.values())).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({k: (json.loads(v) if isinstance(v, str) and _is_json_col(k) else v) for k, v in d.items()})
        return out

    def update(self, table, key, values):
        """key is a one-entry {column: value}; values are columns to set."""
        (kc, kv), = key.items()
        with self.lock, self.db:
            self.db.execute(f"UPDATE {table} SET {','.join(c + '=?' for c in values)} WHERE {kc}=?",
                            [_enc(c, v) for c, v in values.items()] + [kv])

    # ---- audit chain ----------------------------------------------------------------------------------------
    def append_audit(self, actor, actor_kind, action, target_type, target_id, details, at=None):
        with self.lock:
            owned = not self.db.in_transaction  # inside a caller's transaction the caller commits, so both land together
            prev = self.db.execute("SELECT hash FROM audit_event ORDER BY rowid DESC LIMIT 1").fetchone()
            event = dict(event_id=uuid4().hex, at=at or now_iso(), actor=actor, actor_kind=actor_kind, action=action,
                         target_type=target_type, target_id=target_id, details_json=canonical(details),
                         prev_hash=prev[0] if prev else "")
            event["hash"] = sha256(event["prev_hash"] + canonical(event))
            self.db.execute("INSERT INTO audit_event VALUES (:event_id,:at,:actor,:actor_kind,:action,:target_type,"
                            ":target_id,:details_json,:prev_hash,:hash)", event)
            if owned:
                self.db.commit()
        return event["event_id"]

    def verify_audit_chain(self):
        prev = ""
        for row in self.db.execute("SELECT * FROM audit_event ORDER BY rowid"):
            event = dict(row)
            digest = event.pop("hash")
            if event["prev_hash"] != prev or sha256(prev + canonical(event)) != digest:
                return False
            prev = digest
        return True

    # ---- output hash ----------------------------------------------------------------------------------------
    def output_hash(self):
        """sha256 over the sorted rows of the output tables, without run-varying columns."""
        parts = []
        for table in OUTPUT_TABLES:
            rows = [{k: v for k, v in r.items() if k not in OUTPUT_HASH_EXCLUDE} for r in self.select(table)]
            parts.append([table, sorted(canonical(r) for r in rows)])
        return sha256(canonical(parts))


def transition(store, opportunity_id, to_status, actor, actor_kind, details=None, at=None):
    """Move an opportunity along the status machine; writes the audit_event in the same transaction."""
    details = details or {}
    with store.lock, store.db:
        row = store.db.execute("SELECT status FROM opportunity WHERE opportunity_id=?", (opportunity_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown opportunity {opportunity_id}")
        old = row[0]
        if to_status not in TRANSITIONS.get(old, set()):
            raise ValueError(f"illegal transition {old} -> {to_status}")
        if (old, to_status) in HUMAN_GATES and actor_kind != "person":
            raise PermissionError(f"{old} -> {to_status} is a human gate; actor_kind must be person")
        d = dict(details, from_status=old, to_status=to_status)
        if to_status == "accepted" and old == "proposed":
            d["evidence_snapshot"] = [r[0] for r in store.db.execute(
                "SELECT insight_id FROM opportunity_insight WHERE opportunity_id=? ORDER BY insight_id", (opportunity_id,))]
        store.db.execute("UPDATE opportunity SET status=? WHERE opportunity_id=?", (to_status, opportunity_id))
        return store.append_audit(actor, actor_kind, "opportunity.transition", "opportunity", opportunity_id, d, at=at)


def reassign(store, opportunity_id, squad, actor, actor_kind, details=None, at=None):
    """Reassign changes squad, not status; it is a human gate."""
    if actor_kind != "person":
        raise PermissionError("reassign is a human gate; actor_kind must be person")
    with store.lock, store.db:
        row = store.db.execute("SELECT squad FROM opportunity WHERE opportunity_id=?", (opportunity_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown opportunity {opportunity_id}")
        store.db.execute("UPDATE opportunity SET squad=? WHERE opportunity_id=?", (squad, opportunity_id))
        return store.append_audit(actor, actor_kind, "opportunity.reassign", "opportunity", opportunity_id,
                                  dict(details or {}, from_squad=row[0], to_squad=squad), at=at)


def undo(store, audit_event_id, actor, now=None, after=None):
    """Reverse one transition or reassign within 10 seconds by the same actor. Nothing is deleted. after(ev, details, event_id), if given, runs inside the same transaction."""
    now = now or datetime.now(timezone.utc)
    with store.lock, store.db:
        ev = store.db.execute("SELECT * FROM audit_event WHERE event_id=?", (audit_event_id,)).fetchone()
        if ev is None or ev["action"] not in ("opportunity.transition", "opportunity.reassign"):
            raise ValueError("nothing to undo for that event")
        if ev["actor"] != actor:
            raise PermissionError("only the actor who acted can undo")
        if not 0 <= (now - datetime.fromisoformat(ev["at"])).total_seconds() <= UNDO_WINDOW_S:
            raise ValueError("undo window of 10 seconds has passed")
        if store.db.execute("SELECT 1 FROM annotation WHERE undo_of=?", (audit_event_id,)).fetchone():
            raise ValueError("already undone")
        d = json.loads(ev["details_json"])
        col, old, new = ("status", d.get("from_status"), d.get("to_status")) if ev["action"] == "opportunity.transition" \
            else ("squad", d.get("from_squad"), d.get("to_squad"))
        cur = store.db.execute(f"SELECT {col} FROM opportunity WHERE opportunity_id=?", (ev["target_id"],)).fetchone()
        if cur is None or cur[0] != new:
            raise ValueError("opportunity changed since that action")
        store.db.execute(f"UPDATE opportunity SET {col}=? WHERE opportunity_id=?", (old, ev["target_id"]))
        stamp = now.isoformat()
        store.db.execute("INSERT INTO annotation (annotation_id,target_type,target_id,actor,action,undo_of,created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (uuid4().hex, "opportunity", ev["target_id"], actor, "undo", audit_event_id, stamp))
        eid = store.append_audit(actor, "person", "undo", "opportunity", ev["target_id"], {"undo_of": audit_event_id}, at=stamp)
        if after:
            after(ev, d, eid)
        return eid
