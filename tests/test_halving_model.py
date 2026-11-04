"""Tests for scripts/halving_model.py. No matplotlib needed."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("halving_model", ROOT / "scripts" / "halving_model.py")
hm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hm)


def test_generate_is_deterministic(tmp_path):
    inp = hm.load_inputs()
    a, b = tmp_path / "a.csv", tmp_path / "sub" / "b.csv"
    assert hm.generate(a, inp) == hm.generate(b, inp) > 500
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes().startswith(b"item_id,squad,idea,decision,spec,")


def toy(effect):
    return {"shares": {"build": 1.0}, "ai": {"build": effect}, "proc": {"build": 0.0},
            "ramp": [0.0, 0.5, 1.0] + [1.0] * 15, "start": 1, "full": 1}


def test_crossing_found_on_toy_input():
    # effect -0.6: index 1.0, 0.7, 0.4 -> first <= 0.5 in month 3
    s = hm.index_series(toy(-0.6), ["build"])
    assert [round(v, 6) for v in s[:3]] == [1.0, 0.7, 0.4]
    assert hm.first_crossing(s) == 3
    assert hm.month_text(3) == "month 3"
    # exactly 50% counts as halved
    assert hm.first_crossing(hm.index_series(toy(-0.5), ["build"])) == 3
    # effect -0.3 never gets there
    assert hm.first_crossing(hm.index_series(toy(-0.3), ["build"])) is None
    assert hm.month_text(None) == "not within 18 months"


def test_process_phase_in_and_baseline_normalisation():
    p = {"shares": {"a": 0.2, "b": 0.6}, "ai": {"a": 0.0, "b": 0.0}, "proc": {"a": -0.5, "b": 0.0},
         "ramp": [0.0] * 4, "start": 2, "full": 2}
    s = hm.index_series(p, ["a", "b"])
    # month 1 no change; month 2 half phase on a; month 3 full: (0.1 + 0.6) / 0.8
    assert s[0] == 1.0 and s[2] == pytest.approx(0.7 / 0.8) and s[1] == pytest.approx(0.75 / 0.8)


def test_every_input_labelled_and_mid_shares_sum_to_one():
    inp = hm.load_inputs()
    assert hm.validate_inputs(inp) == []
    for sec in ("stage_shares", "ai_effect"):
        for name, e in inp[sec].items():
            assert e["label"] in ("FOUND", "INFERRED") and e["source"], f"{sec}.{name}"
    for name, e in inp["process_changes"]["effect"].items():
        assert e["label"] == "INFERRED" and e["source"], name
    for k in ("adoption_ramp", "lead_time_definitions"):
        assert inp[k]["label"] in ("FOUND", "INFERRED") and inp[k]["source"]
    assert inp["process_changes"]["phase_in"]["label"] == "INFERRED"
    assert sum(e["mid"] for e in inp["stage_shares"].values()) == pytest.approx(1.0)


def test_validation_catches_missing_label_and_bad_sum():
    inp = hm.load_inputs()
    del inp["ai_effect"]["build"]["label"]
    assert any("ai_effect.build" in e for e in hm.validate_inputs(inp))
    inp = hm.load_inputs()
    inp["stage_shares"]["build"]["mid"] = 0.5
    assert any("sum" in e for e in hm.validate_inputs(inp))
    with pytest.raises(SystemExit):
        hm.check_inputs(inp)


def test_model_and_sensitivity_run():
    inp = hm.load_inputs()
    res = hm.run_model(inp)
    assert len(res[("mid", "ai_plus_process", "idea_to_customer")]) == 18
    rows = hm.sensitivity(inp)
    assert rows == sorted(rows, key=lambda r: -r[5]) and rows[0][5] > 0
    assert "Halving idea-to-customer" in hm.answer_sentence(inp, res)


def _row(i, squad, rel, days_flag, days_cust):
    r = datetime.strptime(rel, hm.FMT)
    idea = r - timedelta(days=days_cust)
    flag = idea + timedelta(days=days_flag)
    f = lambda d: d.strftime(hm.FMT)  # noqa: E731
    # the six middle boundaries are collapsed onto flag_on for brevity
    return ",".join([f"I{i}", squad, f(idea)] + [f(flag)] * 7 + [f(r), f(r)])


def test_tracker_windows_on_hand_made_csv(tmp_path):
    # Baseline = released in months 1-3; current = last two months present (5 and 6).
    rows = [_row(1, "a", "2026-05-10T00:00:00", 80, 100), _row(2, "a", "2026-06-10T00:00:00", 80, 100),
            _row(3, "b", "2026-07-10T00:00:00", 80, 100), _row(4, "b", "2026-07-11T00:00:00", 80, 100),
            _row(5, "a", "2026-09-10T00:00:00", 40, 50), _row(6, "b", "2026-10-10T00:00:00", 40, 50)]
    f = tmp_path / "items.csv"
    f.write_text(",".join(hm.COLS) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    t = hm.track(hm.read_items(f))
    assert t["cur_months"] == (5, 6)
    lt = {(g, n): (b, c, raw, shown) for g, n, b, c, raw, shown in t["lt"]}
    assert lt[("overall", "idea_to_customer")] == pytest.approx((100, 50, 1.0, 1.0))
    assert lt[("overall", "idea_to_production_behind_flag")] == pytest.approx((80, 40, 1.0, 1.0))
    tp = {g: (b, c, raw) for g, b, c, raw, shown in t["tp"]}
    # overall: baseline 4 items / 3 months / 2 squads; current 2 items / 2 months / 2 squads
    assert tp["overall"] == pytest.approx((4 / 3 / 2, 0.5, 0.5 / (4 / 6) - 1))
    assert tp["a"] == pytest.approx((2 / 3, 0.5, 0.5 / (2 / 3) - 1))
    # raw can be outside 0-100% and is clamped for display
    assert hm.clamp(-0.2) == 0.0 and hm.clamp(1.4) == 1.0
