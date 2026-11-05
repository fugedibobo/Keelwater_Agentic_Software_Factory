"""Stage 2, triage: one decision-model call per snippet, one fallback model, gating, stratified noise audit.

Nothing is ever dropped silently: a failed backend gives `untriaged`, which proceeds (ADR-003).
"""

import hashlib
import threading
import time

from . import prompts
from .contracts import SignalType, Triage, TriageOutput
from .gateway import BudgetExceeded, GatewayError, ReplayMiss, call_id_for
from .store import canonical, sha256

STRICT = (BudgetExceeded, ReplayMiss)  # never turned into a fallback or an untriaged row


def gate(p, bucket_conf, th):
    """Architecture section 4 gating bands; th is the backend's thresholds from config/pipeline.yaml."""
    if p <= th["drop_p"]:
        return "drop"
    if p >= th["keep_p"] and bucket_conf >= th["keep_bucket_conf"]:
        return "keep"
    return "low_confidence"


def audit_sample(rows, strata):
    """{snippet_id: audit_weight} over drop rows; picks are first n in sha256(snippet_id) order, weight = stratum size / picked."""
    out = {}
    for s in strata:
        pool = [r for r in rows if r["decision"] == "drop" and r["is_signal_p"] <= s["p_max"] and (r["is_signal_p"] > s["p_min"] or s["p_min"] == 0)]
        pool.sort(key=lambda r: hashlib.sha256(r["snippet_id"].encode("utf-8")).hexdigest())
        picked = pool[:s["n"]]
        for r in picked:
            out[r["snippet_id"]] = len(pool) / len(picked)
    return out


def run(ctx):
    gw, cfg = ctx.gateway, ctx.config["pipeline"]["triage"]
    snippets = ctx.store.select("snippet", order_by="snippet_id")
    taxonomy = ", ".join(f"{b['id']} ({b['name']})" for b in ctx.config["taxonomy"]["buckets"])
    prompt, prompt_version = prompts.load_prompt("triage", "fallback")
    system = prompt.replace("{{buckets}}", taxonomy).replace("{{types}}", ", ".join(t.value for t in SignalType))
    state = {"down": gw.stage_cfg("triage").get("backend") != "clef"}  # a profile without a decision backend uses the fallback model
    lock = threading.Lock()
    misses = [0]

    def decided(stage, sn):
        out = gw.decide(sn["text"], stage=stage, target_type="snippet", target_id=sn["snippet_id"])
        TriageOutput(is_product_signal=out["is_signal_p"], bucket=out["bucket"], bucket_confidence=out["bucket_conf"],
                     severity=out["severity"], signal_type=out["signal_type"])  # a bad bucket or type counts as a failed call
        return out

    def primary(sn):
        with lock:
            if state["down"]:
                return None
        body = gw.decide_request("triage", sn["text"])
        try:
            out = decided("triage", sn)
        except STRICT:
            raise
        except (GatewayError, KeyError, ValueError, TypeError):
            with lock:  # one probe decides whether the primary is down for the whole run
                if not state["down"]:
                    try:
                        gw.probe_one("triage")
                    except GatewayError:
                        state["down"] = True
                        print(f"triage: {gw.stage_cfg('triage')['model']} unavailable, using {gw.stage_cfg('triage_fallback')['model']} for this run")
            return None
        return "clef", out, call_id_for("triage", sha256(canonical(body)), "snippet", sn["snippet_id"])

    def fallback(sn):
        if gw.stage_cfg("triage_fallback").get("backend") == "clef":  # demo: a second decision model, about 50 ms, never a chat LLM
            body = gw.decide_request("triage_fallback", sn["text"])
            try:
                out = decided("triage_fallback", sn)
            except STRICT:
                raise
            except (GatewayError, KeyError, ValueError, TypeError):
                return None
            return "fallback", out, call_id_for("triage_fallback", sha256(canonical(body)), "snippet", sn["snippet_id"])
        messages = [{"role": "system", "content": system}, {"role": "user", "content": sn["text"]}]
        body = gw.chat_request("triage_fallback", messages)
        try:
            o = TriageOutput.model_validate(gw.chat("triage_fallback", messages, target_type="snippet", target_id=sn["snippet_id"],
                                                    prompt_version=prompt_version))
        except STRICT:
            raise
        except (GatewayError, KeyError, ValueError, TypeError):
            return None
        out = {"is_signal_p": o.is_product_signal, "bucket": o.bucket, "bucket_conf": o.bucket_confidence,
               "severity": o.severity, "signal_type": o.signal_type.value}
        return "fallback", out, call_id_for("triage_fallback", sha256(canonical(body)), "snippet", sn["snippet_id"])

    def triage_one(sn):
        t0 = time.perf_counter()
        try:
            got = primary(sn) or fallback(sn)
        except ReplayMiss:
            with lock:
                misses[0] += 1
            got = None  # replay with no recorded answer: untriaged row, counted as a cache miss
        ms = round((time.perf_counter() - t0) * 1000, 2)
        if got is None:  # shortcut: no per-snippet retry beyond the gateway's, a later run retries via the cache miss
            return {"snippet_id": sn["snippet_id"], "run_id": ctx.run_id, "backend": "none", "decision": "untriaged", "latency_ms": ms}
        backend, o, call_id = got
        return {"snippet_id": sn["snippet_id"], "run_id": ctx.run_id, "call_id": call_id, "backend": backend, "latency_ms": ms,
                "is_signal_p": o["is_signal_p"], "bucket": o["bucket"], "bucket_conf": o["bucket_conf"], "severity": o["severity"],
                "signal_type": o["signal_type"], "decision": gate(o["is_signal_p"], o["bucket_conf"], cfg["backends"][backend])}

    rows = gw.map(triage_one, snippets)
    missed = gw.triage_cache_misses = misses[0]
    weights = audit_sample(rows, cfg_strata(ctx))
    for r in rows:
        ctx.store.insert("triage", Triage(**r, audit_weight=weights.get(r["snippet_id"])), replace=True)
    counts = {d: sum(r["decision"] == d for r in rows) for d in ("keep", "drop", "low_confidence", "untriaged")}
    assert sum(counts.values()) == len(snippets), f"triage reconciliation failed: {counts} vs {len(snippets)} snippets"
    print(f"triage: {len(snippets)} snippets = " + " + ".join(f"{v} {k}" for k, v in counts.items()) + f"; audit queue {len(weights)}" + (f"; {missed} not in the replay cache" if missed else ""))
    if rows and counts["untriaged"] / len(rows) > 0.01:
        print(f"triage: ALERT {counts['untriaged']} untriaged is above 1% of the run")
    return counts


def cfg_strata(ctx):
    return ctx.config["pipeline"]["noise_audit"]["strata"]
