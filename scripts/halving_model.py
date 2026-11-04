"""Halving model and board tracker: when do Keelwater's delivery timelines halve?

Run (matplotlib is only needed for --outputs):
  uv run python scripts/halving_model.py                       model, first month at 50%, sensitivity
  uv run python scripts/halving_model.py --generate            write synthetic data/delivery/items.csv (seed 42)
  uv run python scripts/halving_model.py --track data/delivery/items.csv
  uv run --with matplotlib python scripts/halving_model.py --outputs   chart (svg, png), summary.md, tracker.md

Inputs: config/halving_inputs.yaml (every input labelled FOUND or INFERRED). All company data is invented.
"""
import argparse
import copy
import csv
import random
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "halving_inputs.yaml"
ITEMS = ROOT / "data" / "delivery" / "items.csv"
OUT_DIR = ROOT / "reports" / "halving"

STAGES = ["discovery_decision", "specification", "build", "review", "test", "release", "adoption"]
SCENARIOS = ("low", "mid", "high")
LEVERS = ("ai_only", "ai_plus_process")
DEFS = ("idea_to_production_behind_flag", "idea_to_customer")
TARGET = 0.5  # board target: lead time at 50% of baseline
MONTHS = 18

# Tracker.
START = date(2026, 5, 1)  # month 1 of the synthetic data
SQUADS = ["intake_claims", "handling_payments", "suppliers_comms", "insight_reporting", "platform_access"]
PILOT = "intake_claims"
BASELINE_MONTHS = (1, 2, 3)  # items released in these months; current = items released in the last two months
BASELINE_DAYS = 180  # idea-to-adoption cycle used to turn shares into days (S18 6-month assumption)
COLS = ["item_id", "squad", "idea", "decision", "spec", "build_start", "pr_opened", "pr_merged",
        "tested", "flag_on", "customer_released", "adopted"]
FMT = "%Y-%m-%dT%H:%M:%S"


# ---------------------------------------------------------------- inputs

def load_inputs(path: Path = CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_inputs(inp: dict) -> list[str]:
    """Return a list of problems; empty means the inputs are usable."""
    errs = []

    def lab(name, d):
        if not isinstance(d, dict) or d.get("label") not in ("FOUND", "INFERRED"):
            errs.append(f"{name}: label must be FOUND or INFERRED")
        if not isinstance(d, dict) or not str(d.get("source", "")).strip():
            errs.append(f"{name}: source missing")

    for sec, d in (("stage_shares", inp.get("stage_shares")), ("ai_effect", inp.get("ai_effect")),
                   ("process_changes.effect", (inp.get("process_changes") or {}).get("effect"))):
        for s in STAGES:
            e = (d or {}).get(s)
            if e is None:
                errs.append(f"{sec}.{s}: missing")
                continue
            lab(f"{sec}.{s}", e)
            for sc in SCENARIOS:
                if not isinstance(e.get(sc), (int, float)):
                    errs.append(f"{sec}.{s}.{sc}: number missing")
    ramp = inp.get("adoption_ramp") or {}
    lab("adoption_ramp", ramp)
    for sc in SCENARIOS:
        if len(ramp.get(sc) or []) != MONTHS:
            errs.append(f"adoption_ramp.{sc}: need {MONTHS} monthly values")
    ph = (inp.get("process_changes") or {}).get("phase_in") or {}
    lab("process_changes.phase_in", ph)
    for sc in SCENARIOS:
        if not {"start_month", "months_to_full"} <= set(ph.get(sc) or {}):
            errs.append(f"process_changes.phase_in.{sc}: start_month and months_to_full needed")
    defs = inp.get("lead_time_definitions") or {}
    lab("lead_time_definitions", defs)
    for k in (*DEFS, "time_to_adoption"):
        if not set(defs.get(k) or ["?"]) <= set(STAGES):
            errs.append(f"lead_time_definitions.{k}: unknown or missing stages")
    if not errs:
        total = sum(inp["stage_shares"][s]["mid"] for s in STAGES)
        if abs(total - 1.0) > 1e-6:
            errs.append(f"stage_shares: mid shares sum to {total:.4f}, must be 1.0")
    return errs


def check_inputs(inp: dict) -> None:
    errs = validate_inputs(inp)
    if errs:
        sys.exit("halving_inputs.yaml is not valid:\n  " + "\n  ".join(errs))


# ---------------------------------------------------------------- model

def params_for(inp: dict, sc: str) -> dict:
    ph = inp["process_changes"]["phase_in"][sc]
    return {
        "shares": {s: inp["stage_shares"][s][sc] for s in STAGES},
        "ai": {s: inp["ai_effect"][s][sc] for s in STAGES},
        "proc": {s: inp["process_changes"]["effect"][s][sc] for s in STAGES},
        "ramp": list(inp["adoption_ramp"][sc]),
        "start": ph["start_month"], "full": ph["months_to_full"],
    }


def phase(start: int, full: int, month: int) -> float:
    return 0.0 if month < start else min(1.0, (month - start + 1) / full)


def index_series(p: dict, stages: list, process: bool = True) -> list:
    """Lead time as a fraction of baseline (1.0 = baseline) for each month 1..len(ramp)."""
    base = sum(p["shares"][s] for s in stages)
    out = []
    for m, ramp in enumerate(p["ramp"], start=1):
        ph = phase(p["start"], p["full"], m) if process else 0.0
        out.append(sum(p["shares"][s] * (1 + p["ai"][s] * ramp) * (1 + p["proc"][s] * ph) for s in stages) / base)
    return out


def first_crossing(series: list, target: float = TARGET):
    """First month (1-based) with index <= target, or None."""
    return next((m for m, v in enumerate(series, start=1) if v <= target + 1e-12), None)


def month_text(m) -> str:
    return f"month {m}" if m else f"not within {MONTHS} months"


def run_model(inp: dict) -> dict:
    """{(scenario, lever, definition): series}, plus (scenario, 'time_to_adoption') entries."""
    res = {}
    for sc in SCENARIOS:
        p = params_for(inp, sc)
        for lever in LEVERS:
            for d in DEFS:
                res[(sc, lever, d)] = index_series(p, inp["lead_time_definitions"][d], lever == "ai_plus_process")
        res[(sc, "ai_plus_process", "time_to_adoption")] = index_series(
            p, inp["lead_time_definitions"]["time_to_adoption"], True)
    return res


def sensitivity(inp: dict) -> list:
    """One-at-a-time swing in idea_to_customer index at month 18 (ai_plus_process), rest at mid.
    Returns [(name, low_value, high_value, index_at_low, index_at_high, swing)] sorted by swing."""
    stages = inp["lead_time_definitions"]["idea_to_customer"]
    base = params_for(inp, "mid")

    def at18(p):
        return index_series(p, stages, True)[-1]

    rows = []

    def add(name, setter, lo, hi):
        outs = []
        for v in (lo, hi):
            p = copy.deepcopy(base)
            setter(p, v)
            outs.append(at18(p))
        rows.append((name, lo, hi, outs[0], outs[1], abs(outs[1] - outs[0])))

    for s in stages:
        for key, label, sec in (("shares", "share", inp["stage_shares"]), ("ai", "AI effect", inp["ai_effect"]),
                                ("proc", "process effect", inp["process_changes"]["effect"])):
            add(f"{s} {label}", lambda p, v, k=key, s=s: p[k].__setitem__(s, v), sec[s]["low"], sec[s]["high"])
    add("adoption ramp level", lambda p, v: p.__setitem__("ramp", list(v)),
        inp["adoption_ramp"]["low"], inp["adoption_ramp"]["high"])
    rows.sort(key=lambda r: -r[5])
    return rows


def fmt_val(v) -> str:
    return f"{v[-1]:.2f}" if isinstance(v, list) else f"{v:+.2f}" if abs(v) < 0.6 and v != 0 else f"{v:.2f}"


def answer_sentence(inp: dict, res: dict) -> str:
    cross = {sc: first_crossing(res[(sc, "ai_plus_process", "idea_to_customer")]) for sc in SCENARIOS}
    m18 = {sc: res[(sc, "ai_plus_process", "idea_to_customer")][-1] for sc in SCENARIOS}
    ai18 = res[("mid", "ai_only", "idea_to_customer")][-1]
    z = f"if only AI is adopted without the process changes (AI alone leaves mid at {ai18:.0%} of baseline at month {MONTHS})"
    if cross["mid"]:
        lo = cross["low"] and f"month {cross['low']}" or f"later than month {MONTHS}"
        hi = cross["high"] and f"month {cross['high']}" or f"later than month {MONTHS}"
        return (f"Halving idea-to-customer is plausible by month {cross['mid']} (mid), between {hi} (high) "
                f"and {lo} (low), and does not happen {z}.")
    reach = (f"only the high scenario reaches it, at month {cross['high']}" if cross["high"]
             else "no scenario reaches it")
    return (f"Halving idea-to-customer is not plausible within {MONTHS} months in the mid scenario "
            f"(month-{MONTHS} index {m18['mid']:.0%} of baseline; low {m18['low']:.0%}, high {m18['high']:.0%}): "
            f"{reach}, and AI alone does not halve it (ai_only mid {ai18:.0%} at month {MONTHS}).")


def model_text(res: dict) -> str:
    cols = (1, 3, 6, 9, 12, 15, 18)
    lines = ["Lead time as % of baseline (100% = today), by month; first month at or below 50%.",
             f"{'scenario':<9}{'levers':<17}{'definition':<32}" + "".join(f"{'m' + str(c):>6}" for c in cols) + "  first <=50%"]
    for sc in SCENARIOS:
        for lever in LEVERS:
            for d in DEFS:
                s = res[(sc, lever, d)]
                lines.append(f"{sc:<9}{lever:<17}{d:<32}" + "".join(f"{s[c - 1]:>6.0%}" for c in cols)
                             + "  " + month_text(first_crossing(s)))
    lines.append("")
    lines.append("Time to adoption (adoption stage only, % of its baseline), month 18: "
                 + ", ".join(f"{sc} {res[(sc, 'ai_plus_process', 'time_to_adoption')][-1]:.0%}" for sc in SCENARIOS))
    return "\n".join(lines)


def sens_text(rows: list) -> str:
    lines = [f"Sensitivity: swing in idea_to_customer index at month {MONTHS} (ai_plus_process, others at mid), top 5.",
             f"{'input':<36}{'low':>8}{'high':>8}{'index@low':>11}{'index@high':>12}{'swing':>8}"]
    for n, lo, hi, il, ih, sw in rows[:5]:
        lines.append(f"{n:<36}{fmt_val(lo):>8}{fmt_val(hi):>8}{il:>11.0%}{ih:>12.0%}{sw * 100:>7.1f}pt")
    lines.append(f"The two inputs that move the answer most: {rows[0][0]}; {rows[1][0]}.")
    return "\n".join(lines)


# ---------------------------------------------------------------- synthetic data

def pilot_multiplier(inp: dict, stage: str, month: int) -> float:
    """Pilot squad stage-time multiplier: mid ai_plus_process effects, clock starts at month 4."""
    if month < 4:
        return 1.0
    k = month - 3
    p = params_for(inp, "mid")
    return (1 + p["ai"][stage] * p["ramp"][k - 1]) * (1 + p["proc"][stage] * phase(1, p["full"], k))


def generate(path: Path, inp: dict, months: int = 6, sigma: float = 0.25) -> int:
    rng = random.Random(42)
    shares = {s: inp["stage_shares"][s]["mid"] for s in STAGES}
    rows = []
    for si, squad in enumerate(SQUADS):
        for m in range(1, months + 1):
            mult = {s: pilot_multiplier(inp, s, m) if squad == PILOT else 1 - 0.003 * (m - 1) for s in STAGES}
            avg = sum(shares[s] * mult[s] for s in STAGES)
            # shortcut: pilot gain applies to items by release month, not start month; real gains lag, upgrade with real data.
            # throughput follows Little's law at fixed work in progress: faster flow, more items.
            n = round(rng.randint(25, 40) / avg)
            first = date(START.year + (START.month + m - 2) // 12, (START.month + m - 2) % 12 + 1, 1)
            nxt = date(first.year + first.month // 12, first.month % 12 + 1, 1)
            span = (nxt - first).days * 86400
            for _ in range(n):
                rel = datetime.combine(first, datetime.min.time()) + timedelta(seconds=rng.randrange(span))
                dur = {s: BASELINE_DAYS * shares[s] * mult[s] * rng.lognormvariate(-sigma ** 2 / 2, sigma) for s in STAGES}
                t = {"customer_released": rel}
                t["flag_on"] = rel - timedelta(days=dur["release"])
                t["adopted"] = rel + timedelta(days=dur["adoption"])
                t["tested"] = t["flag_on"]
                t["pr_merged"] = t["tested"] - timedelta(days=dur["test"])
                t["pr_opened"] = t["pr_merged"] - timedelta(days=dur["review"])
                t["build_start"] = t["pr_opened"] - timedelta(days=dur["build"])
                t["spec"] = t["build_start"]  # shortcut: no queue between sign-off and build start, add one with real data
                t["decision"] = t["spec"] - timedelta(days=dur["specification"])
                t["idea"] = t["decision"] - timedelta(days=dur["discovery_decision"])
                rows.append((squad, rel, {k: v.strftime(FMT) for k, v in t.items()}))
    rows.sort(key=lambda r: (r[0], r[1]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLS)
        for i, (squad, _, t) in enumerate(rows, start=1):
            w.writerow([f"ITEM-{i:05d}", squad] + [t[c] for c in COLS[2:]])
    return len(rows)


# ---------------------------------------------------------------- tracker

def read_items(path: Path) -> list:
    out = []
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            t = {c: datetime.strptime(r[c], FMT) for c in COLS[2:]}
            rel = t["customer_released"]
            out.append({"squad": r["squad"], "month": (rel.year - START.year) * 12 + rel.month - START.month + 1,
                        "behind_flag": (t["flag_on"] - t["idea"]).total_seconds() / 86400,
                        "customer": (rel - t["idea"]).total_seconds() / 86400})
    return out


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def track(items: list) -> dict:
    """Baseline = items released in months 1-3; current = items released in the last two months present."""
    last = max(i["month"] for i in items)
    cur_months = (last - 1, last)
    squads = sorted({i["squad"] for i in items})
    lt_rows, tp_rows, monthly = [], [], {}
    for g in ["overall"] + squads:
        sel = [i for i in items if g == "overall" or i["squad"] == g]
        for key, name in (("behind_flag", "idea_to_production_behind_flag"), ("customer", "idea_to_customer")):
            b = statistics.median(i[key] for i in sel if i["month"] in BASELINE_MONTHS)
            c = statistics.median(i[key] for i in sel if i["month"] in cur_months)
            raw = (b - c) / (b * 0.5)
            lt_rows.append((g, name, b, c, raw, clamp(raw)))
        n_sq = 1 if g != "overall" else len(squads)
        b = sum(1 for i in sel if i["month"] in BASELINE_MONTHS) / len(BASELINE_MONTHS) / n_sq
        c = sum(1 for i in sel if i["month"] in cur_months) / len(cur_months) / n_sq
        raw = (c - b) / b
        tp_rows.append((g, b, c, raw, clamp(raw)))
    base = next(r[2] for r in lt_rows if r[0] == "overall" and r[1] == "idea_to_customer")
    for m in range(1, last + 1):
        if any(i["month"] == m for i in items):
            monthly[m] = statistics.median(i["customer"] for i in items if i["month"] == m) / base
    per_month = {g: [sum(1 for i in items if i["squad"] == g and i["month"] == m) for m in range(1, last + 1)]
                 for g in squads}
    return {"last": last, "cur_months": cur_months, "lt": lt_rows, "tp": tp_rows, "monthly": monthly,
            "per_month": per_month}


def tracker_text(t: dict) -> str:
    c0, c1 = t["cur_months"]
    L = [f"Tracker. Baseline: items released in months {BASELINE_MONTHS[0]}-{BASELINE_MONTHS[-1]} "
         f"(median lead time; throughput = mean items per squad per month). Current: items released in months {c0}-{c1}.",
         "Progress = (baseline - current) / (baseline x 0.5) for lead time; (current - baseline) / baseline for throughput "
         "(target +100%). Shown value is clamped to 0-100%; raw is unclamped.", "",
         f"{'group':<19}{'lead time':<33}{'baseline d':>11}{'current d':>10}{'raw':>8}{'shown':>7}"]
    for g, name, b, c, raw, shown in t["lt"]:
        L.append(f"{g:<19}{name:<33}{b:>11.1f}{c:>10.1f}{raw:>8.1%}{shown:>7.0%}")
    L += ["", f"{'group':<19}{'throughput (items/squad/month)':<33}{'baseline':>11}{'current':>10}{'raw':>8}{'shown':>7}"]
    for g, b, c, raw, shown in t["tp"]:
        L.append(f"{g:<19}{'':<33}{b:>11.1f}{c:>10.1f}{raw:>8.1%}{shown:>7.0%}")
    L += ["", "Items released per squad per month: " + " ".join(f"m{m}" for m in range(1, t["last"] + 1))]
    for g, counts in t["per_month"].items():
        L.append(f"{g:<19}" + " ".join(f"{n:>3}" for n in counts))
    L += ["", "Overall median idea_to_customer / baseline, by month: "
          + ", ".join(f"m{m} {v:.0%}" for m, v in t["monthly"].items())]
    return "\n".join(L)


# ---------------------------------------------------------------- outputs

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d3"
COLOURS = {"low": "#eb6834", "mid": "#2a78d6", "high": "#1baf7a"}  # reference categorical slots 2, 1, 3


def chart_title(res: dict) -> str:
    c = {sc: first_crossing(res[(sc, "ai_plus_process", "idea_to_customer")]) for sc in SCENARIOS}
    m = {sc: res[(sc, "ai_plus_process", "idea_to_customer")][-1] for sc in SCENARIOS}
    if c["mid"]:
        return f"Idea-to-customer time halves by month {c['mid']} (mid), but only with process change"
    if c["high"]:
        return f"Idea-to-customer time halves only in the high case (month {c['high']})"
    return f"Idea-to-customer time does not halve in {MONTHS} months; best case {m['high']:.0%} of today's"


def write_chart(res: dict, tracker: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = "idea_to_customer"
    xs = list(range(1, MONTHS + 1))
    lines = [(f"{sc.capitalize()}", [v * 100 for v in res[(sc, "ai_plus_process", d)]], COLOURS[sc], "-") for sc in SCENARIOS]
    ai = [v * 100 for v in res[("mid", "ai_only", d)]]
    lines.append(("AI only (mid)", ai, MUTED, "--"))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
    fig, ax = plt.subplots(figsize=(12, 6.6), dpi=170)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(MUTED)
    ax.axhline(50, color=INK, linewidth=1.5)
    ax.text(0.7, 49.2, "Board target: 50% of today's lead time", color=INK, fontsize=13, fontweight="bold", va="top")
    for name, ys, col, ls in lines:
        ax.plot(xs, ys, color=col, linestyle=ls, linewidth=2.6, solid_capstyle="round")
        ax.plot([xs[-1]], [ys[-1]], "o", color=col, markersize=8, markeredgecolor="white", markeredgewidth=1.5)
    # Direct labels at month 18, pushed apart so they cannot overlap.
    ends = sorted(((ys[-1], name) for name, ys, _, _ in lines), reverse=True)
    prev = None
    for y, name in ends:
        ty = y if prev is None else min(y, prev - 4.2)
        ax.text(MONTHS + 0.45, ty, f"{name} {y:.0f}%", color=INK, fontsize=13, va="center")
        prev = ty
    pts = tracker["monthly"] if tracker else {}
    if pts:
        ax.plot(list(pts), [v * 100 for v in pts.values()], "o", color=INK, markersize=9,
                markeredgecolor="white", markeredgewidth=1.5, zorder=5)
        mx = list(pts)[2]
        ax.annotate("Tracker actuals\n(synthetic data)", xy=(mx, pts[mx] * 100), xytext=(mx - 0.2, pts[mx] * 100 + 9),
                    color=INK, fontsize=12, ha="center", va="bottom",
                    arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 1})
    lo = min(35, min(min(ys) for _, ys, _, _ in lines) - 5)
    hi = max(110, max(max(ys) for _, ys, _, _ in lines) + 6)
    ax.set_ylim(lo, hi)
    ax.set_xlim(0.5, MONTHS + 0.5)
    ax.set_xticks([1, 3, 6, 9, 12, 15, 18])
    ax.tick_params(colors=MUTED, labelsize=13)
    ax.set_xlabel("Months from the start of the programme (month 1 = May 2026)", color=MUTED, fontsize=13)
    ax.set_ylabel("Lead time, % of today's median (100% = baseline)", color=MUTED, fontsize=13)
    fig.suptitle(chart_title(res), x=0.02, ha="left", fontsize=17, fontweight="bold", color=INK)
    fig.text(0.02, 0.905, "Idea to customer, AI plus process changes (solid) against AI alone (dashed). "
             "Inputs are mostly INFERRED; see config/halving_inputs.yaml.", fontsize=12, color=MUTED, ha="left")
    fig.subplots_adjust(left=0.08, right=0.84, top=0.85, bottom=0.11)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "halving.svg", metadata={"Date": None})
    fig.savefig(out_dir / "halving.png", metadata={"Software": None})
    plt.close(fig)


def summary_md(inp: dict, res: dict, sens: list, t) -> str:
    d = "idea_to_customer"
    L = ["# Halving model: summary", "", "Synthetic company, invented data. Inputs are labelled FOUND or INFERRED in "
         "`config/halving_inputs.yaml`; most are INFERRED.", "", "## Answer", "", answer_sentence(inp, res), "",
         "## First month at or below 50% of baseline", "",
         "| Scenario | Levers | idea_to_production_behind_flag | idea_to_customer | idea_to_customer at month 18 |",
         "|---|---|---|---|---|"]
    for sc in SCENARIOS:
        for lv in LEVERS:
            a, b = (res[(sc, lv, k)] for k in DEFS)
            L.append(f"| {sc} | {lv} | {month_text(first_crossing(a))} | {month_text(first_crossing(b))} | {b[-1]:.0%} |")
    L += ["", "## Most sensitive inputs", "",
          f"Swing in the month-{MONTHS} idea_to_customer index (ai_plus_process), moving one input from its low to its high "
          f"value with the rest at mid. The two that move the answer most: **{sens[0][0]}** and **{sens[1][0]}**.", "",
          "| Input | Low | High | Index at low | Index at high | Swing |", "|---|---|---|---|---|---|"]
    for n, lo, hi, il, ih, sw in sens[:5]:
        L.append(f"| {n} | {fmt_val(lo)} | {fmt_val(hi)} | {il:.0%} | {ih:.0%} | {sw * 100:.1f} pt |")
    L += ["", "## Tracker status", ""]
    if t:
        c0, c1 = t["cur_months"]
        L += [f"Baseline is items released in months {BASELINE_MONTHS[0]}-{BASELINE_MONTHS[-1]}; current is items released in "
              f"months {c0}-{c1}. Shown percentages are clamped to 0-100%; raw is unclamped.", "",
              "| Group | Measure | Baseline | Current | Raw | Of the way to target |", "|---|---|---|---|---|---|"]
        for g, name, b, c, raw, shown in t["lt"]:
            if g == "overall" or g == PILOT:
                L.append(f"| {g} | {name} (days) | {b:.1f} | {c:.1f} | {raw:.1%} | {shown:.0%} |")
        for g, b, c, raw, shown in t["tp"]:
            if g == "overall" or g == PILOT:
                L.append(f"| {g} | throughput (items per squad per month) | {b:.1f} | {c:.1f} | {raw:.1%} | {shown:.0%} |")
        L.append("\nFull tables are in `reports/halving/tracker.md`.")
    else:
        L.append("No tracker data found; run `--generate` first.")
    L += ["", "![Lead time by month](halving.png)", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- cli

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Halving model and board tracker (invented data).")
    ap.add_argument("--generate", action="store_true", help="write synthetic items.csv (seed 42)")
    ap.add_argument("--track", nargs="?", const=str(ITEMS), metavar="CSV", help="report tracker progress from an items csv")
    ap.add_argument("--outputs", "--chart", action="store_true", help="write halving.svg, halving.png, summary.md, tracker.md")
    ap.add_argument("--items", default=str(ITEMS), help="items csv for --generate and --outputs")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args(argv)
    inp = load_inputs(Path(a.config))
    check_inputs(inp)
    out_dir = Path(a.out_dir)
    if a.generate:
        print(f"wrote {generate(Path(a.items), inp)} items to {a.items}")
    t = None
    if a.track or (a.outputs and Path(a.items).exists()):
        t = track(read_items(Path(a.track or a.items)))
        if a.track:
            print(tracker_text(t))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "tracker.md").write_text(
            "# Tracker\n\n```\n" + tracker_text(t) + "\n```\n", encoding="utf-8", newline="\n")
    if (a.generate or a.track) and not a.outputs:
        return
    res = run_model(inp)
    sens = sensitivity(inp)
    print(model_text(res), "", sens_text(sens), "", answer_sentence(inp, res), sep="\n")
    if a.outputs:
        write_chart(res, t, out_dir)
        (out_dir / "summary.md").write_text(summary_md(inp, res, sens, t), encoding="utf-8", newline="\n")
        print(f"wrote halving.svg, halving.png, summary.md in {out_dir}")


if __name__ == "__main__":
    main()
