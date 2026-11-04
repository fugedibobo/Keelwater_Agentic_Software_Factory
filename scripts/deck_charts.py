"""SVG strings for the presentation deck (site/presentation/index.html), built from the repo's own files.

Run: uv run python scripts/deck_charts.py   (prints the size of each chart)
Only the standard library is used here; the halving series come from scripts/halving_model.py (repo code).
Colours are CSS variables defined in the deck: --ink, --ink2, --grid, --c1 (blue), --c2 (orange), --surface.
"""
import csv
import sys
import zlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _svg(w, h, title, desc, body, defs=""):
    i = "t" + str(zlib.crc32(title.encode()))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{i}" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{i}">{title}</title><desc>{desc}</desc>{defs}{body}</svg>')


def halving_series():
    import halving_model as hm
    res = hm.run_model(hm.load_inputs())
    d = "idea_to_customer"
    return {
        "Low": [v * 100 for v in res[("low", "ai_plus_process", d)]],
        "Mid": [v * 100 for v in res[("mid", "ai_plus_process", d)]],
        "High": [v * 100 for v in res[("high", "ai_plus_process", d)]],
        "AI only (mid)": [v * 100 for v in res[("mid", "ai_only", d)]],
    }


def halving_chart():
    s = halving_series()
    W, H, L, R, T, B = 960, 470, 70, 760, 16, 400
    X = lambda m: L + (m - 1) / 17 * (R - L)
    Y = lambda v: T + (110 - v) / 70 * (B - T)
    style = {"Low": ("ink2", ""), "Mid": ("c1", ""), "High": ("c2", ""), "AI only (mid)": ("c1", ' stroke-dasharray="9 6"')}
    out = []
    for v in range(40, 111, 10):
        out.append(f'<line class="gr" x1="{L}" x2="{R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                   f'<text class="tk" x="{L - 10}" y="{Y(v) + 5:.1f}" text-anchor="end">{v}%</text>')
    for m in (1, 3, 6, 9, 12, 15, 18):
        out.append(f'<text class="tk" x="{X(m):.1f}" y="{B + 24}" text-anchor="middle">{m}</text>')
    out.append(f'<text class="tk" x="{(L + R) / 2:.0f}" y="{B + 54}" text-anchor="middle">'
               'Months from the start of the programme (month 1 = May 2026)</text>')
    out.append(f'<line class="tg" x1="{L}" x2="{R}" y1="{Y(50):.1f}" y2="{Y(50):.1f}"/>'
               f'<text class="tl" x="{X(7):.1f}" y="{Y(50) + 24:.1f}">Board target: 50% of today&#39;s lead time</text>')
    ends = []
    for name, ys in s.items():
        col, dash = style[name]
        pts = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in enumerate(ys, start=1))
        out.append(f'<polyline class="ln {col}" fill="none"{dash} points="{pts}"/>')
        out.append(f'<circle class="dot {col}" cx="{X(18):.1f}" cy="{Y(ys[-1]):.1f}" r="5"/>')
        ends.append((ys[-1], name))
    prev = None
    for v, name in sorted(ends, reverse=True):
        y = Y(v) if prev is None else max(Y(v), prev + 22)
        out.append(f'<text class="tl" x="{R + 16}" y="{y + 5:.1f}">{name} {v:.0f}%</text>')
        prev = y
    return _svg(W, H, "Idea-to-customer lead time over 18 months, four model cases",
                "Lines show lead time as a percentage of today's. At month 18: Low 99%, AI only on mid inputs 95%, Mid 79%, High 51%. "
                "Only the High case approaches the 50% board target and none reaches it.", "".join(out))


def delegation_chart():
    # The figures printed in docs/delegation.md section 9 (the script's own last digit can differ by one cent between platforms).
    import re
    doc = (ROOT / "docs" / "delegation.md").read_text(encoding="utf-8")
    allo = float(re.search(r"All Opus 5\.5 : ([\d.]+) USD", doc).group(1))
    routed = float(re.search(r"Routed\s+: ([\d.]+) USD", doc).group(1))
    W, H, X0, SC = 960, 190, 210, 520 / 1142.0
    rows = [("All Opus 5.5", allo, "ink2"), ("Routed by class", routed, "c1")]
    out = []
    for i, (name, v, col) in enumerate(rows):
        y = 16 + i * 66
        out.append(f'<text class="tl" x="0" y="{y + 32}">{name}</text>'
                   f'<rect class="bar {col}" x="{X0}" y="{y}" width="{v * SC:.1f}" height="48" rx="3"/>'
                   f'<text class="tl" x="{X0 + v * SC + 14:.1f}" y="{y + 32}">{v:,.2f} USD a day</text>')
    out.append(f'<text class="tk" x="{X0}" y="172">100 tasks a day. INFERRED: list-price arithmetic, not a measurement.</text>')
    return _svg(W, H, "Delegation cost scenario, USD a day",
                f"All Opus 5.5 costs {allo:,.2f} USD a day; routed by task class costs {routed:,.2f} USD a day. INFERRED.", "".join(out))


def telemetry_rows():
    d = defaultdict(lambda: {"measured": 0, "estimated": 0, "none": 0})
    with open(ROOT / "reports" / "factory" / "build-telemetry.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            b, t = r["tokens_basis"], r["tokens_total"]
            if b in ("measured", "estimated"):
                d[r["engine"]][b] += int(t)
            else:
                d[r["engine"]]["none"] += 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]["measured"]))


def telemetry_chart():
    d = telemetry_rows()
    W, X0, SC = 960, 90, 500 / 3_555_000
    H = 50 + 84 * len(d)
    defs = ('<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            '<rect width="7" height="7" class="sf"/><line x1="0" y1="0" x2="0" y2="7" class="hl"/></pattern></defs>')
    out = [f'<text class="tk" x="{W - 8}" y="18" text-anchor="end">Rows with no token figure (one square each)</text>']
    for i, (eng, v) in enumerate(d.items()):
        y = 36 + i * 84
        out.append(f'<text class="tl" x="0" y="{y + 36}">{eng}</text>')
        for j, (key, cls) in enumerate((("measured", "c1"), ("estimated", "est"))):
            yy = y + j * 34
            w = max(v[key] * SC, 3)
            if v[key]:
                out.append(f'<rect class="bar {cls}" x="{X0}" y="{yy}" width="{w:.1f}" height="26" rx="3"/>')
                out.append(f'<text class="tk" x="{X0 + w + 10:.1f}" y="{yy + 19}">{v[key]:,} {key}</text>')
            else:
                out.append(f'<text class="tk" x="{X0 + 4}" y="{yy + 19}">0 {key}</text>')
        for k in range(v["none"]):
            out.append(f'<rect class="nr" x="{W - 24 - k * 24}" y="{y + 18}" width="18" height="18" rx="2"/>')
    return _svg(W, H, "Tokens per engine on this build, measured and estimated apart",
                "Measured tokens, estimated tokens and the count of rows with no figure, per engine, from the build telemetry file. "
                + "; ".join(f"{e}: {v['measured']:,} measured, {v['estimated']:,} estimated, {v['none']} rows not reported"
                            for e, v in d.items()) + ".", "".join(out), defs)


CSS = """.chart{width:100%;height:auto;display:block}
.chart text{font-family:inherit}
.chart .tk{font-size:15px;line-height:1.5;fill:var(--ink2)}.chart .tl{font-size:17px;line-height:1.5;font-weight:600;fill:var(--ink)}
.chart .gr{stroke:var(--grid);stroke-width:1}.chart .tg{stroke:var(--ink);stroke-width:2;stroke-dasharray:2 5}
.chart .ln{stroke-width:3.5;stroke-linecap:round;stroke-linejoin:round;fill:none}
.chart .ln.c1{stroke:var(--c1)}.chart .ln.c2{stroke:var(--c2)}.chart .ln.ink2{stroke:var(--ink2)}
.chart .dot.c1,.chart .bar.c1{fill:var(--c1)}.chart .dot.c2{fill:var(--c2)}.chart .dot.ink2,.chart .bar.ink2{fill:var(--ink2)}
.chart .bar.est{fill:url(#hatch);stroke:var(--c2);stroke-width:1.5}
.chart .sf{fill:var(--surface)}.chart .hl{stroke:var(--c2);stroke-width:2}
.chart .nr{fill:none;stroke:var(--ink2);stroke-width:1.5;stroke-dasharray:3 2}"""

if __name__ == "__main__":
    for fn in (halving_chart, delegation_chart, telemetry_chart):
        print(fn.__name__, len(fn()))
