"""keelwater eval: run one or all suites; exit 0 only when every floor holds (docs/evals.md 9, architecture 11)."""

import argparse
import time

SUITES = ("ground-truth", "holdout", "stability", "judges")


def parser():
    p = argparse.ArgumentParser(prog="keelwater eval", description="score the pipeline against ground truth, seed 43, a two-batch replay and labels")
    p.add_argument("--suite", choices=[*SUITES, "all"], default="all")
    p.add_argument("--qualify", action="store_true", help="judges: score held_out once for the current judge version and store its state")
    p.add_argument("--report-dir", default="reports")
    p.add_argument("--phoenix", action="store_true", help="log each suite report as a Phoenix experiment")
    p.add_argument("--profile", choices=["replay", "demo"], default="replay", help="demo calls live models for uncached items and records them")
    p.add_argument("--db", help="score this existing store instead of replaying (ground-truth and judges; --qualify defaults to .local/keelwater.sqlite)")
    p.add_argument("--as-of", default="03/11/2026")
    p.add_argument("--cache-dir", default="fixtures/llm_cache")
    p.add_argument("--max-usd", type=float, default=1.75)
    p.add_argument("--scratch", default=".scratch/eval")
    p.add_argument("--seeds", default="labels/seed")
    return p


def main(argv):
    a = parser().parse_args(argv)
    from . import ground_truth, holdout, judges_suite, stability
    mods = {"ground-truth": ground_truth, "holdout": holdout, "stability": stability, "judges": judges_suite}
    ok = True
    for name in (SUITES if a.suite == "all" else (a.suite,)):
        t0 = time.perf_counter()
        print(f"== eval --suite {name}")
        passed, lines, path = mods[name].run_suite(a)
        print("\n".join(lines))
        print(f"   {name}: {'PASS' if passed else 'FAIL'} in {time.perf_counter() - t0:.0f}s")
        if a.phoenix and path:
            from .. import telemetry
            telemetry.log_experiment(path)
        ok = ok and passed
    return 0 if ok else 1
