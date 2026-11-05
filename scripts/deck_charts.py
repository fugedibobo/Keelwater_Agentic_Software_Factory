"""SVG charts and generated tables for the presentation deck, built from the repo's own files.

scripts/build_deck.py puts these into scripts/deck_template.html and writes site/presentation/index.html.
Run: uv run python scripts/deck_charts.py   (prints the size of each piece)

Colours and type sizes are CSS classes and variables defined in the deck template, so light and dark both work:
  --ink, --ink2, --mute, --grid, --rule, --surface, --accent, --tint, --good, --bad, --on-accent.
Sources: halving series from scripts/halving_model.py; results from reports/eval via scripts/readme_sections.py
(the same report ids the README cites); tokens and cost from the table in docs/ai-usage.md (built by scripts/measure_tokens.py).
"""
import re
import sys
import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _svg(w, h, title, desc, body, extra_defs=""):
    i = "t" + str(zlib.crc32(title.encode()))
    m = "m" + i
    defs = (f'<defs><marker id="{m}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
            f'<path d="M0 0 10 5 0 10z" class="mk"/></marker>'
            f'<pattern id="h{i}" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<rect width="8" height="8" class="hf"/><line x1="0" y1="0" x2="0" y2="8" class="hl"/></pattern>{extra_defs}</defs>')
    body = body.replace("MARK", f"url(#{m})").replace("HATCH", f"url(#h{i})")
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{i}" preserveAspectRatio="xMidYMid meet">'
            f'<title id="{i}">{esc(title)}</title><desc>{esc(desc)}</desc>{defs}{body}</svg>')


def lines(x, y, text, cls, width, step, anchor="start"):
    """Wrapped text as tspans: width in characters, step is the line height."""
    out = [f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">']
    for k, ln in enumerate(textwrap.wrap(text, width)):
        out.append(f'<tspan x="{x}" dy="{0 if k == 0 else step}">{esc(ln)}</tspan>')
    out.append("</text>")
    return "".join(out)


# ---------------------------------------------------------------- slide 1: where the time goes
def leadtime_chart():
    # Figures: docs/part1-diagnosis-and-plan.md, "The point": coding and testing 25-35% of idea-to-launch time;
    # halving needs 50 points, so about 20 must come from elsewhere even at zero build time.
    X0, X1 = 330, 1280
    X = lambda p: X0 + p / 100 * (X1 - X0)
    BH = 64
    o = []
    for p in (0, 25, 50, 75, 100):
        o.append(f'<line class="gr" x1="{X(p):.0f}" x2="{X(p):.0f}" y1="14" y2="340"/>'
                 f'<text class="tk" x="{X(p):.0f}" y="368" text-anchor="middle">{p}</text>')
    o.append('<text class="ts" x="0" y="368">Points of today&#39;s time</text>')
    y = 48  # bar A: today
    o.append(f'<text class="tl" x="0" y="{y + 40}">Today: all of it</text>')
    o.append(f'<text class="ts" x="{X(0):.0f}" y="{y - 12}">Coding and testing: 25 to 35 points</text>')
    o.append(f'<rect class="fa" x="{X(0):.0f}" y="{y}" width="{X(25) - X(0):.0f}" height="{BH}"/>'
             f'<rect x="{X(25):.0f}" y="{y}" width="{X(35) - X(25):.0f}" height="{BH}" fill="HATCH"/>'
             f'<rect class="fr" x="{X(35):.0f}" y="{y}" width="{X(100) - X(35):.0f}" height="{BH}"/>')
    o.append(f'<text class="tw" x="{X(12.5):.0f}" y="{y + 41}" text-anchor="middle">Coding, testing</text>')
    o.append(f'<text class="tl" x="{X(67.5):.0f}" y="{y + 28}" text-anchor="middle">Decide, define, release, enable</text>'
             f'<text class="ts" x="{X(67.5):.0f}" y="{y + 54}" text-anchor="middle">65 to 75 points</text>')
    y = 160  # bar B: needed
    o.append(f'<text class="tl" x="0" y="{y + 40}">Cut needed to halve</text>')
    o.append(f'<rect class="fb" x="{X(0):.0f}" y="{y}" width="{X(50) - X(0):.0f}" height="{BH}"/>'
             f'<text class="tl" x="{X(25):.0f}" y="{y + 41}" text-anchor="middle">50 points</text>')
    y = 272  # bar C: free code
    o.append(f'<text class="tl" x="0" y="{y + 40}">Most free code can cut</text>')
    o.append(f'<rect class="gap" x="{X(25):.0f}" y="{y}" width="{X(50) - X(25):.0f}" height="{BH}" rx="3"/>'
             f'<rect class="fa" x="{X(0):.0f}" y="{y}" width="{X(25) - X(0):.0f}" height="{BH}"/>'
             f'<rect x="{X(25):.0f}" y="{y}" width="{X(35) - X(25):.0f}" height="{BH}" fill="HATCH"/>'
             f'<text class="tw" x="{X(12.5):.0f}" y="{y + 41}" text-anchor="middle">25 to 35</text>'
             f'<text class="tl" x="{X(42.5):.0f}" y="{y + 28}" text-anchor="middle">15 to 25</text>'
             f'<text class="ts" x="{X(42.5):.0f}" y="{y + 54}" text-anchor="middle">still to find</text>')
    return _svg(1300, 380, "Where idea-to-launch time goes, and what free code can cut",
                "Three bars on one scale of points of today's idea-to-launch time. Coding and testing are 25 to 35 points. "
                "Halving needs a cut of 50 points. Removing all coding and testing cuts at most 25 to 35 points, "
                "so 15 to 25 points must come from deciding, defining, releasing and enabling.", "".join(o))


# ---------------------------------------------------------------- slide 2: lifecycle with five gates
def lifecycle_diagram():
    # Stages and gates: docs/part1-diagnosis-and-plan.md section 2 (seven stages, five gates, who passes each).
    names = ["Sense", "Decide", "Define", "Build", "Release", "Enable", "Learn"]
    gates = {1: "PM accepts", 2: "Trio signs off", 3: "Engineer merges", 4: "Bundle approved", 5: "Drafts accepted"}
    BW, GAP, BY, BH = 128, 67, 84, 66
    xs = [i * (BW + GAP) for i in range(7)]
    mid = BY + BH / 2
    o = []
    lx0, lx1 = xs[6] + BW / 2, xs[0] + BW / 2
    o.append(f'<path class="arr dsh" d="M{lx0} {BY} V36 H{lx1} V{BY - 4}" marker-end="MARK" fill="none"/>')
    o.append(f'<rect class="bgrect" x="{(lx0 + lx1) / 2 - 190}" y="16" width="380" height="40"/>'
             f'<text class="ts" x="{(lx0 + lx1) / 2}" y="43" text-anchor="middle">Outcomes feed the next signals</text>')
    for i, name in enumerate(names):
        x = xs[i]
        o.append(f'<rect class="box" x="{x}" y="{BY}" width="{BW}" height="{BH}" rx="8"/>'
                 f'<text class="tl" x="{x + BW / 2}" y="{mid + 8}" text-anchor="middle">{name}</text>')
        if i < 6:
            gx0, gx1 = x + BW, xs[i + 1]
            if i == 0:
                o.append(f'<line class="arr" x1="{gx0 + 4}" x2="{gx1 - 4}" y1="{mid}" y2="{mid}" marker-end="MARK"/>')
            else:
                cx = (gx0 + gx1) / 2
                o.append(f'<line class="arr" x1="{gx0 + 3}" x2="{cx - 21}" y1="{mid}" y2="{mid}"/>'
                         f'<line class="arr" x1="{cx + 21}" x2="{gx1 - 4}" y1="{mid}" y2="{mid}" marker-end="MARK"/>'
                         f'<circle class="gate" cx="{cx}" cy="{mid}" r="19"/>'
                         f'<text class="gn" x="{cx}" y="{mid + 8}" text-anchor="middle">{i}</text>'
                         f'<line class="tick" x1="{cx}" x2="{cx}" y1="{mid + 22}" y2="188"/>'
                         f'<text class="tl" x="{cx}" y="216" text-anchor="middle">Gate {i}</text>'
                         f'<text class="tg2" x="{cx}" y="244" text-anchor="middle">{gates[i]}</text>')
    o.append(f'<rect class="sw" x="2" y="274" width="24" height="24" rx="4"/>'
             f'<text class="ts" x="38" y="294">Stage: agents read, draft and check</text>'
             f'<circle class="gate" cx="540" cy="286" r="13"/>'
             f'<text class="ts" x="562" y="294">Gate: a named person decides</text>')
    return _svg(1300, 316, "The agentic product lifecycle: seven stages and five human gates",
                "Sense, Decide, Define, Build, Release, Enable and Learn in a row, with five gates between them. "
                "Gate 1 after Decide: the PM accepts the opportunity. Gate 2: the Trio signs off the intent document and mockup. "
                "Gate 3: an engineer merges the pull request. Gate 4: PM and customer success approve the release bundle. "
                "Gate 5: product marketing accepts the drafts. Learn feeds outcomes back to Sense.", "".join(o))


# ---------------------------------------------------------------- slide 3: delegation
def delegation_diagram():
    # Roles and phases: docs/delegation.md sections 2 and 6 (Now: Opus orchestrates; Sonnet, Haiku and Codex GPT-6.1 Terra build;
    # Codex GPT-6.1 Sol reviews as the other family. Back pocket: GLM 5.3 builds; DeepSeek V4.1 Flash or Qwen3.8 checks).
    o = ['<rect class="boxa" x="0" y="66" width="250" height="110" rx="10"/>'
         '<text class="twb" x="125" y="114" text-anchor="middle">Opus 5.5</text>'
         '<text class="tw" x="125" y="150" text-anchor="middle">orchestrates</text>']
    ys = [6, 86, 166]
    for (n, r), y in zip((("Sonnet 5.5", "builds"), ("Haiku 5.5", "builds"), ("Codex Terra", "builds")), ys):
        o.append(f'<path class="arr" d="M250 121 H290 V{y + 33} H326" marker-end="MARK" fill="none"/>')
        o.append(f'<rect class="box" x="330" y="{y}" width="300" height="66" rx="10"/>'
                 f'<text class="tl" x="350" y="{y + 42}">{n}</text><text class="ts" x="610" y="{y + 42}" text-anchor="end">{r}</text>')
        o.append(f'<path class="arr" d="M630 {y + 33} H672 V121 H716" fill="none"/>')
    o.append('<path class="arr" d="M672 121 H716" marker-end="MARK" fill="none"/>')
    o.append('<rect class="boxt" x="720" y="66" width="270" height="110" rx="10"/>'
             '<text class="tl" x="855" y="114" text-anchor="middle">Codex Sol</text>'
             '<text class="ts" x="855" y="146" text-anchor="middle">checks</text>')
    o.append('<path class="arr" d="M990 121 H1050" marker-end="MARK" fill="none"/>'
             '<rect class="box" x="1054" y="66" width="246" height="110" rx="10"/>'
             '<text class="tl" x="1177" y="114" text-anchor="middle">A person</text>'
             '<text class="ts" x="1177" y="146" text-anchor="middle">merges</text>')
    o.append('<rect class="dash" x="0" y="258" width="1300" height="130" rx="12"/>'
             '<text class="tl" x="20" y="294">Back pocket: the open stack, no tasks yet, for shadow comparison later</text>')
    for x, n, w in ((20, "GLM 5.3 builds", 330), (380, "DeepSeek V4.1 Flash checks", 450), (860, "Qwen3.8 checks", 420)):
        o.append(f'<rect class="chip" x="{x}" y="312" width="{w}" height="58" rx="8"/>'
                 f'<text class="tl" x="{x + 18}" y="349">{n}</text>')
    return _svg(1300, 394, "Delegation: Opus orchestrates, cheaper models build, Codex Sol checks, the open stack waits",
                "Opus 5.5 orchestrates and sends tasks to three builders: Sonnet 5.5, Haiku 5.5 and Codex GPT-6.1 Terra. "
                "Their pull requests go to Codex GPT-6.1 Sol for adversarial review by the other model family, then a person merges. "
                "In the back pocket, not yet routing tasks, the open stack: GLM 5.3 as builder, DeepSeek V4.1 Flash and Qwen3.8 as checkers, "
                "for a later shadow comparison.", "".join(o))


# ---------------------------------------------------------------- slide 4: halving
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
    W, H, L, R, T, B = 1300, 372, 84, 1000, 12, 288
    X = lambda m: L + (m - 1) / 17 * (R - L)
    Y = lambda v: T + (110 - v) / 70 * (B - T)
    style = {"Low": ("mute", ""), "Mid": ("accent", ""), "High": ("ink", ""), "AI only (mid)": ("accent", ' stroke-dasharray="10 7"')}
    out = []
    for v in range(40, 111, 10):
        out.append(f'<line class="gr" x1="{L}" x2="{R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                   f'<text class="tk" x="{L - 12}" y="{Y(v) + 7:.1f}" text-anchor="end">{v}%</text>')
    for m in (1, 3, 6, 9, 12, 15, 18):
        out.append(f'<text class="tk" x="{X(m):.1f}" y="{B + 30}" text-anchor="middle">{m}</text>')
    out.append(f'<text class="tk" x="{(L + R) / 2:.0f}" y="{B + 62}" text-anchor="middle">'
               'Months from the start of the programme (month 1 = May 2026)</text>')
    out.append(f'<line class="tgt" x1="{L}" x2="{R}" y1="{Y(50):.1f}" y2="{Y(50):.1f}"/>'
               f'<text class="tl" x="{X(1.4):.1f}" y="{Y(50) + 28:.1f}">Board target: 50% of today&#39;s lead time</text>')
    ends = []
    for name, ys in s.items():
        col, dash = style[name]
        pts = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in enumerate(ys, start=1))
        out.append(f'<polyline class="ln {col}" fill="none"{dash} points="{pts}"/>')
        out.append(f'<circle class="dot {col}" cx="{X(18):.1f}" cy="{Y(ys[-1]):.1f}" r="6"/>')
        ends.append((ys[-1], name))
    prev = None
    for v, name in sorted(ends, reverse=True):
        y = Y(v) if prev is None else max(Y(v), prev + 30)
        out.append(f'<text class="tl" x="{R + 18}" y="{y + 7:.1f}">{name} {v:.0f}%</text>')
        prev = y
    return _svg(W, H, "Idea-to-customer lead time over 18 months, four model cases",
                "Lines show lead time as a percentage of today's. At month 18: Low 99%, AI only on mid inputs 95%, Mid 79%, High 51%. "
                "Only the High case approaches the 50% board target and none reaches it.", "".join(out))


# ---------------------------------------------------------------- slide 5: pipeline
def pipeline_diagram():
    # Stages: README "The pipeline" and the pipeline PNG from PR #69 (portrait, so redrawn here as a row); detail is in the expander.
    cards = [("Collect", "Code", "Calls, tickets, sessions"),
             ("Filter", "Decision model", "Keeps signal, drops small talk"),
             ("Extract", "Cheap model + code", "Problem and exact quote, quote checked"),
             ("Rank", "Code and formula", "Cluster, match roadmap, rank"),
             ("Decide", "Models, judges, PM", "Cited briefs for the top 10; a PM decides")]
    CW, GAP, Y0, CH = 232, 35, 8, 222
    o = []
    for i, (name, who, text) in enumerate(cards):
        x = i * (CW + GAP)
        o.append(f'<rect class="box" x="{x}" y="{Y0}" width="{CW}" height="{CH}" rx="10"/>'
                 f'<circle class="gate" cx="{x + 30}" cy="{Y0 + 34}" r="17"/>'
                 f'<text class="gn" x="{x + 30}" y="{Y0 + 42}" text-anchor="middle">{i + 1}</text>'
                 f'<text class="tl" x="{x + 58}" y="{Y0 + 42}">{esc(name)}</text>')
        o.append(f'<rect class="chip" x="{x + 12}" y="{Y0 + 64}" width="{CW - 24}" height="36" rx="6"/>'
                 f'<text class="ts" x="{x + CW / 2}" y="{Y0 + 89}" text-anchor="middle">{esc(who)}</text>')
        o.append(lines(x + 16, Y0 + 134, text, "tp", 20, 27))
        if i < 4:
            o.append(f'<line class="arr" x1="{x + CW + 3}" x2="{x + CW + GAP - 3}" y1="{Y0 + CH / 2}" y2="{Y0 + CH / 2}" marker-end="MARK"/>')
    o.append(f'<rect class="boxt" x="0" y="{Y0 + CH + 18}" width="1300" height="52" rx="8"/>'
             f'<text class="tl" x="650" y="{Y0 + CH + 52}" text-anchor="middle">'
             "Code checks every quote and number; a failed check hides the brief.</text>")
    return _svg(1300, 304, "The Signal Engine pipeline in five steps",
                "Step 1, collect: calls, tickets and sessions arrive each night. Step 2, filter: a decision model keeps signal and drops small talk. "
                "Step 3, extract: a cheap model writes the problem and quote and code verifies the quote. Step 4, rank: cluster, "
                "match the roadmap and rank by formula. Step 5, decide: the top ten get cited briefs, three judges check them and the PM decides.",
                "".join(o))


# ---------------------------------------------------------------- slide 7: results against floors
def _eval():
    import readme_sections as rs
    floors42, floors43, bools = rs.read_floors()
    return rs, floors42, floors43, bools, rs.load_report("ground-truth", rs.CURRENT["ground-truth"]), rs.load_report("holdout", rs.CURRENT["holdout"])


def results_chart():
    rs, f42, f43, bools, r42, r43 = _eval()

    def row(rep, floors, label, key):
        m, g = rep["metrics"], rep["gates"]
        v = m[key]
        _, fl, _op = floors[key]
        if key == "themes_recovered":
            tot = m["themes_total"]
            return label, v / tot, (tot if fl == "all" else fl) / tot, g[key], f"{v} of {tot}"
        return label, v, fl, g[key], f"{v:.2f}"
    rows42 = [("Signal recall", "signal_recall"), ("Noise-drop rate", "noise_drop_rate"), ("Bucket accuracy", "bucket_accuracy"),
              ("Quote verification", "quote_verification"), ("Attribution", "attribution"),
              ("Themes recovered", "themes_recovered"), ("Mean purity", "mean_purity")]
    rows43 = [("Signal recall", "signal_recall"), ("Quote verification", "quote_verification"),
              ("Attribution", "attribution"), ("Themes recovered", "themes_recovered"), ("Mean purity", "mean_purity")]
    o = []
    for px, title, rep, floors, rows in ((0, "Seed 42", r42, f42, rows42), (670, "Seed 43, held out", r43, f43, rows43)):
        X0, X1 = px + 206, px + 406
        X = lambda p: X0 + p * (X1 - X0)
        for p in (0, 0.5, 1.0):
            o.append(f'<line class="gr" x1="{X(p):.0f}" x2="{X(p):.0f}" y1="36" y2="{44 + 44 * len(rows)}"/>'
                     f'<text class="tk" x="{X(p):.0f}" y="{86 + 44 * len(rows) - 6}" text-anchor="middle">{p:g}</text>')
        o.append(f'<text class="tg3" x="{px}" y="26">{title}</text>')
        y = 44
        for label, key in rows:
            lab, v, fl, ok, txt = row(rep, floors, label, key)
            o.append(f'<text class="tp2" x="{px}" y="{y + 25}">{label}</text>'
                     f'<rect class="{"okb" if ok else "badb"}" x="{X0}" y="{y + 6}" width="{max(X(v) - X0, 2):.1f}" height="26" rx="2"/>'
                     f'<line class="floor" x1="{X(fl):.1f}" x2="{X(fl):.1f}" y1="{y}" y2="{y + 38}"/>'
                     f'<text class="tp2 b" x="{X1 + 12}" y="{y + 25}">{txt}</text>'
                     f'<text class="{"okt" if ok else "badt"}" x="{X1 + 84}" y="{y + 25}">{"holds" if ok else "below floor"}</text>')
            y += 44
    o.append('<line class="floor" x1="672" x2="672" y1="310" y2="334"/>'
             '<text class="ts" x="686" y="329">Black tick: the floor each check must reach</text>')
    return _svg(1300, 388, "Eval results against their floors, seed 42 and held-out seed 43",
                "Bars show each measure as a share of 1; a black tick marks the floor. Seed 42: signal recall 0.95 against 0.90, noise-drop 0.64 against 0.60, "
                "bucket accuracy 0.90 against 0.75, quote verification 0.99 against 0.93 all hold; attribution 0.98 against 1.00, themes recovered 1 of 6 "
                "against 6 of 6 and mean purity 0.54 against 0.75 are below their floors. Seed 43: signal recall, quote verification and attribution hold; "
                "themes recovered 0 of 3 against 2 of 3 and mean purity 0.37 against 0.75 are below their floors.", "".join(o))


def results_tables_html():
    """Every gated check, from the same reports the README cites. PASS and FAIL are the report's own gates."""
    rs, f42, f43, bools, r42, r43 = _eval()
    out = []

    def table(title, rep, rows, floors, b):
        m, g = rep["metrics"], rep["gates"]
        t = [f"<table><caption>{title}</caption><thead><tr><th>Check</th><th class=\"n\">Result</th><th class=\"n\">Floor</th><th>Gate</th></tr></thead><tbody>"]
        for label, key, kind in rows:
            fl, gated = rs.floor_text(floors, b, key, kind, m)
            gate = '<span class="pass">PASS</span>' if gated and g[key] else ('<span class="fail">FAIL</span>' if gated else "reported")
            t.append(f'<tr><td>{esc(label)}</td><td class="n">{rs.value(m, key, kind)}</td><td class="n">{esc(fl)}</td><td>{gate}</td></tr>')
        t.append("</tbody></table>")
        return "".join(t)
    rep42, rep43 = r42["run_id"], r43["run_id"]
    out.append(table(f"Seed 42 (report ground-truth-{rep42})", r42, rs.SEED42, f42, bools))
    out.append(table(f"Seed 43, held out (report holdout-{rep43})", r43, rs.SEED43, f43, ()))
    return "".join(out)


def earlier_table_html():
    rs, f42, f43, bools, r42, r43 = _eval()
    e42 = rs.load_report("ground-truth", rs.EARLIER["ground-truth"])
    e43 = rs.load_report("holdout", rs.EARLIER["holdout"])
    rows = [("Seed 42: themes recovered", "themes_recovered", "of", e42, r42), ("Seed 42: mean purity", "mean_purity", "f", e42, r42),
            ("Seed 42: citation failures", "citation_failures", "i", e42, r42), ("Seed 43: themes recovered", "themes_recovered", "of", e43, r43),
            ("Seed 43: mean purity", "mean_purity", "f", e43, r43), ("Seed 43: noise themes in the top 10", "noise_in_top10", "i", e43, r43)]
    t = ['<table><caption>Earlier run (04/11/2026) against the current routing (05/11/2026)</caption>'
         '<thead><tr><th>Measure</th><th class="n">Earlier</th><th class="n">Now</th></tr></thead><tbody>']
    for label, key, kind, a, b in rows:
        t.append(f'<tr><td>{label}</td><td class="n">{rs.value(a["metrics"], key, kind)}</td><td class="n">{rs.value(b["metrics"], key, kind)}</td></tr>')
    t.append("</tbody></table>")
    return "".join(t)


def judges_table_html():
    rs, *_ = _eval()
    rep = rs.load_report("judges", rs.CURRENT["judges"])
    m = rep["metrics"]
    t = ['<table><caption>Judges: held-out agreement on constructed items (they never certify)</caption>'
         '<thead><tr><th>Judge</th><th class="n">Constructed labels</th><th class="n">True-positive rate</th><th class="n">True-negative rate</th>'
         '<th class="n">Real PM labels</th></tr></thead><tbody>']
    for j in ("signal", "faithfulness", "duplicate"):
        p = f"{j}.synthetic_seed.held_out_"
        t.append(f'<tr><td>{j.capitalize()}</td><td class="n">{m[p + "labels"]}</td><td class="n">{m[p + "tpr"]:.2f}</td>'
                 f'<td class="n">{m[p + "tnr"]:.2f}</td><td class="n">0 of {rs.MIN_LABELS} per class</td></tr>')
    t.append("</tbody></table>")
    return "".join(t)


# ---------------------------------------------------------------- slide 8: tokens and API cost equivalent
def usage_rows():
    """Rows of the generated table in docs/ai-usage.md: (model, what, tokens, tokens text, rate, cost)."""
    doc = (ROOT / "docs" / "ai-usage.md").read_text(encoding="utf-8")
    block = doc.split("<!-- tokens:start -->")[1].split("<!-- tokens:end -->")[0]
    rows = []
    for ln in block.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and len(c) == 5 and c[0] not in ("Model", "---", "") and not c[0].startswith("-"):
            tok = int(re.search(r"([\d,]+)", c[2]).group(1).replace(",", ""))
            rows.append({"model": c[0].strip("*"), "what": c[1], "tokens": tok, "basis": c[2], "rate": c[3].strip("*"), "cost": float(c[4].strip("*"))})
    return rows


def usage_chart():
    rows = usage_rows()
    total = [r for r in rows if r["model"] == "Total"][0]
    rows = sorted([r for r in rows if r["model"] != "Total"], key=lambda r: -r["cost"])
    X0, X1 = 230, 620
    SC = (X1 - X0) / max(r["cost"] for r in rows)
    fmt = lambda n: f"{n / 1e6:.1f}M" if n >= 1_000_000 else f"{n:,}"
    o = [f'<text class="tk" x="{X0}" y="26">API cost equivalent, USD</text>'
         f'<text class="tk" x="950" y="26" text-anchor="end">Tokens, measured</text>']
    y = 50
    for r in rows:
        w = max(r["cost"] * SC, 3)
        o.append(f'<text class="tl" x="0" y="{y + 28}">{esc(r["model"])}</text>'
                 f'<rect class="fa" x="{X0}" y="{y + 6}" width="{w:.1f}" height="32" rx="2"/>'
                 f'<text class="tl" x="{X0 + w + 12:.1f}" y="{y + 30}">{r["cost"]:,.2f}</text>'
                 f'<text class="tp2" x="950" y="{y + 30}" text-anchor="end">{fmt(r["tokens"])}</text>')
        y += 56
    o.append(f'<line class="rl" x1="0" x2="950" y1="{y + 4}" y2="{y + 4}"/>'
             f'<text class="tl" x="0" y="{y + 40}">Total</text>'
             f'<text class="tl" x="{X0}" y="{y + 40}">USD {total["cost"]:,.2f}</text>'
             f'<text class="tl" x="950" y="{y + 40}" text-anchor="end">{total["tokens"]:,}</text>')
    return _svg(960, y + 60, "Tokens and API cost equivalent by model for this build",
                "API cost equivalent in USD and measured tokens per model: " + "; ".join(
                    f"{r['model']} {r['cost']:,.2f} USD and {r['tokens']:,} tokens" for r in rows)
                + f". Total {total['cost']:,.2f} USD and {total['tokens']:,} tokens.", "".join(o))


def usage_table_html():
    rows = usage_rows()
    t = ['<table><thead><tr><th>Model</th><th>What it did</th><th class="n">Tokens</th><th class="n">USD per million</th><th class="n">API cost equivalent, USD</th></tr></thead><tbody>']
    for r in rows:
        b = "<b>" if r["model"] == "Total" else ""
        e = "</b>" if b else ""
        t.append(f'<tr><td>{b}{esc(r["model"])}{e}</td><td>{esc(r["what"])}</td><td class="n">{r["basis"].replace("**", "")}</td>'
                 f'<td class="n">{r["rate"]}</td><td class="n">{b}{r["cost"]:,.2f}{e}</td></tr>')
    t.append("</tbody></table>")
    return "".join(t)


PIECES = {"LEADTIME": leadtime_chart, "LIFECYCLE": lifecycle_diagram, "DELEGATION": delegation_diagram, "HALVING": halving_chart,
          "PIPELINE": pipeline_diagram, "RESULTS": results_chart, "RESULTS_TABLES": results_tables_html,
          "EARLIER_TABLE": earlier_table_html, "JUDGES_TABLE": judges_table_html, "USAGE": usage_chart, "USAGE_TABLE": usage_table_html}

if __name__ == "__main__":
    for k, fn in PIECES.items():
        print(k, len(fn()))
