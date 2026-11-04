"""Stage 0: native exports -> raw_record, with per-source schema validation, route and account resolution."""

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from ..config import ROOT
from ..store import raw_id
from . import accounts as acc
from .fullstory import ts

SCHEMAS = ROOT / "contracts" / "sources"


def _schema(name, *path):
    s = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    for k in path:
        s = s[k]
    return jsonschema.Draft202012Validator(s)


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def _sid(item, default):
    return item.get("id", default) if isinstance(item, dict) else default


class Connector:
    def __init__(self, ctx):
        self.store = ctx.store
        self.root = Path(ctx.data_dir)
        self.teams = acc.load_teams(self.root)
        self.dom_map, self.id_map = {}, {}

    def quarantine(self, source, source_id, reason):
        self.store.append_audit("system", "system", "ingest.quarantine", "raw_record", f"{source}:{source_id}",
                                {"source": source, "source_id": str(source_id), "reason": reason})

    def check(self, validator, item, source, source_id):
        err = next(iter(validator.iter_errors(item)), None)
        if err:
            self.quarantine(source, source_id, f"{err.message[:160]} at {'/'.join(map(str, err.absolute_path))}")
        return err is None

    def write(self, source, source_id, payload, route=None, account=(None, None), occurred_at=None):
        self.store.insert("raw_record", {
            "raw_id": raw_id(source, source_id), "source": source, "route": route, "source_id": str(source_id),
            "account_id": account[0], "account_status": account[1], "occurred_at": occurred_at, "payload_json": payload},
            replace=True)

    def load(self, rel):
        """Parsed JSON of a file under the data root, or None when absent; unreadable JSON is quarantined."""
        p = self.root / rel
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            self.quarantine(rel.split("/")[0], rel, f"not valid JSON: {e}")

    def files(self, folder):
        d = self.root / folder
        return sorted(d.glob("*.json")) if d.is_dir() else []

    # ---- sources ---------------------------------------------------------------------------------------------
    def hubspot(self):
        data, v = self.load("hubspot/companies.json"), _schema("hubspot_companies", "properties", "results", "items")
        good = [r for r in (data or {}).get("results", []) if self.check(v, r, "hubspot", _sid(r, "?"))]
        accts, self.id_map, self.dom_map = acc.canonical_accounts(good)
        for a in accts:
            self.store.insert("account", a, replace=True)
        for r in good:
            self.write("hubspot", r["id"], r)

    def gong(self):
        calls, trs = self.load("gong/calls.json"), self.load("gong/transcripts.json")
        vc = _schema("gong_calls", "properties", "calls", "items")
        vt = _schema("gong_transcripts", "properties", "callTranscripts", "items")
        tr = {}
        for t in (trs or {}).get("callTranscripts", []):
            if self.check(vt, t, "gong", f"transcript:{t.get('callId', '?') if isinstance(t, dict) else '?'}"):
                tr[t["callId"]] = t["transcript"]
        for c in (calls or {}).get("calls", []):
            cid = c.get("metaData", {}).get("id", "?") if isinstance(c, dict) else "?"
            if not self.check(vc, c, "gong", cid):
                continue
            ids = {self.id_map[o["objectId"]] for x in c.get("context", []) if x["system"].lower() == "hubspot"
                   for o in x["objects"] if o["objectType"].lower() in ("account", "company") and o["objectId"] in self.id_map}
            account = acc.settle(ids) if ids else acc.by_emails(
                [p.get("emailAddress") for p in c["parties"] if p["affiliation"] == "External"], self.dom_map)
            self.write("gong", cid, {"call": c, "transcript": tr.get(cid, [])}, "sales", account, c["metaData"]["started"])

    def intercom(self):
        v = _schema("intercom_conversation")
        for f in self.files("intercom"):
            c = self.load(f"intercom/{f.name}")
            if c is None or not self.check(v, c, "intercom", _sid(c, f.name)):
                continue
            self.write("intercom", c["id"], c, "support", acc.by_emails([c["source"]["author"].get("email")], self.dom_map),
                       _iso(c["created_at"]))

    def fireflies(self):
        v = _schema("fireflies_transcript")
        for f in self.files("fireflies"):
            t = self.load(f"fireflies/{f.name}")
            if t is None or not self.check(v, t, "fireflies", _sid(t, f.name)):
                continue
            emails = [a["email"] for a in t.get("meeting_attendees", [])]
            route = next((r for e in [t["host_email"], *emails]
                          if (r := acc.team_of(e, self.teams)) in ("onboarding", "account_management")), None)
            customers = [e for e in emails if not acc.is_internal(e, self.teams)]
            self.write("fireflies", t["id"], t, route, acc.by_emails(customers, self.dom_map),
                       datetime.fromtimestamp(t["date"] / 1000, timezone.utc).isoformat())

    def fullstory(self):
        sessions, vs = self.load("fullstory/sessions.json"), _schema("fullstory_session")
        ve, events = _schema("fullstory_event"), {}
        p = self.root / "fullstory" / "events.ndjson"
        for n, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines() if p.is_file() else [], 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                ok = self.check(ve, e, "fullstory", f"event line {n}")
                if ok:
                    ts(e["event_time"])
            except ValueError as ex:
                self.quarantine("fullstory", f"event line {n}", f"unreadable event: {ex}")
                continue
            if ok:
                events.setdefault(e["session_id"], []).append(e)
        known = set()
        for s in sessions or []:
            sid = s.get("sessionId", "?") if isinstance(s, dict) else "?"
            if not self.check(vs, s, "fullstory", sid):
                continue
            known.add(sid)
            self.write("fullstory", sid, {"session": s, "events": events.get(sid, [])}, "sessions",
                       acc.by_emails([s["userId"]], self.dom_map), s["createdTime"])
        for sid in sorted(set(events) - known):
            self.quarantine("fullstory", sid, f"{len(events[sid])} events without a session row")

    def reference(self, source, rel, key, name):
        data, v = self.load(rel), _schema(name, "properties", key, "items")
        for r in (data or {}).get(key, []):
            sid = _sid(r, "?")
            if self.check(v, r, source, sid):
                self.write(source, sid, r, occurred_at=r.get("completed_at"))


def run(ctx):
    c = Connector(ctx)
    c.hubspot()  # first: every other source resolves accounts against it
    c.gong()
    c.intercom()
    c.fireflies()
    c.fullstory()
    c.reference("shortcut", "shortcut/stories.json", "stories", "shortcut_stories")
    c.reference("notion", "notion/pages.json", "results", "notion_pages")
