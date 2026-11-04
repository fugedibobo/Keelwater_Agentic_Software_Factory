"""Stage 10: accepted opportunity -> intent document (stays in the VPC) + de-identified factory job (docs/contracts)."""

import argparse
import json
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from . import citations, config
from .brief import chat_with_id, fact_sheet, members, render
from .contracts import Handoff
from .gateway import Gateway, GatewayError
from .prompts import load_prompt
from .store import Store, canonical, content_id, sha256, transition

VALIDATOR = Draft202012Validator(json.loads(config.FACTORY_JOB_SCHEMA.read_text(encoding="utf-8")))
TIERS = {"strategic": "Strategic", "enterprise": "Enterprise", "growth": "Growth"}
QUOTE_WORDS = 5


def norm(text):
    """evals.md 3.2 normalisation (the Gong/Fireflies filler rule is skipped: it only matters for quote matching)."""
    s = unicodedata.normalize("NFKC", str(text)).casefold()
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[‐-—]", "-", s).replace(" ", " ")
    s = re.sub(r"(?<=\d)\.(?=\d)", "\x00", s)  # keep . and , between digits
    s = re.sub(r"(?<=\d),(?=\d)", "\x02", s)
    s = re.sub(r"(?<=\w)'(?=\w)", "\x01", s)  # keep in-word apostrophes
    s = re.sub(r"[^\w\s£%\x00\x01\x02]|_", " ", s)
    return re.sub(r"\s+", " ", s.replace("\x00", ".").replace("\x01", "'").replace("\x02", ",")).strip()


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def deidentify_errors(job, store):
    """Errors for any account name, or any run of QUOTE_WORDS words copied from an insight quote, in the job."""
    text = " " + " ".join(norm(s) for s in _strings(job)) + " "
    errs = [f"de-identification: account name {a['name']!r} in job" for a in store.select("account")
            if norm(a["name"]) and f" {norm(a['name'])} " in text]
    words = text.split()
    grams = {" ".join(words[i:i + QUOTE_WORDS]) for i in range(len(words) - QUOTE_WORDS + 1)}
    for ins in store.select("insight"):
        q = norm(ins["quote"]).split()
        if any(" ".join(q[i:i + QUOTE_WORDS]) in grams for i in range(len(q) - QUOTE_WORDS + 1)):
            errs.append(f"de-identification: {QUOTE_WORDS}+ words of insight {ins['insight_id']} in job")
    return errs


def schema_errors(job):
    return [f"schema {'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}" for e in VALIDATOR.iter_errors(job)]


def arr_band(arr):
    return "under_100k" if arr < 1e5 else "100k_500k" if arr < 5e5 else "500k_1m" if arr < 1e6 else "over_1m"


def users_affected(store, ms):
    groups = {}
    for acct in {m["account_id"] for m in ms if m["account_id"]}:
        a = store.select("account", {"account_id": acct})[0]
        g = groups.setdefault(TIERS.get((a["tier"] or "").lower(), "prospect"), {"accounts": 0, "arr": 0.0})
        g["accounts"] += 1
        g["arr"] += a["arr_gbp"] or 0
    # shortcut: no contact roles in the store, so one generic role; upgrade when speaker roles are ingested.
    return [{"tier": t, "accounts": g["accounts"], "arr_band": arr_band(g["arr"]), "roles": ["claims handler"]}
            for t, g in sorted(groups.items())]


def manifest_hash(store):
    """Hash of the run inputs that decide the output (not profile or run id, so a replay matches the demo run)."""
    runs = store.select("run")
    r = runs[-1] if runs else {}
    return sha256(canonical({k: r.get(k) for k in ("data_hash", "config_hash", "prompt_versions", "model_ids")}))


def accept_event(store, opportunity_id):
    for ev in reversed(store.select("audit_event", {"target_id": opportunity_id})):
        if ev["action"] == "opportunity.transition" and ev["details_json"].get("to_status") == "accepted":
            return ev
    return None


def draft_intent(ctx, opp, ms):
    store, gw = ctx.store, ctx.gateway
    body, pv = load_prompt("handoff", "intent")
    by_id = {m["insight_id"]: m for m in ms}
    # shortcut: the fact sheet counts the current members, not only the accept-time snapshot; upgrade if joins change after accept.
    facts = fact_sheet(store, opp["opportunity_id"], ctx.as_of)
    names = {r["account_id"]: r["name"] for r in store.select("account")}
    prompt = render(body, opportunity={"title": opp["title"], "problem_statement": opp["problem_statement"]}, fact_sheet=facts,
                    insights=[{"id": m["insight_id"], "quote": m["quote"], "account": m["account"], "route": m["route"],
                               "date": m["date"]} for m in ms])
    out, _ = chat_with_id(gw, "handoff", prompt, "opportunity", opp["opportunity_id"], pv)
    fails = citations.check(out["intent_doc_md"], by_id, facts, names)
    if fails:  # one retry with the failure list, as the brief writer does
        retry = (prompt + "\n<failed_checks>\nYour previous draft failed these checks. Fix them and write the intent document again.\n"
                 + "\n".join(f"- {f['rule']}: {f['detail']}" for f in fails) + "\n</failed_checks>\n<previous_draft>\n"
                 + out["intent_doc_md"] + "\n</previous_draft>")
        out, _ = chat_with_id(gw, "handoff", retry, "opportunity", opp["opportunity_id"], pv)
        fails = citations.check(out["intent_doc_md"], by_id, facts, names)
    return out, fails


def build_job(ctx, opp, out, snapshot, ms, accept, handoff_id, doc_sha):
    key = sha256(canonical([opp["opportunity_id"], snapshot, doc_sha]))
    mhash = manifest_hash(ctx.store)
    job = {
        "schema_version": 1, "job_id": content_id("job", key), "idempotency_key": key, "status": "draft", "action": "create",
        "opportunity_id": opp["opportunity_id"], "created_at": f"{ctx.as_of.isoformat()}T00:00:00Z",  # as_of, not the clock: replay must match
        "created_by": "keelwater-signal-engine",
        "evidence": {"insight_ids": snapshot, "run_manifest_hash": mhash, "intent_doc": {"handoff_id": handoff_id, "sha256": doc_sha}},
        "problem_statement": out["problem_statement"], "users_affected": users_affected(ctx.store, ms),
        "acceptance_criteria": [{"id": f"AC{i}", **c} for i, c in enumerate(out["acceptance_criteria"], 1)],
        # shortcut: baseline is the member count at hand-off and the target is 0 post-ship mentions; upgrade to a Metabase question per squad.
        "outcome_metric": {"name": out["metric_name"], "definition": out["metric_definition"],
                           "baseline": {"value": len(snapshot), "unit": "insights", "as_of": ctx.as_of.isoformat()}, "target": 0,
                           "window_days": 30,
                           "query": {"kind": "sql", "ref": "SELECT count(*) FROM opportunity_insight WHERE "
                                                           f"opportunity_id = '{opp['opportunity_id']}' AND post_ship = 1"}},
        "constraints": out["constraints"], "non_goals": out["non_goals"], "data_classification": "confidential",
        # trace.run_id is the run-input hash prefix: a random run id would change the output hash on every replay.
        "trace": {"opportunity_id": opp["opportunity_id"], "handoff_id": handoff_id, "run_id": mhash[:16]},
    }
    if accept:
        job["evidence"]["snapshot_at"] = accept["at"]
        job["gate_approvals"] = [{"gate": "opportunity_accepted", "actor": accept["actor"], "role": "pm", "approved_at": accept["at"]}]
    return job


def draft(ctx, opp, preview=False):
    """Draft and store one handoff. A real draft needs status accepted and, if valid, moves it to intent_drafted."""
    store = ctx.store
    oid = opp["opportunity_id"]
    if not preview and opp["status"] != "accepted":
        raise ValueError(f"{oid} is {opp['status']}, not accepted; a person must accept it first (or use --preview)")
    accept = None if preview else accept_event(store, oid)
    snapshot = list(accept["details_json"].get("evidence_snapshot", [])) if accept else []
    ms = [m for m in members(store, oid) if not snapshot or m["insight_id"] in snapshot]
    snapshot = snapshot or [m["insight_id"] for m in ms]
    out, fails = draft_intent(ctx, opp, ms)
    handoff_id = content_id("handoff", oid, snapshot)
    doc = out["intent_doc_md"]
    job = build_job(ctx, opp, out, snapshot, ms, accept, handoff_id, sha256(doc))
    errors = [f"citation {f['rule']}: {f['detail']}" for f in fails] + deidentify_errors(job, store) + schema_errors(job)
    row = Handoff(handoff_id=handoff_id, opportunity_id=oid, intent_doc_md=doc, factory_job_json=job, evidence_snapshot=snapshot,
                  manifest_hash=job["evidence"]["run_manifest_hash"], errors_json=errors)
    store.insert("handoff", row, replace=True)
    if not errors and not preview:
        transition(store, oid, "intent_drafted", "keelwater-signal-engine", "system", {"handoff_id": handoff_id})
    return row


def submit(store, handoff_id, approvals):
    """Trio sign-off (Gate 2): add the approvals, mark the job submitted and re-validate. Returns the error list."""
    (h,) = store.select("handoff", {"handoff_id": handoff_id})
    job = dict(h["factory_job_json"], status="submitted")
    job["gate_approvals"] = [*job.get("gate_approvals", []), *approvals]
    errors = deidentify_errors(job, store) + schema_errors(job)
    if errors:
        store.update("handoff", {"handoff_id": handoff_id}, {"errors_json": errors})
    else:
        store.update("handoff", {"handoff_id": handoff_id}, {"factory_job_json": job, "status": "approved", "errors_json": []})
    return errors


def pending(store):
    """Accepted opportunities with no valid handoff yet (an invalid draft is redrafted on the next run)."""
    done = {h["opportunity_id"] for h in store.select("handoff") if not h["errors_json"]}
    return [o for o in store.select("opportunity", {"status": "accepted"}, order_by="opportunity_id") if o["opportunity_id"] not in done]


def run(ctx):
    ctx.gateway.map(lambda opp: draft(ctx, opp), pending(ctx.store))


def main(argv):
    from .pipeline import RunContext
    p = argparse.ArgumentParser(prog="keelwater handoff", description="Draft the intent doc and factory job for an accepted opportunity")
    p.add_argument("opportunity_id")
    p.add_argument("--preview", action="store_true", help="draft for a proposed opportunity; its status stays unchanged")
    p.add_argument("--profile", choices=["replay", "demo", "aws", "self-hosted"], default="replay")
    p.add_argument("--as-of", default="03/11/2026")
    p.add_argument("--db", default=".local/keelwater.sqlite")
    p.add_argument("--cache-dir", default="fixtures/llm_cache")
    p.add_argument("--max-usd", type=float, default=0.10)
    a = p.parse_args(argv)
    store = Store(a.db).init()
    rows = store.select("opportunity", {"opportunity_id": a.opportunity_id})
    if not rows:
        print(f"unknown opportunity {a.opportunity_id}")
        return 2
    run_id = uuid.uuid4().hex[:16]
    ctx = RunContext(store, Gateway(store, a.profile, a.cache_dir, run_id, a.max_usd), run_id, datetime.strptime(a.as_of, "%d/%m/%Y").date(),
                     Path("."), 42, "all", a.profile, Path("reports"), {}, a)
    try:
        h = draft(ctx, rows[0], a.preview)
    except (ValueError, GatewayError) as e:
        print(f"handoff failed: {e}")
        return 1
    print(f"handoff {h.handoff_id}: {'valid' if not h.errors_json else 'invalid'}")
    for e in h.errors_json:
        print(f"  {e}")
    return 0 if not h.errors_json else 1
