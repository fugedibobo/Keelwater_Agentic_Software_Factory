"""Shared suite plumbing: replay the pipeline into a scratch store, write reports, compute drift metrics."""

import contextlib
import io
import json
from pathlib import Path

from .. import cli, pipeline
from ..store import Store
from .stats import weighted_rate

JUDGES = ("signal", "duplicate", "faithfulness")


def replay(args, seed=42, batch="all", as_of=None, db=None):
    """Run the pipeline (profile from args, replay by default) into `db`; returns (return code, output text, run report dict)."""
    scratch = Path(args.scratch)
    db = db or scratch / f"seed{seed}-{batch}.sqlite"
    argv = ["--profile", args.profile, "--seed", str(seed), "--batch", batch, "--as-of", as_of or args.as_of, "--db", str(db),
            "--cache-dir", args.cache_dir, "--report-dir", str(scratch / "rep"), "--max-usd", str(args.max_usd)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pipeline.run_pipeline(cli.run_parser().parse_args(argv))
    path = pipeline.report_path(scratch / "rep", args.profile, seed, batch)
    report = json.loads(path.read_text(encoding="utf-8")) if rc == 0 and path.is_file() else {}
    return rc, buf.getvalue(), report


def open_store(db):
    return Store(db)


def write_report(report_dir, report):
    out = Path(report_dir) / "eval"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{report.suite}-{report.run_id}.json"
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path


def f2(v):
    return "n/a" if v is None else f"{v:.2f}"


def judged_verdicts(store):
    """{(target_id, judge): verdict} from the newest judgement rows."""
    return {(j["target_id"], j["judge"]): j["verdict"] for j in store.select("judgement")}


def agreement(items):
    """items: (human verdict, judge verdict, weight). Returns {tpr, tnr, n_pass, n_fail, tpr_n, tnr_n, tpr_lo, tpr_hi, tnr_lo, tnr_hi}.

    TPR = share of human passes the judge passes; TNR = share of human fails it fails (evals.md 5.6); weighted, Wilson on the effective size.
    """
    passes = [(j == "pass", w) for h, j, w in items if h == "pass"]
    fails = [(j == "fail", w) for h, j, w in items if h == "fail"]
    tpr, tpr_n, tpr_lo, tpr_hi = weighted_rate(passes)
    tnr, tnr_n, tnr_lo, tnr_hi = weighted_rate(fails)
    return {"tpr": tpr, "tnr": tnr, "n_pass": len(passes), "n_fail": len(fails), "tpr_n": tpr_n, "tnr_n": tnr_n,
            "tpr_lo": tpr_lo, "tpr_hi": tpr_hi, "tnr_lo": tnr_lo, "tnr_hi": tnr_hi}


def drift(store):
    """The three evals.md 8.1 metrics where data exists; None otherwise."""
    judged = judged_verdicts(store)
    labels = [l for l in store.select("label") if l["blind"]]
    per_judge = {}
    for j in JUDGES:
        items = [(l["verdict"], judged[(l["target_id"], j)], l["weight"]) for l in labels if l["judge"] == j and (l["target_id"], j) in judged]
        r = agreement(items)
        per_judge[j] = {"tpr": r["tpr"], "tnr": r["tnr"], "n": len(items)}
    audit = [(l["verdict"] == "pass", l["weight"]) for l in labels if l["target_type"] == "noise_audit"]
    miss = weighted_rate(audit)[0]
    acts = [a["action"] for a in store.select("annotation") if a["action"] in ("accept", "merge", "reject", "park")]
    acceptance = sum(a in ("accept", "merge") for a in acts) / len(acts) if acts else None
    return {"label_panel_agreement": per_judge, "noise_audit_miss_rate": miss, "pm_acceptance_rate": acceptance}


def store_drift(store, run_id=None):
    """Compute the drift metrics and keep them in the run's manifest_json under `drift`."""
    d = drift(store)
    row = store.db.execute("SELECT run_id FROM run ORDER BY rowid DESC LIMIT 1").fetchone() if run_id is None else (run_id,)
    if row:
        old = (store.select("run", {"run_id": row[0]}) or [{}])[0].get("manifest_json") or {}
        store.update("run", {"run_id": row[0]}, {"manifest_json": {**old, "drift": d}})
    return d
