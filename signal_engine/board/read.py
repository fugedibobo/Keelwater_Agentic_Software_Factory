"""Read functions over the store, shared by the API and the static renderer (docs/signal-board.md sections 3 to 9)."""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator
from markupsafe import Markup, escape

from .. import config
from ..store import canonical, sha256

JUDGES = ("faithfulness", "signal", "duplicate")
PAGE = 100
RULE_GROUP = {"quotes": "quotes", "cited_ids": "citations", "uncited_claims": "citations", "citation_spread": "citations",
              "numbers": "numbers", "customer_names": "names"}
PAST_DRAFT = ("intent_drafted", "in_factory", "shipped", "enabled", "measured")
# shortcut: drift floors are fixed constants here, move to config/ranking.yaml when the PMs tune them.
FLOORS = {"agreement": (0.75, "min"), "miss_rate": (0.10, "max"), "acceptance": (0.20, "min")}


def q(store, sql, *args):
    with store.lock:
        rows = store.db.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def jload(v, default=None):
    try:
        return json.loads(v) if isinstance(v, str) else (v if v is not None else default)
    except ValueError:
        return default


def uk(d):
    """DD/MM/YYYY from an ISO date or datetime string."""
    return f"{str(d)[8:10]}/{str(d)[5:7]}/{str(d)[:4]}" if d else ""


def mmss(ms):
    s = int((ms or 0) // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def md(text):
    """Tiny Markdown to HTML (headings, bullets, paragraphs), escaped. shortcut: no inline markup, upgrade with a library if drafts need it."""
    out, items = [], []

    def flush():
        if items:
            out.append("<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>")
            items.clear()
    for block in (text or "").split("\n"):
        line = block.rstrip()
        m = re.match(r"(#{1,4})\s+(.*)", line)
        if line.startswith("- "):
            items.append(line[2:])
            continue
        flush()
        if m:
            n = min(6, len(m.group(1)) + 4)  # sits under the handoff's own h4
            out.append(f"<h{n}>{escape(m.group(2))}</h{n}>")
        elif line:
            out.append(f"<p>{escape(line)}</p>")
    flush()
    return Markup("".join(out))


# ---- runs and header -----------------------------------------------------------------------------------------

def runs(store):
    return q(store, "SELECT * FROM run ORDER BY started_at, rowid")


def latest_run(store):
    r = runs(store)
    return r[-1] if r else None


def run_info(store):
    run = latest_run(store)
    if run:
        for k in ("prompt_versions", "model_ids", "manifest_json"):
            run[k] = jload(run[k], {})
    return run


def judge_states(store):
    latest = {}
    for r in q(store, "SELECT * FROM judge_version ORDER BY rowid"):
        latest[r["judge"]] = r
    return latest


def header(store):
    js = judge_states(store)
    trusted = sum(1 for j in js.values() if j["state"] == "trusted")
    states = sorted({j["state"] for j in js.values() if j["state"] != "trusted"})
    return {"run": run_info(store), "trusted": trusted, "judges_total": len(JUDGES), "judge_note": ", ".join(states)}


# ---- opportunities -------------------------------------------------------------------------------------------

def _ranks(store, run_id):
    rows = q(store, "SELECT opportunity_id FROM score WHERE run_id=? ORDER BY total DESC, opportunity_id", run_id)
    return {r["opportunity_id"]: i + 1 for i, r in enumerate(rows)}


def since_last_week(store):
    run = latest_run(store)
    if not run:
        return {"new": [], "up": [], "down": [], "post_ship": [], "decided": [], "new_evidence": 0, "previous_run": None}
    rs = runs(store)
    prev = rs[-2] if len(rs) > 1 else None
    as_of = date.fromisoformat(run["as_of"][:10])
    week_ago = (as_of - timedelta(days=7)).isoformat()
    ranks, prev_ranks = _ranks(store, run["run_id"]), (_ranks(store, prev["run_id"]) if prev else {})
    opps = q(store, "SELECT opportunity_id, first_seen_as_of FROM opportunity")
    new = [i for i in ranks if i not in prev_ranks] if prev else [o["opportunity_id"] for o in opps if o["first_seen_as_of"][:10] >= week_ago]
    up = [i for i, r in ranks.items() if i in prev_ranks and prev_ranks[i] - r >= 2]
    down = [i for i, r in ranks.items() if i in prev_ranks and r - prev_ranks[i] >= 2]
    post = sorted({r["opportunity_id"] for r in q(store, "SELECT opportunity_id FROM opportunity_insight WHERE post_ship=1")})
    since = (prev or run)["started_at"]
    decided = sorted({a["target_id"] for a in q(store, "SELECT target_id FROM annotation WHERE action!='undo' AND created_at>=?", since)})
    evidence = q(store, "SELECT COUNT(*) n FROM insight i JOIN snippet s ON s.snippet_id=i.snippet_id JOIN raw_record r ON r.raw_id=s.raw_id "
                        "WHERE r.occurred_at>=?", week_ago)[0]["n"]
    return {"new": new, "up": up, "down": down, "post_ship": post, "decided": decided, "new_evidence": evidence,
            "previous_run": prev["run_id"] if prev else None}


def checks_for(brief):
    """Deterministic check line: ok or FAILED with the rule and the mismatch."""
    if not brief:
        return None
    failed = {}
    for f in jload(brief["check_failures_json"], []):
        rule, detail = (f.get("rule", "check"), f.get("detail", "")) if isinstance(f, dict) else ("check", str(f))
        failed.setdefault(RULE_GROUP.get(rule, rule), []).append(f"{rule}: {detail}")
    names = list(dict.fromkeys(list(RULE_GROUP.values()) + list(failed)))
    return [{"name": n, "ok": n not in failed, "detail": "; ".join(failed.get(n, []))} for n in names]


def judge_line(j, states):
    jv = states.get(j["judge"], {})
    state = jv.get("state", "uncalibrated")
    note = {"calibrating": f"calibrating: {jv.get('n_pass', 0)} of 50 pass, {jv.get('n_fail', 0)} of 50 fail",
            "uncalibrated": "not yet calibrated", "trusted": "trusted",
            "revoked": f"trust revoked {uk(jv.get('state_changed_at'))}"}[state]
    return {"judge": j["judge"], "verdict": j["verdict"], "critique": j["critique"], "state": state, "note": note}


def _chips(sc):
    chips = [(n, sc[k], k) for n, k in (("breadth", "breadth"), ("severity", "severity"), ("value", "value"), ("corroboration", "corroboration"), ("recency", "recency"))]
    if abs(sc["renewal"] - 1) > 1e-9:
        chips.append(("renewal", f"x{sc['renewal']:g}", "renewal"))
    if abs(sc["roadmap"] - 1) > 1e-9:
        chips.append(("on roadmap", f"x{sc['roadmap']:g}", "roadmap"))
    hints = {"renewal": "x(1 + 0.25 x renewing share of affected ARR)", "roadmap": "x0.5 when on the roadmap"}
    return [{"name": n, "value": v, "hint": hints.get(k, f"{n} factor of the score")} for n, v, k in chips]


def _opp_row(store, o, sc, ranks, prev_ranks, prev_scores, since, states, run):
    oid = o["opportunity_id"]
    brief = (q(store, "SELECT * FROM brief WHERE opportunity_id=? ORDER BY rowid DESC LIMIT 1", oid) or [None])[0]
    js = q(store, "SELECT * FROM judgement WHERE (target_type='opportunity' AND target_id=?) OR (target_type='brief' AND target_id=?) ORDER BY rowid",
           oid, brief["brief_id"] if brief else "")
    accts = q(store, "SELECT i.account_id, a.arr_gbp, a.renewal_date FROM opportunity_insight oi JOIN insight i ON i.insight_id=oi.insight_id "
                     "LEFT JOIN account a ON a.account_id=i.account_id WHERE oi.opportunity_id=?", oid)
    seen = {a["account_id"]: a for a in accts if a["account_id"]}
    as_of = date.fromisoformat(run["as_of"][:10]) if run else date.today()
    renewing = sum(1 for a in seen.values() if a["renewal_date"] and as_of <= date.fromisoformat(a["renewal_date"][:10]) <= as_of + timedelta(days=90))
    rank, prev = ranks.get(oid), prev_ranks.get(oid)
    is_new = oid in since["new"]
    row = dict(o, rank=rank, score=sc["total"] if sc else None, chips=_chips(sc) if sc else [],
               trend={"new": is_new, "delta": (prev - rank) if (prev and rank) else 0,
                      "score_delta": round(sc["total"] - prev_scores[oid], 2) if sc and oid in prev_scores else None},
               checks=checks_for(brief), brief_failed=bool(brief and brief["check_status"] == "failed_checks"),
               judges=[judge_line(j, states) for j in js],
               accounts_n=len(seen), arr_gbp=sum(a["arr_gbp"] or 0 for a in seen.values()), renewing_n=renewing,
               flags=" ".join(n for n, ids in (("new", since["new"]), ("up", since["up"]), ("down", since["down"]), ("postship", since["post_ship"]),
                                               ("decided", since["decided"])) if oid in ids))
    return row


def opportunities(store, status=None, bucket=None, squad=None):
    """Ranked list for the latest run with chips, trend and check line."""
    run = latest_run(store)
    if not run:
        return []
    rs = runs(store)
    prev = rs[-2] if len(rs) > 1 else None
    ranks, prev_ranks = _ranks(store, run["run_id"]), (_ranks(store, prev["run_id"]) if prev else {})
    scores = {s["opportunity_id"]: s for s in q(store, "SELECT * FROM score WHERE run_id=?", run["run_id"])}
    prev_scores = {s["opportunity_id"]: s["total"] for s in q(store, "SELECT * FROM score WHERE run_id=?", prev["run_id"])} if prev else {}
    since, states = since_last_week(store), judge_states(store)
    out = []
    for o in q(store, "SELECT * FROM opportunity"):
        if (status and o["status"] != status) or (bucket and o["bucket"] != bucket) or (squad and o["squad"] != squad):
            continue
        out.append(_opp_row(store, o, scores.get(o["opportunity_id"]), ranks, prev_ranks, prev_scores, since, states, run))
    return sorted(out, key=lambda r: (r["rank"] is None, r["rank"] or 0, r["opportunity_id"]))


def evidence_ref(r):
    src, sid = r["source"], r["source_id"]
    payload = jload(r["payload_json"], {}) or {}
    if src == "gong":
        return f"Gong call {sid}, {mmss(r['start_ms'])}"
    if src == "intercom":
        return f"Intercom conversation {sid}"
    if src == "fireflies":
        return f"Fireflies transcript {sid}, sentence {payload.get('sentence_index', '?') if isinstance(payload, dict) else '?'}"
    if src == "fullstory":
        return f"FullStory session {sid}, window {mmss(r['start_ms'])} to {mmss(r['end_ms'])}"
    return f"{src} {sid}"


def opportunity(store, oid, listing=None):
    """Drill-down: brief, evidence, accounts, checks, judgements, history. None when unknown."""
    rows = [r for r in (listing if listing is not None else opportunities(store)) if r["opportunity_id"] == oid]
    if not rows:
        return None
    o = rows[0]
    brief = (q(store, "SELECT * FROM brief WHERE opportunity_id=? ORDER BY rowid DESC LIMIT 1", oid) or [None])[0]
    ev = q(store, "SELECT i.insight_id, i.quote, i.quote_match, i.quote_span_start s0, i.quote_span_end s1, i.account_id, i.account_status, "
                  "sn.text, sn.context_text, sn.start_ms, sn.end_ms, r.raw_id, r.source, r.source_id, r.payload_json, oi.post_ship "
                  "FROM opportunity_insight oi JOIN insight i ON i.insight_id=oi.insight_id JOIN snippet sn ON sn.snippet_id=i.snippet_id "
                  "JOIN raw_record r ON r.raw_id=sn.raw_id WHERE oi.opportunity_id=? ORDER BY i.insight_id", oid)
    evidence = []
    for e in ev:
        if e["quote_match"] == "failed":  # unmatched quotes never reach the page
            continue
        a, b = (e["s0"], e["s1"]) if e["s0"] is not None else ((e["text"].find(e["quote"]),) * 2)
        if e["s0"] is None:
            b = a + len(e["quote"])
        evidence.append(dict(insight_id=e["insight_id"], before=e["text"][:a], match=e["text"][a:b], after=e["text"][b:], context=e["context_text"],
                             ref=evidence_ref(e), raw_id=e["raw_id"], post_ship=bool(e["post_ship"]), match_kind=e["quote_match"]))
    accts = {}
    unresolved = 0
    for e in ev:
        if not e["account_id"] or e["account_status"] not in (None, "resolved"):
            unresolved += 1
            continue
        accts[e["account_id"]] = accts.get(e["account_id"], 0) + 1
    accounts = []
    for aid, n in accts.items():
        a = (q(store, "SELECT * FROM account WHERE account_id=?", aid) or [None])[0]
        accounts.append(dict(account_id=aid, name=a["name"] if a else None, arr_gbp=a["arr_gbp"] if a else None, tier=a["tier"] if a else None,
                             renewal=uk(a["renewal_date"]) if a else "", insights=n, in_hubspot=bool(a)))
    hist = q(store, "SELECT a.action, a.actor, a.reason_code, a.note, a.created_at FROM annotation a WHERE a.target_id=? ORDER BY a.rowid", oid)
    return dict(o, brief=brief, evidence=evidence, post_ship_evidence=[e for e in evidence if e["post_ship"]],
                evidence_main=[e for e in evidence if not e["post_ship"]], accounts=accounts, unresolved=unresolved, history=hist,
                tag_disputed=o["tag"] != "none" and o["tag_state"] == "proposed" and any(j["judge"] == "duplicate" and j["verdict"] == "fail" for j in o["judges"]))


def tag_queue(store):
    return [o for o in opportunities(store) if o["tag"] != "none" and o["tag_state"] == "proposed"
            and any(j["judge"] == "duplicate" and j["verdict"] == "fail" for j in o["judges"])]


def raw_record(store, raw_id):
    r = (q(store, "SELECT * FROM raw_record WHERE raw_id=?", raw_id) or [None])[0]
    if r:
        r["payload_json"] = jload(r["payload_json"], {})
    return r


# ---- labels --------------------------------------------------------------------------------------------------

def label_queue(store, actor=None):
    """This week's blind sample: briefs of the latest run per judge, and the noise-audit items. Judge verdicts are never included."""
    run = latest_run(store)
    if not run:
        return {"briefs": [], "noise": []}
    done = {(l["target_type"], l["target_id"], l["judge"]) for l in (q(store, "SELECT * FROM label WHERE actor=?", actor) if actor else q(store, "SELECT * FROM label"))}
    briefs = [dict(target_type="brief", target_id=b["brief_id"], title=b["title"], body_md=b["body_md"], judges=[j for j in JUDGES if ("brief", b["brief_id"], j) not in done and j != "duplicate"])
              for b in q(store, "SELECT b.brief_id, b.body_md, o.title FROM brief b JOIN opportunity o ON o.opportunity_id=b.opportunity_id WHERE b.run_id=?", run["run_id"])]
    return {"briefs": [b for b in briefs if b["judges"]], "noise": [n for n in noise_items(store, run) if ("noise_audit", n["snippet_id"], "signal") not in done]}


def noise_items(store, run=None):
    run = run or latest_run(store)
    if not run:
        return []
    rows = q(store, "SELECT t.snippet_id, t.is_signal_p, t.audit_weight, s.text FROM triage t JOIN snippet s ON s.snippet_id=t.snippet_id "
                    "WHERE t.run_id=? AND t.decision='drop' AND t.audit_weight IS NOT NULL ORDER BY t.is_signal_p DESC, t.snippet_id LIMIT 40", run["run_id"])
    labels = {l["target_id"]: l for l in q(store, "SELECT * FROM label WHERE target_type='noise_audit' ORDER BY rowid")}
    return [dict(r, label=("missed signal" if labels[r["snippet_id"]]["verdict"] == "pass" else "noise") if r["snippet_id"] in labels else None) for r in rows]


def judge_critique(store, target_type, target_id, judge):
    """Revealed only after the label is saved."""
    return (q(store, "SELECT verdict, critique FROM judgement WHERE target_type=? AND target_id=? AND judge=? ORDER BY rowid DESC LIMIT 1",
              target_type, target_id, judge) or [None])[0]


# ---- pipeline ------------------------------------------------------------------------------------------------

def _pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))] if vals else None


def pipeline(store):
    run = run_info(store)
    if not run:
        return None
    rid = run["run_id"]
    funnel = []
    for src in [r["source"] for r in q(store, "SELECT DISTINCT source FROM raw_record ORDER BY source")]:
        base = "FROM snippet s JOIN raw_record r ON r.raw_id=s.raw_id WHERE r.source=?"
        dec = {d["decision"]: d["n"] for d in q(store, f"SELECT t.decision, COUNT(*) n FROM triage t JOIN snippet s ON s.snippet_id=t.snippet_id JOIN raw_record r ON r.raw_id=s.raw_id WHERE t.run_id=? AND r.source=? GROUP BY t.decision", rid, src)}
        opps = q(store, "SELECT DISTINCT oi.opportunity_id FROM opportunity_insight oi JOIN insight i ON i.insight_id=oi.insight_id JOIN snippet s ON s.snippet_id=i.snippet_id "
                        "JOIN raw_record r ON r.raw_id=s.raw_id WHERE r.source=?", src)
        briefs = q(store, "SELECT COUNT(DISTINCT b.opportunity_id) n FROM brief b WHERE b.run_id=? AND b.opportunity_id IN (SELECT oi.opportunity_id FROM opportunity_insight oi "
                          "JOIN insight i ON i.insight_id=oi.insight_id JOIN snippet s ON s.snippet_id=i.snippet_id JOIN raw_record r ON r.raw_id=s.raw_id WHERE r.source=?)", rid, src)[0]["n"]
        funnel.append(dict(source=src, raw=q(store, "SELECT COUNT(*) n FROM raw_record WHERE source=?", src)[0]["n"],
                           snippets=q(store, "SELECT COUNT(*) n " + base, src)[0]["n"], kept=dec.get("keep", 0), dropped=dec.get("drop", 0),
                           low_confidence=dec.get("low_confidence", 0), untriaged=dec.get("untriaged", 0),
                           insights=q(store, "SELECT COUNT(*) n FROM insight i JOIN snippet s ON s.snippet_id=i.snippet_id JOIN raw_record r ON r.raw_id=s.raw_id "
                                             "WHERE i.run_id=? AND i.quote_match!='failed' AND r.source=?", rid, src)[0]["n"], opps=len(opps), briefs=briefs))
    cols = ("raw", "snippets", "kept", "dropped", "low_confidence", "untriaged", "insights")
    total = {c: sum(f[c] for f in funnel) for c in cols}
    total["opps"] = q(store, "SELECT COUNT(DISTINCT opportunity_id) n FROM opportunity_insight")[0]["n"]
    total["briefs"] = q(store, "SELECT COUNT(DISTINCT opportunity_id) n FROM brief WHERE run_id=?", rid)[0]["n"]
    stages = []
    calls = q(store, "SELECT * FROM model_call WHERE run_id=? ORDER BY rowid", rid)
    for key in dict.fromkeys((c["stage"], c["model"], c["profile"]) for c in calls):
        cs = [c for c in calls if (c["stage"], c["model"], c["profile"]) == key]
        stages.append(dict(stage=key[0], model=key[1], profile=key[2], calls=len(cs), p50=_pct([c["latency_ms"] for c in cs], .5),
                           p95=_pct([c["latency_ms"] for c in cs], .95), tokens_in=sum(c["tokens_in"] for c in cs), tokens_out=sum(c["tokens_out"] for c in cs),
                           cost=sum(c["cost_usd"] for c in cs), cached=sum(c["cached"] for c in cs) / len(cs)))
    backends = {}
    for t in q(store, "SELECT backend, decision, COUNT(*) n FROM triage WHERE run_id=? GROUP BY backend, decision", rid):
        b = backends.setdefault(t["backend"], {"total": 0})
        b[t["decision"]] = t["n"]
        b["total"] += t["n"]
    n_all = sum(b["total"] for b in backends.values()) or 1
    fallback = sum(b["total"] for k, b in backends.items() if "fallback" in k) / n_all
    manifest = {k: run[k] for k in ("run_id", "profile", "seed", "batch", "as_of", "status", "data_hash", "config_hash", "prompt_versions", "model_ids")}
    manifest["manifest"] = run["manifest_json"]
    cap = (run["manifest_json"] or {}).get("max_usd")
    return dict(run=run, funnel=funnel, total=total, stages=stages, backends=backends, fallback_share=fallback, fallback_flag=fallback > 0.2,
                spend=sum(c["cost"] for c in stages), cap=cap, manifest_text=json.dumps(manifest, indent=2, sort_keys=True, default=str))


# ---- evals ---------------------------------------------------------------------------------------------------

def newest_report(reports_dir, suite):
    files = sorted(Path(reports_dir).glob(f"{suite}-*.json"), key=lambda p: (p.stat().st_mtime, p.name)) if reports_dir and Path(reports_dir).is_dir() else []
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def _week(ts):
    d = datetime.fromisoformat(str(ts)[:19])
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _series(pairs, key):
    """pairs: (week, numerator, denominator). Returns the series, a polyline for the latest points and the alert."""
    by = {}
    for wk, n, d in pairs:
        a = by.setdefault(wk, [0.0, 0.0])
        a[0] += n
        a[1] += d
    pts = [(wk, a[0] / a[1]) for wk, a in sorted(by.items()) if a[1]]
    floor, kind = FLOORS[key]
    last = pts[-1][1] if pts else None
    alert = last is not None and ((last < floor) if kind == "min" else (last > floor))
    poly = " ".join(f"{4 + i * (112 / max(1, len(pts) - 1)):.1f},{28 - v * 24:.1f}" for i, (_, v) in enumerate(pts)) if len(pts) > 1 else ""
    return dict(key=key, points=pts, last=last, floor=floor, kind=kind, alert=alert, polyline=poly)


def drift(store):
    judged = {(j["target_id"], j["judge"]): j["verdict"] for j in q(store, "SELECT * FROM judgement WHERE target_type='brief'")}
    labels = q(store, "SELECT * FROM label WHERE blind=1 ORDER BY created_at")
    agree = [(_week(l["created_at"]), float(judged[(l["target_id"], l["judge"])] == l["verdict"]), 1) for l in labels if (l["target_id"], l["judge"]) in judged]
    miss = [(_week(l["created_at"]), l["weight"] * (l["verdict"] == "pass"), l["weight"]) for l in labels if l["target_type"] == "noise_audit"]
    ann = q(store, "SELECT action, created_at FROM annotation WHERE action IN ('accept','merge','reject','park')")
    acc = [(_week(a["created_at"]), float(a["action"] in ("accept", "merge")), 1) for a in ann]
    return [_series(agree, "agreement"), _series(miss, "miss_rate"), _series(acc, "acceptance")]


def evals(store, reports_dir=None):
    reports = {s: newest_report(reports_dir, s) for s in ("ground-truth", "holdout", "stability", "judges")}
    gt, ho = reports["ground-truth"], reports["holdout"]
    keys = list(dict.fromkeys(list((gt or {}).get("metrics", {})) + list((ho or {}).get("metrics", {}))))
    rows = [dict(metric=k, seed42=(gt or {}).get("metrics", {}).get(k), seed43=(ho or {}).get("metrics", {}).get(k)) for k in keys]
    items = noise_items(store)
    done = [i for i in items if i["label"]]
    w = sum(i["audit_weight"] for i in done)
    miss = sum(i["audit_weight"] for i in done if i["label"] == "missed signal") / w if w else None
    return dict(available=any(reports.values()), reports=reports, ground_truth=rows, stability=reports["stability"], judge_report=reports["judges"],
                judges=list(judge_states(store).values()), noise=items, noise_labelled=len(done), miss_rate=miss, drift=drift(store))


# ---- handoffs ------------------------------------------------------------------------------------------------

def validate_job(job):
    schema = json.loads(config.FACTORY_JOB_SCHEMA.read_text(encoding="utf-8"))
    errs = sorted(Draft202012Validator(schema).iter_errors(job), key=lambda e: list(map(str, e.path)))
    return [f"{'/'.join(map(str, e.path)) or '(job)'}: {e.message}"[:300] for e in errs[:10]]


def handoffs(store):
    out = []
    for o in q(store, "SELECT * FROM opportunity WHERE status IN ('accepted','intent_drafted','in_factory','shipped','enabled','measured') ORDER BY rowid"):
        h = (q(store, "SELECT * FROM handoff WHERE opportunity_id=? ORDER BY rowid DESC LIMIT 1", o["opportunity_id"]) or [None])[0]
        if h:
            h["factory_job"] = jload(h["factory_job_json"])
            h["errors"] = validate_job(h["factory_job"]) if h["factory_job"] is not None else ["no factory job drafted"]
            h["job_text"] = json.dumps(h["factory_job"], indent=2, sort_keys=True) if h["factory_job"] is not None else ""
            h["preview"] = o["status"] not in PAST_DRAFT
        out.append(dict(opportunity=o, handoff=h))
    return out


def outtakes(store, kind=None):
    return q(store, "SELECT * FROM outtake" + (" WHERE kind=?" if kind else "") + " ORDER BY rowid", *([kind] if kind else []))


# ---- audit ---------------------------------------------------------------------------------------------------

def chain_status(store):
    """Re-compute the hash chain: the last verified event, or the first break (mirrors Store.verify_audit_chain)."""
    prev, n = "", 0
    for r in q(store, "SELECT * FROM audit_event ORDER BY rowid"):
        ev = dict(r)
        digest = ev.pop("hash")
        if ev["prev_hash"] != prev or sha256(prev + canonical(ev)) != digest:
            return dict(ok=False, verified=n, break_at=r["event_id"], text=f"BROKEN at event {n + 1} ({r['event_id']})")
        prev, n = digest, n + 1
    return dict(ok=True, verified=n, break_at=None, text=f"verified to event {n}" if n else "no events yet")


def audit(store, table="audit_event", run=None, stage=None, model=None, actor=None, frm=None, to=None, cached=None, page=1):
    if table == "model_call":
        sql, args = "SELECT * FROM model_call WHERE 1=1", []
        for col, v in (("run_id", run), ("stage", stage), ("model", model)):
            if v:
                sql, args = sql + f" AND {col}=?", args + [v]
        if cached:
            sql += " AND cached=1"
    else:
        sql, args = "SELECT * FROM audit_event WHERE 1=1", []
        for cond, v in (("actor=?", actor), ("at>=?", frm), ("at<=?", to and to + "T99")):
            if v:
                sql, args = sql + " AND " + cond, args + [v]
    rows = q(store, sql + " ORDER BY rowid", *args)
    page = max(1, int(page or 1))
    return dict(table=table, total=len(rows), page=page, pages=max(1, -(-len(rows) // PAGE)), rows=rows[(page - 1) * PAGE:page * PAGE], chain=chain_status(store))


def audit_both(store):
    """Both tables, first page each, for the board page."""
    return {"audit_event": audit(store, "audit_event"), "model_call": audit(store, "model_call")}


def squads():
    return list(config.squads())


def buckets():
    return list(config.bucket_ids())
