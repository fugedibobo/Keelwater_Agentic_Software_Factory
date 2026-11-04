"""Stage 6: the ranking formula of architecture section 4. Pure code from config/ranking.yaml, never an LLM (ADR-004)."""

import math
import statistics
from datetime import date

from .contracts import Score
from .tag import parse_dt

FACTORS = ("breadth", "severity", "value", "corroboration", "recency", "renewal", "roadmap")


def day(s):
    d = parse_dt(s)
    return d.date() if d else None


def total_of(row):
    return math.prod(row[f] for f in FACTORS)


def factors(members, accounts, cfg, as_of, median, tag):
    """members: dicts with severity, account_id, occurred_at, route. Returns the seven factors, their total and the unresolved count."""
    nominal = cfg["nominal_arr_share"] * median

    def arr(aid):  # prospects have no ARR; an account unknown to the table counts as one
        a = accounts.get(aid)
        return a["arr_gbp"] if a and a["arr_gbp"] is not None else nominal

    accts = sorted({m["account_id"] for m in members if m["account_id"]})
    weights = [arr(m["account_id"]) if m["account_id"] else nominal for m in members]
    affected = sum(arr(a) for a in accts)
    f = {"breadth": math.log(1 + len(accts), cfg["breadth"]["log_base"])}
    # shortcut: zero total weight (no customer ARR anywhere) falls back to a plain mean, upgrade if that case is real
    f["severity"] = (sum(w * m["severity"] for w, m in zip(weights, members)) / sum(weights) if sum(weights)
                     else sum(m["severity"] for m in members) / len(members))
    f["value"] = (max(cfg["value"]["floor"], 1 + math.log(affected / median, cfg["value"]["log_base"]))
                  if affected > 0 and median > 0 else cfg["value"]["floor"])
    routes = len({m["route"] for m in members if m["route"]})
    f["corroboration"] = cfg["corroboration"][min(routes, 3)] if routes else cfg["corroboration"][1]
    win = cfg["recency"]["window_days"]
    recent = sum(1 for m in members if m["day"] and 0 <= (as_of - m["day"]).days <= win)
    f["recency"] = max(cfg["recency"]["floor"], recent / len(members))
    soon = sum(arr(a) for a in accts if accounts.get(a) and accounts[a]["renewal_date"]
               and 0 <= (date.fromisoformat(accounts[a]["renewal_date"]) - as_of).days <= cfg["renewal"]["window_days"])
    f["renewal"] = 1 + cfg["renewal"]["weight"] * (soon / affected if affected else 0)
    f["roadmap"] = cfg["roadmap"]["on_roadmap"] if tag == "on_roadmap" else cfg["roadmap"]["otherwise"]
    f["total"] = total_of(f)
    f["unresolved_insights"] = sum(1 for m in members if not m["account_id"])
    return f


def run(ctx):
    store, cfg = ctx.store, ctx.config["ranking"]
    accounts = {a["account_id"]: a for a in store.select("account")}
    arrs = [a["arr_gbp"] for a in accounts.values() if a["arr_gbp"] is not None]
    median = statistics.median(arrs) if arrs else 0.0
    insights = {i["insight_id"]: i for i in store.select("insight")}
    snippets = {s["snippet_id"]: s["raw_id"] for s in store.select("snippet")}
    raws = {r["raw_id"]: r for r in store.select("raw_record")}
    for o in store.select("opportunity", order_by="opportunity_id"):
        if o["merged_into"] is not None:
            continue
        tag = "none" if o["tag_state"] == "removed" else o["tag"]
        members = []
        for link in store.select("opportunity_insight", {"opportunity_id": o["opportunity_id"]}):
            if tag == "shipped" and not link["post_ship"]:  # a shipped item scores only its post-ship evidence
                continue
            ins = insights[link["insight_id"]]
            raw = raws[snippets[ins["snippet_id"]]]
            members.append({"severity": ins["severity"], "account_id": ins["account_id"], "route": raw["route"],
                            "occurred_at": raw["occurred_at"], "day": day(raw["occurred_at"])})
        if not members:
            continue
        row = factors(members, accounts, cfg, ctx.as_of, median, tag)
        store.insert("score", Score(opportunity_id=o["opportunity_id"], run_id=ctx.run_id, **row), replace=True)
    bad = [s["opportunity_id"] for s in store.select("score", {"run_id": ctx.run_id}) if abs(s["total"] - total_of(s)) > 1e-9]
    if bad:  # evals 3.5: any mismatch fails the run
        raise RuntimeError(f"score.total does not recompute from its factors: {bad}")
