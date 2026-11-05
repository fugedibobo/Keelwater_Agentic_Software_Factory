"""Board readability (#63): hover help for every metric, tab order, About tab, light/dark tokens (AA contrast), README diagrams."""

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import seed_store  # noqa: E402

from signal_engine import config  # noqa: E402
from signal_engine.board import cli, read  # noqa: E402
from signal_engine.evals import ground_truth as gt  # noqa: E402
from signal_engine.store import Store  # noqa: E402

REPORTS = config.ROOT / "reports" / "eval"
STATIC = Path(read.__file__).parent / "static"


def _filled(group, key):
    entry = read.HELP[group].get(key)
    assert entry and entry["label"].strip() and entry["what"].strip(), f"no help for {group}.{key}"


def test_every_eval_metric_has_help():
    keys = set()
    for suite in ("ground-truth", "holdout", "stability"):
        for p in REPORTS.glob(f"{suite}-*.json"):  # every committed report, not only the newest
            keys |= {(("stability" if suite == "stability" else "metrics"), k) for k in json.loads(p.read_text(encoding="utf-8"))["metrics"]}
    keys |= {("metrics", k) for k in (*gt.FLOORS_42, *gt.FLOORS_43, *gt.BOOLS_42)}
    keys |= {("judges", k) for k in ("judge", "signal", "faithfulness", "duplicate", "n_pass", "n_fail", "tpr", "tnr", "state")}
    keys |= {("drift", k) for k in ("agreement", "miss_rate", "acceptance")}
    keys |= {("scores", k) for k in ("total", "breadth", "severity", "value", "corroboration", "recency", "renewal", "roadmap")}
    keys |= {("columns", k) for k in ("ground_truth", "metric", "seed42", "seed43", "gate", "stability")} | {("stability", "stable")}
    assert len(keys) > 40
    for group, key in sorted(keys):
        _filled(group, key)
    assert read.HELP["noise_audit"]["what"].strip()


def test_help_text_carries_floors_from_the_gates_and_ranking_config():
    assert "seed 42: at least 0.90 (target 0.95)" in read.gate_text("signal_recall") and "seed 43: at least 0.85" in read.gate_text("signal_recall")
    assert "seed 42: all 6 themes" in read.gate_text("themes_recovered") and "seed 43: at least 2 (target 3)" in read.gate_text("themes_recovered")
    assert "must be yes" in read.gate_text("top_set") and "Reported only" in read.gate_text("kendall_tau")
    rk = config.load("ranking")  # the numbers typed into the score help must be the configured ones
    h = {k: v["what"] for k, v in read.HELP["scores"].items()}
    assert f"{rk['corroboration'][2]:g}" in h["corroboration"] and f"{rk['corroboration'][3]:g}" in h["corroboration"]
    assert str(rk["recency"]["window_days"]) in h["recency"] and f"{rk['recency']['floor']:g}" in h["recency"]
    assert str(rk["renewal"]["window_days"]) in h["renewal"] and f"{rk['renewal']['weight']:g}" in h["renewal"]
    assert f"x{rk['roadmap']['on_roadmap']:g}" in h["roadmap"] and f"{rk['value']['floor']:g}" in h["value"]


@pytest.fixture
def html(tmp_path):
    db = seed_store.seed_copy(tmp_path / "demo", tmp_path.parent)
    for old in (tmp_path / "demo" / "reports" / "eval").glob("*.json"):
        old.unlink()
    for new in REPORTS.glob("*.json"):  # the committed reports carry the real metric names
        shutil.copy2(new, tmp_path / "demo" / "reports" / "eval" / new.name)
    out = tmp_path / "site"
    assert cli.main(["static", "--db", str(db), "--out", str(out)]) == 0
    return (out / "index.html").read_text(encoding="utf-8")


def test_tabs_start_with_about_and_markers_are_wired(html):
    order = re.findall(r'<a role="tab" id="t-(\w+)"[^>]*>([^<]+)</a>', html)
    assert [t for t, _ in order] == ["about", "opportunities", "handoffs", "pipeline", "evals", "audit", "how"]
    assert [n for _, n in order] == ["0 About this board", "1 Opportunities", "2 Handoffs", "3 Pipeline", "4 Evals", "5 Audit", "6 How it works"]
    ids = re.findall(r'(?<![-\w])id="([^"]+)"', html)  # not data-id
    assert len(ids) == len(set(ids)), "duplicate ids"
    markers = re.findall(r'<button type="button" class="i" aria-label="[^"]+" aria-describedby="(h-[^"]+)" title="([^"]+)"', html)
    assert len(markers) > 20 and all(f'id="{d}"' in html and t.strip() for d, t in markers)
    assert 'id="theme-toggle"' in html and 'localStorage.getItem("board-theme")' in html
    for label in ("Themes recovered (of planted themes)", "Over-merges (two real themes merged into one)", "dropped as noise when the model is at least 75% sure"):
        assert label in html
    assert 'data-metric="themes_recovered"' in html


def test_about_tab_is_about_250_words_and_plain():
    text = (Path(read.__file__).parent / "templates" / "about.html").read_text(encoding="utf-8")
    words = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).split()
    assert 220 <= len(words) <= 290, len(words)
    assert "FOUND" not in text and "INFERRED" not in text and "30 fictional insurers" in text and "simulated" in text.lower()


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _lum(h):
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in _rgb(h)]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(css, selector):
    block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def test_both_themes_pass_aa_contrast():
    css = (STATIC / "board.css").read_text(encoding="utf-8")
    dark = _tokens(css, ":root")
    light = {**dark, **_tokens(css, ":root[data-theme=light]")}
    assert "prefers-color-scheme" not in css, "dark is the default whatever the OS says"
    for name, t in (("dark", dark), ("light", light)):
        for fg, bg in (("fg", "bg"), ("fg", "surface"), ("muted", "bg"), ("muted", "surface"), ("accent", "bg"), ("accent", "surface"), ("accent-fg", "accent"),
                       ("ok", "surface"), ("bad", "surface"), ("ok", "bg"), ("bad", "bg"), ("fg", "warn-bg"), ("fg", "mark")):
            assert _ratio(t[fg], t[bg]) >= 4.5, f"{name}: {fg} on {bg} is {_ratio(t[fg], t[bg]):.2f}"
        for bg in ("bg", "surface"):  # borders and the info marker outline are UI components: 3:1
            assert _ratio(t["line"], t[bg]) >= 3.0, f"{name}: line on {bg} is {_ratio(t['line'], t[bg]):.2f}"


def test_readme_has_images_not_interactive_diagrams():
    readme = (config.ROOT / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"mermaid|iframe|docs/diagrams/[\w-]+\.html|\(interactive\)", readme, re.I)
    for png in ("agentic-pdlc", "pipeline"):
        assert f"[![" in readme and f"](docs/diagrams/{png}.png)](docs/diagrams/{png}.png)" in readme
        assert (config.ROOT / "docs" / "diagrams" / f"{png}.png").is_file()
    assert (config.ROOT / "docs" / "diagrams" / "pipeline.mmd").is_file()
    assert readme.index("## Start here") < readme.index("## How ready is this") < readme.index("## Part 2") < readme.index("### Screenshots")
    assert readme.index("### Screenshots") < readme.index("## Why trust it")
