"""Suite 3: two-batch replay, September then October into one store (evals.md 4.4)."""

from datetime import datetime
from pathlib import Path

from ..contracts import StabilityReport
from ..store import Store
from . import common, ground_truth as gt

SEP_AS_OF, OCT_AS_OF = "01/10/2026", "03/11/2026"


def snapshot(a):
    """Planted-theme opportunities of a store: {opportunity_id: (theme, frozenset of insight ids)} plus per-theme shares."""
    planted = {t for t, th in a.truth.themes.items() if th["kind"] in gt.SIGNAL_KINDS}
    opps = {o: (a.label[o], frozenset(ids)) for o, ids in a.members.items() if a.label[o] in planted}
    return {"opps": opps, "shares": {t: a.theme_share(t) for t in planted}}


def check(before, after):
    """The three conditions of evals.md 4.4. Returns (metrics, gates)."""
    lost = [o for o, (theme, _) in before["opps"].items() if after["opps"].get(o, (None,))[0] != theme]
    forked = [t for t, sh in after["shares"].items() if sum(s >= gt.SPLIT_SHARE for s in sh.values()) >= 2]
    shrunk = [o for o, (_, ids) in before["opps"].items() if o in after["opps"] and not ids <= after["opps"][o][1]]
    m = {"opportunities_after_sep": len(before["opps"]), "ids_lost": len(lost), "themes_forked": len(forked), "memberships_shrunk": len(shrunk)}
    return m, {"ids_kept": not lost, "no_fork": not forked, "memberships_grow": not shrunk}


def run_suite(a):
    truth_path = gt.GT_PATH
    if not truth_path.is_file():
        return False, [f"ground truth missing: {truth_path.as_posix()} (run: keelwater generate --seed 42)"], None
    truth = gt.Truth(gt.load_gt(truth_path))
    db = Path(a.scratch) / "stability.sqlite"
    rc, out, _ = common.replay(a, batch="sep", as_of=SEP_AS_OF, db=db)
    if rc != 0:
        return False, [f"sep replay failed (exit {rc}):\n{out}"], None
    store = Store(db)
    before = snapshot(gt.Analysis(store, truth))
    store.close()
    rc, out, report = common.replay(a, batch="oct", as_of=OCT_AS_OF, db=db)
    if rc != 0:
        return False, [f"oct replay failed (exit {rc}):\n{out}"], None
    store = Store(db)
    after = snapshot(gt.Analysis(store, truth))
    m, g = check(before, after)
    run_id = report["run_id"]
    passed = all(g.values())
    rep = StabilityReport(run_id=run_id, seed=42, passed=passed, metrics=m, gates=g, cache_keys=report.get("manifest", {}).get("cache_keys", []),
                          detail={"as_of": [SEP_AS_OF, OCT_AS_OF]})
    path = common.write_report(a.report_dir, rep)
    out = [f"run {run_id}  sep as_of={SEP_AS_OF} then oct as_of={OCT_AS_OF}  same store",
           f"ids kept      {'PASS' if g['ids_kept'] else 'FAIL'}  {m['ids_lost']} of {m['opportunities_after_sep']} September planted-theme opportunities lost their id",
           f"no forks      {'PASS' if g['no_fork'] else 'FAIL'}  {m['themes_forked']} themes held by two opportunities of 25% or more",
           f"memberships   {'PASS' if g['memberships_grow'] else 'FAIL'}  {m['memberships_shrunk']} September memberships shrank",
           f"overall  {'PASS' if passed else 'FAIL'}   report: {path.as_posix()}"]
    store.close()
    return passed, out, path
