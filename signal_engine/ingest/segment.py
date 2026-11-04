"""Stage 1: raw_record -> snippet. Customer turns only, the preceding internal turn kept as context_text.

A turn is {side, key, email, text, start, end}; side is external (customer), internal (Keelwater staff),
quarantine (speaker maps to nobody), fin (Intercom bot) or note (Intercom admin note).
"""

import html
import re

from ..contracts import Snippet
from ..store import snippet_id
from . import accounts as acc
from . import fullstory as fs

SOURCES = ("gong", "intercom", "fireflies", "fullstory")


def group(sentences):
    """Consecutive sentences (key, email, side, text, start_ms, end_ms) by one speaker -> turns."""
    turns = []
    for key, email, side, text, a, b in sentences:
        if turns and turns[-1]["key"] == key:
            turns[-1]["text"] += " " + text.strip()
            turns[-1]["end"] = b
        else:
            turns.append({"side": side, "key": key, "email": email, "text": text.strip(), "start": a, "end": b})
    return turns


def emit(store, raw, turns):
    """Write snippets for external turns; audit speaker quarantines and removals. Returns the snippet count."""
    n, counts, prev, quarantined = 0, {"internal": 0, "fin": 0, "note": 0}, None, {}
    for t in turns:
        side = t["side"]
        if side == "note":  # a note is invisible to the conversation: it neither counts as context nor breaks it
            counts["note"] += 1
            continue
        if side == "external" and t["text"]:
            ctx = prev["text"] if prev and prev["side"] == "internal" else ""
            store.insert("snippet", Snippet(snippet_id=snippet_id(raw["raw_id"], t["start"], t["text"]), raw_id=raw["raw_id"],
                                            speaker_email=t["email"], text=t["text"], context_text=ctx,
                                            start_ms=t["start"], end_ms=t["end"]), replace=True)
            n += 1
        elif side == "quarantine":
            quarantined[t["key"]] = quarantined.get(t["key"], 0) + 1
        elif side in counts:
            counts[side] += 1
        prev = t
    for label, k in quarantined.items():
        store.append_audit("system", "system", "ingest.quarantine_speaker", "raw_record", raw["raw_id"],
                           {"source": raw["source"], "source_id": raw["source_id"], "speaker": label, "turns": k})
    if any(counts.values()):
        store.append_audit("system", "system", "segment.removed", "raw_record", raw["raw_id"], {"source": raw["source"], **counts})
    return n


def gong(raw, teams):
    p = raw["payload_json"]
    parties = {x["speakerId"]: x for x in p["call"]["parties"]}
    sents = []
    for item in p["transcript"]:
        party, sid = parties.get(item["speakerId"]), item["speakerId"]
        email = (party or {}).get("emailAddress")
        if party is None:
            side = "quarantine"
        elif acc.is_internal(email, teams) or party["affiliation"] == "Internal":
            side = "internal"
        elif party["affiliation"] == "External" or email:
            side = "external"
        else:
            side = "quarantine"
        sents += [(sid, email, side, s["text"], s["start"], s["end"]) for s in item["sentences"]]
    return group(sents)


def fireflies(raw, teams):
    t = raw["payload_json"]
    names = {}
    for a in t.get("meeting_attendees", []):
        for n in (a.get("name"), a.get("displayName")):
            if n:
                names[n.strip().casefold()] = a["email"]
    sents = []
    for s in t["sentences"]:
        email = names.get(s["speaker_name"].strip().casefold())
        side = "quarantine" if email is None else "internal" if acc.is_internal(email, teams) else "external"
        sents.append((s["speaker_name"], email, side, s["text"], round(s["start_time"] * 1000), round(s["end_time"] * 1000)))
    return group(sents)


def plain(body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", body or ""))).strip()


def intercom(raw, teams):
    c = raw["payload_json"]
    src = c["source"]
    t0, turns = c["created_at"], []
    turns.append({"side": "external" if src["author"]["type"] in ("user", "lead", "contact") else "internal", "key": "source",
                  "email": src["author"].get("email"), "text": plain(src.get("body")), "start": 0, "end": 0})
    for p in sorted(c["conversation_parts"]["conversation_parts"], key=lambda p: p["created_at"]):
        a = p["author"]["type"]
        side = ("fin" if a == "bot" else "note" if p["part_type"] == "note" else "internal" if a == "admin" else "external")
        ms = (p["created_at"] - t0) * 1000
        turns.append({"side": side, "key": a, "email": p["author"].get("email"), "text": plain(p.get("body")), "start": ms, "end": ms})
    return turns


def fullstory(store, raw):
    p = raw["payload_json"]
    start = fs.ts(p["session"]["createdTime"])
    wins, before, after = fs.windows(p["events"], start)
    ids = []
    for w in wins:
        text = "\n".join(w["lines"])
        sid = snippet_id(raw["raw_id"], w["start_ms"], text)
        store.insert("snippet", Snippet(snippet_id=sid, raw_id=raw["raw_id"], speaker_email=p["session"]["userId"], text=text,
                                        context_text="", start_ms=w["start_ms"], end_ms=w["end_ms"]), replace=True)
        ids.append({"snippet_id": sid, "event_ids": w["event_ids"]})  # evidence links back to the raw events
    store.append_audit("system", "system", "segment.fullstory", "raw_record", raw["raw_id"],
                       {"session_id": raw["source_id"], "before_s": before, "after_s": after, "windows": ids})
    return len(wins)


def reconciliation(store):
    """Per-source counts from the store, plus FullStory seconds before and after the idle-strip."""
    rows = {s: dict.fromkeys(("raw", "quarantined", "speaker_turns", "snippets", "internal", "fin", "notes"), 0) for s in
            ("gong", "intercom", "fireflies", "fullstory", "hubspot", "shortcut", "notion")}
    for r in store.select("raw_record"):
        rows[r["source"]]["raw"] += 1
    source_of = {r["raw_id"]: r["source"] for r in store.select("raw_record")}
    for s in store.select("snippet"):
        rows[source_of[s["raw_id"]]]["snippets"] += 1
    fs_s = [0.0, 0.0]
    for e in store.select("audit_event"):
        d = e["details_json"]
        if e["action"] == "ingest.quarantine":
            rows[d["source"]]["quarantined"] += 1
        elif e["action"] == "ingest.quarantine_speaker":
            rows[d["source"]]["speaker_turns"] += d["turns"]
        elif e["action"] == "segment.removed":
            for k in ("internal", "fin", "note"):
                rows[d["source"]]["notes" if k == "note" else k] += d[k]
        elif e["action"] == "segment.fullstory":
            fs_s[0] += d["before_s"]
            fs_s[1] += d["after_s"]
    return rows, fs_s


def table(store):
    rows, (before, after) = reconciliation(store)
    head = ("source", "raw", "quarantined", "q.speaker turns", "snippets", "internal removed", "Fin removed", "admin notes removed")
    lines = [head] + [(s, *map(str, r.values())) for s, r in rows.items()]
    w = [max(len(str(l[i])) for l in lines) for i in range(len(head))]
    out = ["  ".join(str(c).ljust(w[i]) for i, c in enumerate(l)) for l in lines]
    out.append(f"FullStory session minutes: {before / 60:.1f} before idle-strip, {after / 60:.1f} after")
    return "\n".join(out)


def run(ctx):
    teams = acc.load_teams(ctx.data_dir)
    for raw in ctx.store.select("raw_record"):
        if raw["source"] == "fullstory":
            fullstory(ctx.store, raw)
        elif raw["source"] in SOURCES:
            emit(ctx.store, raw, {"gong": gong, "intercom": intercom, "fireflies": fireflies}[raw["source"]](raw, teams))
    print(table(ctx.store))
