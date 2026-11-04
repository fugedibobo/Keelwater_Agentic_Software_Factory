"""Suite 2: replay held-out seed 43 and score it against data/holdout/ground_truth.yaml (evals.md 4.3)."""

import json
from pathlib import Path

from ..contracts import HoldoutReport
from . import common, ground_truth as gt
from .common import f2


def seed42_metrics(a):
    """Metrics of the newest ground-truth report; scores seed 42 first when there is none."""
    files = sorted((Path(a.report_dir) / "eval").glob("ground-truth-*.json"), key=lambda p: (p.stat().st_mtime, p.name))
    if files:
        return json.loads(files[-1].read_text(encoding="utf-8"))["metrics"], None
    passed, out, path = gt.run_suite(a)
    return (json.loads(path.read_text(encoding="utf-8"))["metrics"] if path else {}), out


def run_suite(a):
    got = gt.evaluate_seed(a, 43)
    if isinstance(got, str):
        return False, [got], None
    store, report, m, d, g = got
    run_id = report.get("run_id") or gt.latest_run_id(store) or "unknown"
    common.store_drift(store)
    m42, _ = seed42_metrics(a)
    passed = all(g.values())
    rep = HoldoutReport(run_id=run_id, seed=43, passed=passed, metrics={k: v for k, v in m.items() if not isinstance(v, (list, dict))},
                        gates=g, cache_keys=report.get("manifest", {}).get("cache_keys", []), detail=d)
    path = common.write_report(a.report_dir, rep)
    out = gt.lines(43, run_id, report, m, d, g)
    out.append(f"{'metric':<22}{'seed 42':>9}{'seed 43':>9}{'floor 43':>10}")
    for k in dict.fromkeys([*gt.FLOORS_43, "noise_drop_rate", "bucket_accuracy", "split_themes", "over_merges", "top3_set"]):
        floor = gt.FLOORS_43.get(k, (None, "reported", None))[1]
        out.append(f"{k:<22}{_fmt(m42.get(k)):>9}{_fmt(m.get(k)):>9}{str(floor):>10}")
    out.append(f"overall  {'PASS' if passed else 'FAIL'}   report: {path.as_posix()}" + ("" if passed else "   failing: " + ", ".join(k for k, v in g.items() if not v)))
    store.close()
    return passed, out, path


def _fmt(v):
    return "-" if v is None else f2(v) if isinstance(v, float) else str(v)
