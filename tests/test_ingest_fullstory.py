"""FullStory idle-strip and interaction windows."""

import json
from pathlib import Path

from signal_engine.ingest import fullstory as fs

FIX = Path(__file__).resolve().parent / "fixtures" / "ingest" / "fullstory"
T0 = fs.ts("2026-10-14T09:00:00Z")


def ev(i, sec, typ="click", **props):
    p = {"target_text": "Save", **props}
    return {"event_id": f"e{i}", "event_time": f"2026-10-14T{9 + sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}Z",
            "session_id": "s", "event_type": typ, "event_properties": p, "source_properties": {"page_name": "Claim > Documents"}}


def test_fixture_two_hours_to_under_six_minutes():
    events = [json.loads(x) for x in (FIX / "events.ndjson").read_text(encoding="utf-8").splitlines()][:-1]  # last line is the bad row
    wins, before, after = fs.windows(events, T0)
    assert before > 6900 and after < 360
    assert any('Claim > Documents: click "Document type" select, rage x5' in w["lines"] for w in wins)
    assert wins == fs.windows(events, T0)[0]  # deterministic


def test_render_dead_error_and_exception():
    assert fs.render(ev(1, 0, fs_dead_count=2)) == 'Claim > Documents: click "Save", dead x2'
    assert fs.render(ev(1, 0, fs_error_kind="network")) == 'Claim > Documents: click "Save", error network'
    assert fs.render(ev(1, 0, "exception", message="boom")).endswith("exception \"Save\", boom")


def test_no_trigger_no_window():
    assert fs.windows([ev(1, 0), ev(2, 10)], T0) == ([], 10.0, 0.0)


def test_far_apart_triggers_stay_separate_and_near_ones_merge():
    # triggers 500 s apart on the stripped clock
    far = [ev(1, 0, fs_rage_count=3), ev(2, 100), ev(3, 200), ev(4, 300), ev(5, 400), ev(6, 500, fs_dead_count=1)]
    wins, _, after = fs.windows(far, T0)
    assert len(wins) == 2 and after == 120  # each window clipped at the session edge
    close = [ev(1, 0, fs_rage_count=3), ev(2, 60, fs_rage_count=3)]
    assert len(fs.windows(close, T0)[0]) == 1


def test_idle_gap_over_120s_is_cut():
    evs = [ev(1, 0, fs_rage_count=3), ev(2, 30), ev(3, 7200, fs_dead_count=1)]  # 2 h gap cut to zero
    wins, before, after = fs.windows(evs, T0)
    assert before == 7200 and len(wins) == 1 and after == 30 and wins[0]["event_ids"] == ["e1", "e2", "e3"]
