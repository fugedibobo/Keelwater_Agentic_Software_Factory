"""Board read functions, handoff validity, hash chain, and the static render."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import seed_store  # noqa: E402

from signal_engine import config  # noqa: E402
from signal_engine.board import cli, read  # noqa: E402
from signal_engine.store import Store  # noqa: E402


@pytest.fixture
def seeded(tmp_path):
    db = seed_store.seed_copy(tmp_path / "demo", tmp_path.parent)
    s = Store(db)
    yield s, tmp_path / "demo"
    s.close()


def test_since_last_week_with_two_runs_and_with_one(seeded):
    s, _ = seeded
    st = read.since_last_week(s)
    assert st["previous_run"] == seed_store.R1 and st["new"] == ["o5"]
    assert st["up"] == ["o1"] and st["down"] == ["o2"]
    assert st["post_ship"] == ["o4"] and st["decided"] == ["o3"] and st["new_evidence"] >= 6
    s.db.execute("DELETE FROM score WHERE run_id=?", (seed_store.R1,)); s.db.execute("DELETE FROM run WHERE run_id=?", (seed_store.R1,)); s.db.commit()
    one = read.since_last_week(s)  # a single-run store still shows the strip
    assert one["previous_run"] is None and one["new"] == ["o1", "o2", "o3", "o5"] and one["post_ship"] == ["o4"] and one["new_evidence"] >= 6


def test_check_line_names_failures_and_judge_state(seeded):
    s, _ = seeded
    rows = {o["opportunity_id"]: o for o in read.opportunities(s)}
    ok = {c["name"]: c["ok"] for c in rows["o1"]["checks"]}
    assert ok == {"quotes": True, "citations": True, "numbers": True, "names": True}
    bad = [c for c in rows["o2"]["checks"] if not c["ok"]]
    assert len(bad) == 1 and bad[0]["name"] == "numbers" and "does not match the fact sheet" in bad[0]["detail"] and rows["o2"]["brief_failed"]
    assert rows["o2"]["judges"][0]["note"] == "calibrating: 23 of 50 pass, 8 of 50 fail"
    assert rows["o4"]["checks"] is None
    assert [c["name"] for c in rows["o1"]["chips"]] == ["breadth", "severity", "value", "corroboration", "recency", "renewal"]
    assert "on roadmap" in [c["name"] for c in rows["o5"]["chips"]]
    assert rows["o1"]["rank"] == 1 and rows["o1"]["trend"]["delta"] == 2 and rows["o5"]["trend"]["new"]


def test_drill_down_quotes_accounts_and_disputed_tags(seeded):
    s, _ = seeded
    o = read.opportunity(s, "o1")
    e = o["evidence"][0]
    assert e["match"] in e["before"] + e["match"] + e["after"] and e["match"].startswith("I have to redo") and e["before"] == "" and e["after"].startswith(" and it takes")
    assert e["context"] == "So what slows you down most?" and e["ref"]
    assert o["unresolved"] == 1 and o["accounts"] and o["accounts"][0]["in_hubspot"]
    s.db.execute("DELETE FROM account WHERE account_id='acc1'"); s.db.commit()
    assert any(a["name"] is None and not a["in_hubspot"] for a in read.opportunity(s, "o1")["accounts"] + read.opportunity(s, "o3")["accounts"] + read.opportunity(s, "o4")["accounts"])
    assert [o["opportunity_id"] for o in read.tag_queue(s)] == ["o5"]
    assert read.opportunity(s, "o4")["post_ship_evidence"] and read.opportunity(s, "zzz") is None
    s.db.execute("UPDATE insight SET quote_match='failed'"); s.db.commit()
    assert read.opportunity(s, "o1")["evidence"] == []  # unmatched quotes never reach the page


def test_handoffs_validity_and_preview(seeded):
    s, _ = seeded
    by = {h["opportunity"]["opportunity_id"]: h for h in read.handoffs(s)}
    assert by["o4"]["handoff"]["errors"] == [] and not by["o4"]["handoff"]["preview"]
    bad = by["o3"]["handoff"]
    assert bad["errors"] and bad["preview"]  # accepted, not yet intent_drafted
    assert read.md("# T\n\n- a <b>\n- c")  .startswith("<h5>T</h5><ul><li>a &lt;b&gt;")


def test_pipeline_evals_and_audit_chain(seeded):
    s, d = seeded
    p = read.pipeline(s)
    assert p["total"]["raw"] == sum(f["raw"] for f in p["funnel"]) and p["total"]["dropped"] == 40 and p["fallback_flag"] is False
    assert {x["stage"] for x in p["stages"]} == {"triage", "extract", "brief", "judge"} and p["cap"] == 1.5
    ev = read.evals(s, d / "reports" / "eval")
    assert ev["available"] and {r["metric"] for r in ev["ground_truth"]} >= {"theme_recall", "loud_narrow_rank"} and ev["stability"]["passed"]
    assert ev["miss_rate"] is None and len(ev["noise"]) == 40 and len(ev["judges"]) == 3
    assert read.evals(s, d / "nowhere")["available"] is False
    assert read.chain_status(s)["ok"] and read.chain_status(s)["verified"] == 2
    s.db.execute("DROP TRIGGER audit_no_update"); s.db.execute("UPDATE audit_event SET actor='mallory' WHERE rowid=2"); s.db.commit()
    broken = read.chain_status(s)
    assert not broken["ok"] and broken["verified"] == 1 and "BROKEN" in broken["text"]


def test_audit_pages_at_100(seeded):
    s, _ = seeded
    for i in range(130):
        s.append_audit("system", "system", "x", "run", "r", {"i": i})
    a = read.audit(s, "audit_event")
    assert a["total"] == 132 and len(a["rows"]) == 100 and a["pages"] == 2 and len(read.audit(s, "audit_event", page=2)["rows"]) == 32


def test_static_render_is_self_contained_and_honest(seeded, tmp_path):
    s, d = seeded
    out = tmp_path / "site"
    assert cli.main(["static", "--db", str(d / "keelwater.sqlite"), "--out", str(out)]) == 0
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Static snapshot of run run-20261103, 03/11/2026. Actions are disabled. Run the local server to review." in html
    assert "fetch(" not in html and "board-live" not in html and 'src="/static' not in html and 'href="/static' not in html
    assert "<style>" in html and "board-data" in html
    buttons = re.findall(r"<button[^>]*data-act=[^>]*>", html)
    assert buttons and all("disabled" in b for b in buttons)
    for secret in (str(config.ROOT), str(tmp_path), str(config.ROOT).replace("\\", "/"), "OPENROUTER_API_KEY", "TYPESAFE_API_KEY", "sk-or-"):
        assert secret not in html
    assert not re.search(r"[A-Za-z]:\\\\|/Users/|/home/", html)
    for tab in ("opportunities", "handoffs", "pipeline", "evals", "audit", "how"):
        assert f'id="{tab}"' in html and f'href="#{tab}"' in html
    assert "Bulk reassignment of claims" in html and "PREVIEW: not accepted by a PM" in html and "VALID" in html and "INVALID" in html
    assert "Synthetic data. Keelwater is fictional." in html and "id=\"raw-" in html
    assert (out / "diagrams").is_dir() == (config.ROOT / "docs" / "diagrams" / "agentic-pdlc.html").is_file()


def test_static_render_without_reports_or_diagrams(tmp_path, monkeypatch):
    db = seed_store.seed_copy(tmp_path / "demo", tmp_path.parent)
    for p in (tmp_path / "demo" / "reports" / "eval").glob("*.json"):
        p.unlink()
    monkeypatch.setattr(config, "ROOT", tmp_path / "norepo")  # no docs/diagrams there
    out = tmp_path / "site"
    assert cli.main(["static", "--db", str(db), "--out", str(out)]) == 0
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "not evaluated yet: run <code>uv run keelwater eval --suite all</code>" in html and "Diagram not available" in html


def test_cli_needs_a_store(tmp_path, capsys):
    assert cli.main(["static", "--db", str(tmp_path / "none.sqlite"), "--out", str(tmp_path / "o")]) == 2
