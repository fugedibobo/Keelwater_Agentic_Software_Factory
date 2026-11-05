"""Rewrite the README regions this script owns, from committed reports and the model cache.

Regions sit between <!-- generated:NAME:start --> and <!-- generated:NAME:end --> (inline or on their own lines):
  results           verdict, seed 42, seed 43, stability and judges, from reports/eval/<suite>-<id>.json
  limits-clustering the theme counts in the first Limits bullet
  cost              USD per nightly run, from the usage in fixtures/llm_cache priced with config/models.yaml

    python scripts/readme_sections.py           write README.md
    python scripts/readme_sections.py --check   exit 1 if README.md differs (writes nothing)

Floors come from FLOORS_42 / FLOORS_43 in signal_engine/evals/ground_truth.py (read with ast, never retyped here).
Cost reads only usage fields and request.model of the cached calls; no prompt or response text is read or printed.
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EVAL_DIR = ROOT / "reports" / "eval"
RUN_REPORT = ROOT / "reports" / "runs" / "latest-demo.json"
CACHE_DIR = ROOT / "fixtures" / "llm_cache"
EARLIER_LABEL = "Earlier run (gpt-oss routing, 04/11/2026)"
MIN_LABELS = 50  # evals.md section 7: real PM labels per judge class needed to certify

# Report ids the README cites. Change these when a new live run is committed.
CURRENT = {"ground-truth": "efe009d511d14c7d", "holdout": "67fb4d4fbff640ad",
           "stability": "6d7f81793bec4276", "judges": "8483fdb0aaee4817"}
EARLIER = None  # same shape as CURRENT; set it to render the comparison table

# (label, metric key, kind): f = 2 decimals, i = integer, of = "n of total", b = yes/no, pair = two keys
SEED42 = [
    ("Signal recall", "signal_recall", "f"), ("Noise-drop rate", "noise_drop_rate", "f"),
    ("Bucket accuracy", "bucket_accuracy", "f"), ("Quote verification", "quote_verification", "f"),
    ("Account attribution", "attribution", "f"), ("Themes recovered", "themes_recovered", "of"),
    ("Mean purity", "mean_purity", "f"), ("Split themes", "split_themes", "i"), ("Over-merges", "over_merges", "i"),
    ("Noise themes in the top 10", "noise_in_top10", "i"),
    ("Top-6 set equals the six real themes", "top_set", "b"),
    ("Adversarial probe ranks below all six", "probe_below_six", "b"),
    ("Citation failures after retry", "citation_failures", "i"),
    ("Faithfulness pass rate (reported)", "faithfulness_pass_rate", "f"),
]
SEED43 = [
    ("Signal recall", "signal_recall", "f"), ("Quote verification", "quote_verification", "f"),
    ("Account attribution", "attribution", "f"), ("Themes recovered", "themes_recovered", "of"),
    ("Mean purity", "mean_purity", "f"), ("Noise themes in the top 10", "noise_in_top10", "i"),
    ("Citation failures after retry", "citation_failures", "i"),
    ("Noise-drop rate, bucket accuracy (reported)", ("noise_drop_rate", "bucket_accuracy"), "pair"),
]


def load_report(suite, run_id):
    return json.loads((EVAL_DIR / f"{suite}-{run_id}.json").read_text(encoding="utf-8"))


def read_floors():
    """FLOORS_42, FLOORS_43 and BOOLS_42 as literals from ground_truth.py, without importing the package."""
    tree = ast.parse((ROOT / "signal_engine" / "evals" / "ground_truth.py").read_text(encoding="utf-8"))
    found = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
             if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
             and n.targets[0].id in ("FLOORS_42", "FLOORS_43", "BOOLS_42")}
    return found["FLOORS_42"], found["FLOORS_43"], found["BOOLS_42"]


def f2(v):
    return f"{v:.2f}"


def value(m, key, kind):
    if kind == "pair":
        return ", ".join(f2(m[k]) for k in key)
    v = m[key]
    if kind == "f":
        return f2(v)
    if kind == "of":
        return f"{v} of {m['themes_total']}"
    if kind == "b":
        return "yes" if v else "no"
    return str(v)


def floor_text(floors, bools, key, kind, m):
    """-> (floor text, comparable). A bool metric must be yes; a metric with no floor is reported only."""
    if kind == "pair" or (key not in floors and key not in bools):
        return "not gated", False
    if key in bools:
        return "yes", True
    _, fl, op = floors[key]
    if fl == "all":
        fl = m["themes_total"]
    if kind == "of":
        return f"{fl} of {m['themes_total']}", True
    if op == "<=":
        return ("0" if fl == 0 else f"at most {fl}"), True
    return (f2(fl) if isinstance(fl, float) else str(fl)), True


def seed_table(report, rows, floors, bools):
    m, g = report["metrics"], report["gates"]
    out = ["| Metric | Result | Floor | Holds |", "|---|---|---|---|"]
    for label, key, kind in rows:
        fl, gated = floor_text(floors, bools, key, kind, m)
        holds = ("yes" if g[key] else "no") if gated else "n/a"
        out.append(f"| {label} | {value(m, key, kind)} | {fl} | {holds} |")
    return "\n".join(out)


def earlier_table(now, before, floors42, floors43, bools):
    """One compact table of the gated numeric metrics: earlier run against now, with the floor."""
    out = [f"**{EARLIER_LABEL}**, same suites and floors:", "", "| Metric | Earlier | Now | Floor |", "|---|---|---|---|"]
    for tag, rows, floors, b in (("Seed 42", SEED42, floors42, bools), ("Seed 43", SEED43, floors43, ())):
        for label, key, kind in rows:
            fl, gated = floor_text(floors, b, key, kind, now[tag]["metrics"])
            if gated and kind != "b":
                out.append(f"| {tag}: {label} | {value(before[tag]['metrics'], key, kind)} "
                           f"| {value(now[tag]['metrics'], key, kind)} | {fl} |")
    return "\n".join(out)


def stability_text(rep):
    m = rep["metrics"]
    lost = (f"No September opportunity lost its id (0 of {m['opportunities_after_sep']})" if m["ids_lost"] == 0
            else f"{m['ids_lost']} of {m['opportunities_after_sep']} September opportunities lost their id")
    shrunk = "no membership shrank" if m["memberships_shrunk"] == 0 else f"{m['memberships_shrunk']} memberships shrank"
    fork = (f"but {m['themes_forked']} planted themes are held by two opportunities of 25% or more each"
            if m["themes_forked"] else "and no planted theme is held by two opportunities of 25% or more each")
    return f"{lost} and {shrunk}, {fork}." if m["themes_forked"] else f"{lost}, {shrunk}, {fork}."


def judges_block(rep, run_id):
    rows = rep["detail"]["rows"]
    real_labels = max([r["dev"]["labels"] + r["held_out"]["labels"] for r in rows if r["origin"] == "real_pm"] or [0])
    certified = [r for r in rows if r["origin"] == "real_pm" and r["state"] != "uncalibrated"]
    state = "passes" if rep["passed"] else "fails"
    head = (f"**Judges** (`eval --suite judges`, report `judges-{run_id}`; {state}, "
            f"{'some certified' if certified else 'none certified'}). The `synthetic_seed` rows are constructed items and "
            f"never certify (evals.md section 7). The `real_pm` rows hold {real_labels} of {MIN_LABELS} labels per class, "
            f"so every judge is uncalibrated. Held-out agreement on the constructed items, with 95% intervals:")
    out = ["| Judge | True-positive rate | True-negative rate |", "|---|---|---|"]
    for r in rows:
        if r["origin"] != "synthetic_seed":
            continue
        h = r["held_out"]
        out.append(f"| {r['judge']} | {f2(h['tpr'])} ({f2(h['tpr_lo'])} to {f2(h['tpr_hi'])}) "
                   f"| {f2(h['tnr'])} ({f2(h['tnr_lo'])} to {f2(h['tnr_hi'])}) |")
    return head + "\n\n" + "\n".join(out)


def load_set(ids):
    return {"Seed 42": load_report("ground-truth", ids["ground-truth"]), "Seed 43": load_report("holdout", ids["holdout"]),
            "Stability": load_report("stability", ids["stability"]), "Judges": load_report("judges", ids["judges"])}


def results_region():
    f42, f43, bools = read_floors()
    now = load_set(CURRENT)
    labels = {"Seed 42": "on seed 42", "Seed 43": "on seed 43", "Stability": "on stability"}
    failing = [labels[n] for n in labels if not now[n]["passed"]]
    judges = now["Judges"]
    uncert = not judges["detail"]["qualified"]
    fails = ", ".join(failing[:-1]) + (" and " if len(failing) > 1 else "") + (failing[-1] if failing else "")
    verdict = ("Verdict: " + (f"the floors fail {fails}" if failing else "every floor holds") + ". "
               + ("The judge suite passes only because no judge can be certified without real PM labels. "
                  if judges["passed"] and uncert else "The judge suite " + ("passes. " if judges["passed"] else "fails. "))
               + f"`eval --suite all` exits {0 if all(r['passed'] for r in now.values()) else 1}. "
               "The tables are the latest run of each suite in `reports/eval/`; the numbers are the same in the board's Evals tab.")
    c = CURRENT
    parts = [
        verdict,
        f"**Seed 42** (`eval --suite ground-truth`, report `ground-truth-{c['ground-truth']}`; the gates are in "
        f"[evals.md section 4.2](docs/evals.md)). Synthetic.\n\n" + seed_table(now["Seed 42"], SEED42, f42, bools),
        f"**Seed 43, held out** (`eval --suite holdout`, report `holdout-{c['holdout']}`; floors in "
        f"[evals.md section 4.3](docs/evals.md)). Synthetic.\n\n" + seed_table(now["Seed 43"], SEED43, f43, ()),
        f"**Stability** (`eval --suite stability`, report `stability-{c['stability']}`): "
        f"{'passes' if now['Stability']['passed'] else 'fails'}. " + stability_text(now["Stability"]),
        judges_block(judges, c["judges"]),
    ]
    if EARLIER:
        parts.append(earlier_table(now, load_set(EARLIER), f42, f43, bools))
    return "\n\n".join(parts)


def limits_region():
    a, b = load_report("ground-truth", CURRENT["ground-truth"])["metrics"], load_report("holdout", CURRENT["holdout"])["metrics"]
    return (f"seed 42 recovers {a['themes_recovered']} of {a['themes_total']} themes "
            f"and seed 43 recovers {b['themes_recovered']} of {b['themes_total']}")


def price_table(stages):
    """model id -> {in, out}: every priced model in the demo profile; a stage's price covers its own model."""
    prices = {}
    for st in stages.values():
        if "price" in st and "model" in st:
            prices[st["model"]] = st["price"]
    return prices


def cost_per_run(report_path, cache_dir, stages):
    """USD for one run: tokens from the cached responses' usage, priced per request model, else the stage price."""
    prices = price_table(stages)
    total = 0.0
    for key in json.loads(Path(report_path).read_text(encoding="utf-8"))["manifest"]["cache_keys"]:
        stage = key.split("/")[0]
        call = json.loads((Path(cache_dir) / f"{key}.json").read_text(encoding="utf-8"))
        price = prices.get(call["request"].get("model")) or stages.get(stage, {}).get("price")
        if price is None:
            raise SystemExit(f"no price for model {call['request'].get('model')!r} (stage {stage}) in config/models.yaml")
        u = call["response"].get("usage", {})
        total += ((u.get("tokens_in") or 0) * price["in"] + (u.get("tokens_out") or 0) * price.get("out", 0.0)) / 1e6
    return total


def sig2(x):
    return f"{float(f'{x:.2g}'):g}"


def cost_region():
    stages = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))["profiles"]["demo"]["stages"]
    c = cost_per_run(RUN_REPORT, CACHE_DIR, stages)
    return (f"tokens come to about USD {sig2(c)} per nightly run at demo volume, {sig2(c * 10)} at 10x and "
            f"{sig2(c * 100)} at 100x (estimated from list prices and the recorded token counts of the demo run, INFERRED).")


REGIONS = {"results": lambda: "\n" + results_region() + "\n", "limits-clustering": limits_region, "cost": cost_region}


def render(text):
    for name, make in REGIONS.items():
        pat = re.compile(rf"(<!-- generated:{name}:start -->)(.*?)(<!-- generated:{name}:end -->)", re.S)
        if len(pat.findall(text)) != 1:
            raise SystemExit(f"README needs exactly one generated:{name} region")
        text = pat.sub(lambda m: m.group(1) + make() + m.group(3), text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if README.md differs; write nothing")
    args = ap.parse_args(argv)
    old = README.read_text(encoding="utf-8")
    new = render(old)
    if args.check:
        if new != old:
            print("README.md generated regions are out of date: run python scripts/readme_sections.py")
            return 1
        print("README.md generated regions are current")
        return 0
    if new != old:
        README.write_text(new, encoding="utf-8", newline="\n")
    print("README.md written" if new != old else "README.md unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
