"""Stage 7: one cited brief per top opportunity. Code computes every number; the writer copies them."""

import json
from datetime import date, timedelta

from . import citations
from .contracts import Brief
from .gateway import call_id_for
from .prompts import load_prompt
from .store import canonical, content_id, sha256, transition

RENEWAL_DAYS = 90


def members(store, opportunity_id):
    """Member insights with account name, route and date, in insight_id order."""
    with store.lock:
        rows = store.db.execute(
            "SELECT i.insight_id, i.quote, i.quote_match, i.account_id, a.name AS account, r.route, r.occurred_at AS date "
            "FROM opportunity_insight oi JOIN insight i ON i.insight_id=oi.insight_id "
            "LEFT JOIN account a ON a.account_id=i.account_id LEFT JOIN snippet s ON s.snippet_id=i.snippet_id "
            "LEFT JOIN raw_record r ON r.raw_id=s.raw_id WHERE oi.opportunity_id=? ORDER BY i.insight_id", (opportunity_id,)).fetchall()
    return [dict(r, verified=r["quote_match"] != "failed") for r in rows]


def fact_sheet(store, opportunity_id, as_of):
    """Accounts, ARR, mentions, routes and renewals computed from the store, so the writer never calculates."""
    ms = members(store, opportunity_id)
    accounts = {}
    for m in ms:
        if m["account_id"]:
            with store.lock:
                row = store.db.execute(
                    "SELECT name, arr_gbp, renewal_date FROM account WHERE account_id=?", (m["account_id"],)).fetchone()
            a = accounts.setdefault(m["account_id"], {"mentions": 0, **dict(row or {})})
            a["mentions"] += 1
    by_route = {}
    for m in ms:
        if m["route"]:
            by_route[m["route"]] = by_route.get(m["route"], 0) + 1
    horizon = as_of + timedelta(days=RENEWAL_DAYS)
    renewing = [a for a in accounts.values() if a.get("renewal_date") and as_of <= date.fromisoformat(a["renewal_date"][:10]) <= horizon]
    return {"as_of": as_of.isoformat(), "accounts_n": len(accounts), "mentions_n": len(ms), "routes_n": len(by_route),
            "mentions_by_route": by_route, "arr_total_gbp": sum(a.get("arr_gbp") or 0 for a in accounts.values()),
            "renewals_90d_n": len(renewing),
            "accounts": [{"name": a.get("name"), "arr_gbp": a.get("arr_gbp"), "renewal_date": a.get("renewal_date"),
                          "mentions": a["mentions"]} for a in accounts.values()]}


def render(prompt, **parts):
    for k, v in parts.items():
        prompt = prompt.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
    return prompt


def chat_with_id(gw, stage, prompt, target_type, target_id, prompt_version, schema=None):
    """gateway.chat plus the call_id of that exact request."""
    messages = [{"role": "user", "content": prompt}]
    body = gw.chat_request(stage, messages, schema)
    out = gw.chat(stage, messages, target_type=target_type, target_id=target_id, prompt_version=prompt_version, schema=schema)
    return out, call_id_for(stage, sha256(canonical(body)), target_type, target_id)


def write_brief(ctx, opp):
    store, gw = ctx.store, ctx.gateway
    body, pv = load_prompt("brief", "writer")
    ms = members(store, opp["opportunity_id"])
    by_id = {m["insight_id"]: m for m in ms}
    facts = fact_sheet(store, opp["opportunity_id"], ctx.as_of)
    names = {r["account_id"]: r["name"] for r in store.select("account")}
    prompt = render(body, opportunity={"title": opp["title"], "problem_statement": opp["problem_statement"]}, fact_sheet=facts,
                    insights=[{"id": m["insight_id"], "quote": m["quote"], "account": m["account"], "route": m["route"],
                               "date": m["date"]} for m in ms])
    out, call_id = chat_with_id(gw, "brief", prompt, "opportunity", opp["opportunity_id"], pv)
    fails = citations.check(out["body_md"], by_id, facts, names)
    if fails:  # one retry with the failure list
        retry = (prompt + "\n<failed_checks>\nYour previous draft failed these checks. Fix them and write the brief again.\n"
                 + "\n".join(f"- {f['rule']}: {f['detail']}" for f in fails) + "\n</failed_checks>\n<previous_draft>\n"
                 + out["body_md"] + "\n</previous_draft>")
        out, call_id = chat_with_id(gw, "brief", retry, "opportunity", opp["opportunity_id"], pv)
        fails = citations.check(out["body_md"], by_id, facts, names)
    brief = Brief(brief_id=content_id("brief", opp["opportunity_id"]), opportunity_id=opp["opportunity_id"], run_id=ctx.run_id,
                  call_id=call_id, body_md=out["body_md"], citations_json=citations.cited_ids(out["body_md"]),
                  check_status="failed_checks" if fails else "passed", check_failures_json=fails, prompt_version=pv,
                  model=gw.model_ids()["brief"])
    store.insert("brief", brief, replace=True)
    transition(store, opp["opportunity_id"], "proposed", "brief", "system", {"brief_id": brief.brief_id, "check_status": brief.check_status})


def top_opportunities(ctx):
    with ctx.store.lock:
        rows = ctx.store.db.execute(
            "SELECT o.* FROM opportunity o JOIN score s ON s.opportunity_id=o.opportunity_id AND s.run_id=? "
            "WHERE o.status='new' AND o.tag='none' ORDER BY s.total DESC, o.opportunity_id LIMIT ?",
            (ctx.run_id, ctx.config["pipeline"]["top_n"])).fetchall()
    return [dict(r) for r in rows]


def run(ctx):
    ctx.gateway.map(lambda opp: write_brief(ctx, opp), top_opportunities(ctx))
