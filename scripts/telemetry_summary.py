"""Summarise reports/factory/build-telemetry.csv into docs/delegation.md section 10.

  uv run python scripts/telemetry_summary.py              print the summary
  uv run python scripts/telemetry_summary.py --write-doc  also rewrite the block between the measured markers

Every figure is computed from the CSV. "not reported" cells are counted, never summed or estimated.
The "refreshed on" date is the CSV file's modification time unless --date DD/MM/YYYY is given.
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "reports" / "factory" / "build-telemetry.csv"
DOC_PATH = ROOT / "docs" / "delegation.md"
START, END = "<!-- measured:start -->", "<!-- measured:end -->"
ORDER = ["opus", "sonnet", "haiku", "codex", "agy", "other"]
NEW_BUILDERS = ("codex", "agy")


def num(cell):
    try:
        return float(cell)
    except (TypeError, ValueError):
        return None  # "not reported" and blanks


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def engines(rows):
    seen = {r["engine"] for r in rows}
    return [e for e in ORDER if e in seen] + sorted(seen - set(ORDER))


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def summarise(rows):
    s = {"engines": engines(rows), "tokens": {}, "usd": {}, "first": {}, "rework": {}, "build": {}}
    for e in s["engines"]:
        mine = [r for r in rows if r["engine"] == e]
        t = {"measured": 0.0, "estimated": 0.0, "missing": 0}
        u = {"measured": 0.0, "estimated": 0.0}
        for r in mine:
            v = num(r["tokens_total"])
            if v is not None and r["tokens_basis"] in ("measured", "estimated"):
                t[r["tokens_basis"]] += v
            else:
                t["missing"] += 1
            d = num(r["live_usd"])
            if d is not None and r["live_usd_basis"] in ("measured", "estimated"):
                u[r["live_usd_basis"]] += d
        builds = [r for r in mine if r["role"] == "build"]
        checked = [r for r in builds if r["first_check_result"] in ("PASS", "REWORK")]
        s["tokens"][e], s["usd"][e] = t, u
        s["first"][e] = (sum(r["first_check_result"] == "PASS" for r in checked), len(checked))
        s["rework"][e] = int(sum(num(r["rework_count"]) or 0 for r in builds))
        s["build"][e] = len(builds)
    builds = [r for r in rows if r["role"] == "build"]
    accepted = [r for r in builds if r["status"] in ("done", "partial")]
    s["n_builds"] = len(builds)
    s["n_accepted"] = len(accepted)
    s["accepted_new"] = sum(r["engine"] in NEW_BUILDERS for r in accepted)
    status = {}
    for r in rows:
        status.setdefault(r["issue"], r["status"])
    s["counts"] = {k: sum(v == k for v in status.values()) for k in ("done", "partial", "in-progress")}
    s["n_rows"], s["n_orders"] = len(rows), len(status)
    return s


def render(s, date):
    c = s["counts"]
    L = [f"{c['done']} done, {c['partial']} partial, {c['in-progress']} in progress: refreshed on {date}",
         f"({s['n_rows']} rows across {s['n_orders']} work orders.)"]
    L += ["", "First-check pass rate, reworks and share of building, per engine "
          "(build rows only; rows without a PASS or REWORK first check are left out of the rate).", "",
          "| Engine | First check passed | Pass rate | Reworks | Build rows | Share of build rows |",
          "|---|---|---|---|---|---|"]
    for e in s["engines"]:
        p, n = s["first"][e]
        L.append(f"| {e} | {p} of {n} | {pct(p, n)} | {s['rework'][e]} | {s['build'][e]} | {pct(s['build'][e], s['n_builds'])} |")
    L += ["", f"Total reworks (REWORK verdicts on build pull requests): {sum(s['rework'].values())}.",
          f"Codex and agy built {s['accepted_new']} of {s['n_accepted']} "
          f"done or partial work orders ({pct(s['accepted_new'], s['n_accepted'])}); "
          f"their share of all {s['n_builds']} build rows is "
          f"{pct(sum(s['build'].get(e, 0) for e in NEW_BUILDERS), s['n_builds'])}."]
    return "\n".join(L)


def write_doc(doc_text, block):
    a, b = doc_text.find(START), doc_text.find(END)
    if a < 0 or b < a:
        raise SystemExit(f"markers {START} / {END} not found in the doc")
    return doc_text[:a + len(START)] + "\n\n" + block + "\n\n" + doc_text[b:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--doc", type=Path, default=DOC_PATH)
    ap.add_argument("--date", help="refreshed-on date, DD/MM/YYYY (default: CSV modification time)")
    ap.add_argument("--write-doc", action="store_true")
    a = ap.parse_args(argv)
    date = a.date or datetime.fromtimestamp(a.csv.stat().st_mtime).strftime("%d/%m/%Y")
    block = render(summarise(load(a.csv)), date)
    print(block)
    if a.write_doc:
        a.doc.write_bytes(write_doc(a.doc.read_text(encoding="utf-8"), block).encode("utf-8"))  # LF kept on Windows


if __name__ == "__main__":
    main()
