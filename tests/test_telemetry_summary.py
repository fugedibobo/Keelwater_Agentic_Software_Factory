"""Tests for scripts/telemetry_summary.py on a toy CSV; never reads the real CSV or docs."""
import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("telemetry_summary", ROOT / "scripts" / "telemetry_summary.py")
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

NR = "not reported"
COLS = ["issue", "status", "role", "engine", "tokens_total", "tokens_basis", "live_usd", "live_usd_basis",
        "first_check_result", "rework_count"]


def row(issue, status, role, engine, tok=NR, basis=NR, usd=NR, ubasis=NR, first="", rw=""):
    return dict(zip(COLS, [issue, status, role, engine, tok, basis, usd, ubasis, first, rw]))


TOY = [
    row("1", "done", "build", "sonnet", "100", "measured", "0", "measured", "PASS", "0"),
    row("1", "done", "orchestrate", "opus", "10", "estimated"),
    row("2", "done", "build", "sonnet", "300", "measured", "0.5", "estimated", "REWORK", "1"),
    row("2", "done", "check", "sonnet", NR, NR),
    row("3", "partial", "build", "codex", NR, NR, "0.25", "measured", "PASS", "0"),
    row("4", "in-progress", "build", "sonnet", NR, NR, first="none"),
]


@pytest.fixture
def toy_csv(tmp_path):
    p = tmp_path / "t.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(TOY)
    return p


def test_totals_keep_measured_estimated_and_missing_apart(toy_csv):
    s = ts.summarise(ts.load(toy_csv))
    assert s["tokens"]["sonnet"] == {"measured": 400.0, "estimated": 0.0, "missing": 2}
    assert s["tokens"]["opus"] == {"measured": 0.0, "estimated": 10.0, "missing": 0}
    assert s["tokens"]["codex"]["missing"] == 1 and s["tokens"]["codex"]["measured"] == 0
    assert s["usd"]["sonnet"] == {"measured": 0.0, "estimated": 0.5}
    assert s["usd"]["codex"]["measured"] == 0.25


def test_pass_rate_reworks_and_share(toy_csv):
    s = ts.summarise(ts.load(toy_csv))
    assert s["first"]["sonnet"] == (1, 2)  # the in-progress "none" row is excluded
    assert s["first"]["codex"] == (1, 1)
    assert s["rework"] == {"opus": 0, "sonnet": 1, "codex": 0}
    assert s["n_builds"] == 4 and s["build"]["codex"] == 1
    assert (s["accepted_new"], s["n_accepted"]) == (1, 3)  # in-progress build not counted as accepted
    assert s["counts"] == {"done": 2, "partial": 1, "in-progress": 1}


def test_render_and_write_doc(toy_csv, tmp_path):
    block = ts.render(ts.summarise(ts.load(toy_csv)), "04/11/2026")
    assert block.startswith("2 done, 1 partial, 1 in progress: refreshed on 04/11/2026")
    assert "| sonnet | 1 of 2 | 50% | 1 | 3 | 75% |" in block
    assert "built 1 of 3 done or partial work orders (33%)" in block
    doc = tmp_path / "d.md"
    doc.write_text(f"intro\n{ts.START}\nOLD\n{ts.END}\ntail\n", encoding="utf-8")
    ts.main(["--csv", str(toy_csv), "--doc", str(doc), "--date", "04/11/2026", "--write-doc"])
    out = doc.read_text(encoding="utf-8")
    assert "OLD" not in out and out.startswith("intro\n") and out.endswith(f"{ts.END}\ntail\n")
    assert "refreshed on 04/11/2026" in out
    ts.main(["--csv", str(toy_csv), "--doc", str(doc), "--date", "04/11/2026", "--write-doc"])
    assert doc.read_text(encoding="utf-8") == out  # idempotent
