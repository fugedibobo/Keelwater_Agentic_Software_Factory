"""Seed a small synthetic store plus eval reports for the Signal Board: `python tests/fixtures/seed_store.py <dir>`.

Writes <dir>/keelwater.sqlite and <dir>/reports/eval/*.json. Two runs, six opportunities, all names synthetic (.example).
"""

import json
import sys
from pathlib import Path

from signal_engine.store import Store, content_id, sha256

R1, R2 = "run-20261027", "run-20261103"
A1, A2 = "2026-10-27", "2026-11-03"
H = "a" * 64


def seed(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s = Store.fresh(out / "keelwater.sqlite")
    ins = s.insert

    for rid, started, as_of, cost in ((R1, "2026-10-27T02:00:00+00:00", A1, 0.05), (R2, "2026-11-03T02:00:00+00:00", A2, 0.12)):
        manifest = dict(profile="replay", seed=42, batch="all", as_of=as_of, data_hash=H, config_hash="b" * 64,
                        config_files={"ranking": "c" * 8}, prompt_versions={"brief": "v1"}, model_ids={"brief": "qwen/qwen3.8-max-0902"})
        ins("run", dict(run_id=rid, started_at=started, as_of=as_of, profile="replay", seed=42, batch="all", data_hash=H,
                        config_hash="b" * 64, prompt_versions={"brief": "v1"}, model_ids={"brief": "qwen/qwen3.8-max-0902"},
                        output_hash="d" * 64, cost_usd=cost, status="done", manifest_json={**manifest, "max_usd": 1.5}))

    accounts = [("acc1", "Pendleford Motor Mutual", 690000, "Strategic", "2026-11-28"), ("acc2", "Harrow Fleet Cover", 410000, "Enterprise", "2027-06-30"),
                ("acc3", "Northgate Home Insurance", 120000, "Growth", "2027-02-01")]
    for a in accounts:
        ins("account", dict(zip(("account_id", "name", "arr_gbp", "tier", "renewal_date"), a)))

    # (opp id, title, bucket, status, squad, first seen, tag, tag_state, score run1, score run2)
    opps = [
        ("o1", "Bulk reassignment of claims", "triage_assignment", "proposed", "intake_claims", A1, "none", None, 4.0, 7.4),
        ("o2", "Audit-trail export is slow", "reporting_mi", "proposed", "insight_reporting", A1, "none", None, 6.5, 5.5),
        ("o3", "Payment approval confusion", "reserves_payments", "accepted", "handling_payments", A1, "none", None, 5.0, 5.8),
        ("o4", "Document upload loses files", "documents_evidence", "shipped", "handling_payments", "2026-09-01", "shipped", "confirmed", 3.0, 3.1),
        ("o5", "Supplier portal login resets", "supplier_network", "proposed", "suppliers_comms", A2, "on_roadmap", "proposed", None, 2.9),
        ("o6", "Letter templates cannot be reused", "customer_comms", "parked", "suppliers_comms", "2026-10-01", "none", None, 2.0, 2.4),
    ]
    for oid, title, bucket, status, squad, seen, tag, tstate, s1, s2 in opps:
        ins("opportunity", dict(opportunity_id=oid, title=title, problem_statement=f"{title}: handlers lose time every week.", bucket=bucket,
                                status=status, squad=squad, first_seen_as_of=seen, tag=tag, tag_ref="story-88" if tag != "none" else None,
                                tag_state=tstate))
        for rid, tot in ((R1, s1), (R2, s2)):
            if tot is not None:
                ins("score", dict(opportunity_id=oid, run_id=rid, total=tot, breadth=round(tot * .3, 2), severity=round(tot * .4, 2),
                                  value=round(tot * .2, 2), corroboration=round(tot * .15, 2), recency=round(tot * .1, 2),
                                  renewal=1.25 if oid == "o1" else 1.0, roadmap=0.5 if tag == "on_roadmap" else 1.0,
                                  unresolved_insights=1 if oid == "o1" else 0))

    sources = ["gong", "intercom", "fireflies", "fullstory"]
    n = 0
    for oi, (oid, *_rest) in enumerate(opps):
        for k in range(2):
            n += 1
            src = sources[(oi + k) % 4]
            raw = content_id("raw", src, f"s{n}")
            acc = None if (oid == "o1" and k == 1) else accounts[(oi + k) % 3][0]
            ins("raw_record", dict(raw_id=raw, source=src, route="support", source_id=f"{src}-{8800 + n}", account_id=acc,
                                   account_status="resolved" if acc else "unresolved",
                                   occurred_at=("2026-10-30" if k == 0 else "2026-09-20") + "T10:00:00+00:00",
                                   payload_json={"note": "synthetic record", "n": n}))
            quote = f"I have to redo forty of these by hand every week number {n}"
            text = f"{quote} and it takes ages."
            sid = content_id("snippet", raw, 0, text)
            ins("snippet", dict(snippet_id=sid, raw_id=raw, text=text, context_text="So what slows you down most?",
                                start_ms=872000 + n * 1000, end_ms=880000 + n * 1000))
            start = text.index(quote)
            iid = content_id("insight", sid, quote)
            ins("insight", dict(insight_id=iid, snippet_id=sid, run_id=R2, problem=f"Problem {n}", quote=quote, quote_match="exact",
                                quote_span_start=start, quote_span_end=start + len(quote), severity=3, account_id=acc,
                                account_status="resolved" if acc else "unresolved"))
            ins("opportunity_insight", dict(opportunity_id=oid, insight_id=iid, similarity=.8, post_ship=int(oid == "o4" and k == 1)))
            ins("triage", dict(snippet_id=sid, run_id=R2, backend="decision_model", is_signal_p=.9, decision="keep", latency_ms=200))

    # noise-audit sample: 40 dropped items with weights
    for i in range(40):
        near = i < 25
        raw = content_id("raw", "intercom", f"drop{i}")
        ins("raw_record", dict(raw_id=raw, source="intercom", source_id=f"conv-drop{i}", payload_json={"n": i}, occurred_at="2026-10-31T09:00:00+00:00"))
        sid = content_id("snippet", raw, 0, f"drop {i}")
        ins("snippet", dict(snippet_id=sid, raw_id=raw, text=f"Thanks, that is sorted now ({i})."))
        ins("triage", dict(snippet_id=sid, run_id=R2, backend="cheap_llm_fallback" if i % 10 == 0 else "decision_model",
                           is_signal_p=.07 if near else .02, decision="drop", latency_ms=150, audit_weight=4.0 if near else 12.0))

    for oid, *_ in opps[:3]:
        failed = oid == "o2"
        ins("brief", dict(brief_id=content_id("brief", oid), opportunity_id=oid, run_id=R2, body_md="Handlers reassign claims one by one [i1].",
                          citations_json=["i1"], check_status="failed_checks" if failed else "passed",
                          check_failures_json=[{"rule": "numbers", "detail": "GBP 2.0m does not match the fact sheet (total 1,100,000)"}] if failed else [],
                          prompt_version="v1", model="qwen/qwen3.8-max-0902"))
    states = {"faithfulness": (23, 8), "signal": (31, 12), "duplicate": (19, 5)}
    for j, (p, f) in states.items():
        ins("judge_version", dict(judge_version_id=f"{j}@v1+glm", judge=j, prompt_version="v1", model="glm", state="calibrating", n_pass=p, n_fail=f))
    for oid in ("o1", "o2", "o3"):
        bid = content_id("brief", oid)
        for j, v in (("faithfulness", "fail" if oid == "o2" else "pass"), ("signal", "pass")):
            ins("judgement", dict(judgement_id=content_id("j", oid, j), run_id=R2, judge_version_id=f"{j}@v1+glm", judge=j,
                                  target_type="brief", target_id=bid, verdict=v, critique=f"{j} critique for {oid}"))
    ins("judgement", dict(judgement_id=content_id("j", "o5"), run_id=R2, judge_version_id="duplicate@v1+glm", judge="duplicate",
                          target_type="opportunity", target_id="o5", verdict="fail", critique="Roadmap story 88 covers a different problem."))

    stages = [("triage", "cloudflare/clef", 210), ("extract", "qwen/qwen3.8-flash", 640), ("brief", "qwen/qwen3.8-max-0902", 2100), ("judge", "glm", 1800)]
    for i, (stage, model, ms) in enumerate(stages * 3):
        ins("model_call", dict(call_id=f"call{i}", run_id=R2, stage=stage, target_type="opportunity", target_id="o1", model=model, profile="replay",
                               input_hash=sha256(f"in{i}")[:8], output_hash=sha256(f"out{i}")[:8], tokens_in=500, tokens_out=120,
                               cost_usd=0.01, latency_ms=ms + i * 5, cached=int(i % 2 == 0)))

    job = {"schema_version": 1, "job_id": "1" * 16, "idempotency_key": H, "status": "draft", "action": "create", "opportunity_id": "o4".ljust(16, "0"),
           "created_at": "2026-11-03T10:00:00Z", "created_by": "priya.n", "data_classification": "internal",
           "trace": {"opportunity_id": "2" * 16, "handoff_id": "3" * 16, "run_id": R2}}
    job.update(opportunity_id="2" * 16, evidence={"insight_ids": ["4" * 16], "run_manifest_hash": H, "intent_doc": {"handoff_id": "3" * 16, "sha256": H}},
               problem_statement="Handlers lose uploaded documents during claim handling every week.",
               users_affected=[{"tier": "Enterprise", "accounts": 2, "roles": ["claims handler"]}],
               acceptance_criteria=[{"id": "AC1", "given": "a handler uploads a file", "when": "the page reloads", "then": "the file is listed"}],
               outcome_metric={"name": "lost uploads", "definition": "uploads missing after reload", "baseline": {"value": 12, "unit": "per week", "as_of": A2},
                               "target": 0, "query": {"kind": "sql", "ref": "q1"}}, constraints=["no schema change"], non_goals=["bulk import"])
    ins("handoff", dict(handoff_id="h4", opportunity_id="o4", intent_doc_md="# Intent: document uploads\n\n## Problem\n\nFiles vanish.\n\n- keep files\n- show them",
                        factory_job_json=job, status="sent"))
    ins("handoff", dict(handoff_id="h3", opportunity_id="o3", intent_doc_md="# Intent: payment approval\n\nDraft text.", factory_job_json={"schema_version": 1},
                        status="drafted"))
    for i, kind in enumerate(("release_note", "help_article", "change_notice", "followup_brief")):
        ins("outtake", dict(outtake_id=f"out{i}", story_ref="story-77", kind=kind, body_md=f"Draft {kind}.", status="draft"))

    s.append_audit("system", "system", "run.done", "run", R2, {"cost_usd": 0.12}, at="2026-11-03T02:10:00+00:00")
    s.append_audit("priya.n", "person", "opportunity.transition", "opportunity", "o3", {"from_status": "proposed", "to_status": "accepted"},
                   at="2026-11-03T09:12:40+00:00")
    ins("annotation", dict(annotation_id="ann0", target_type="opportunity", target_id="o3", actor="priya.n", action="accept", created_at="2026-11-03T09:12:40+00:00"))
    s.close()

    rep = out / "reports" / "eval"
    rep.mkdir(parents=True, exist_ok=True)
    reports = {
        "ground-truth-42": dict(suite="ground-truth", run_id=R2, seed=42, passed=True, metrics={"theme_recall": 1.0, "top6_exact": True, "loud_narrow_rank": 8}, gates={"recall": True}),
        "holdout-43": dict(suite="holdout", run_id=R2, seed=43, passed=True, metrics={"theme_recall": 1.0, "loud_narrow_rank": 9}, gates={"recall": True}),
        "stability-42": dict(suite="stability", run_id=R2, seed=42, passed=True, metrics={"ids_stable": True, "themes_forked": 0}, gates={"stable": True}),
        "judges-42": dict(suite="judges", run_id=R2, seed=42, passed=False, metrics={"faithfulness_n": 31}, gates={"trusted": False}),
    }
    for name, body in reports.items():
        (rep / f"{name}-0.json").write_text(json.dumps(body), encoding="utf-8")
    return out / "keelwater.sqlite"


_TEMPLATE = {}


def seed_copy(dest, scratch):
    """Seed once per test run under `scratch`, then copy the folder (a seed is ~200 committed inserts, slow on Windows)."""
    import shutil
    if "dir" not in _TEMPLATE:
        _TEMPLATE["dir"] = Path(scratch) / "seed_template"
        seed(_TEMPLATE["dir"])
    shutil.copytree(_TEMPLATE["dir"], dest)
    return Path(dest) / "keelwater.sqlite"


if __name__ == "__main__":
    print(seed(sys.argv[1] if len(sys.argv) > 1 else ".scratch/board-demo"))
