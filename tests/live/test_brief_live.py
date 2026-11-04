"""Live smoke: one fixture opportunity through the brief writer and all three judges.
Run by a sonnet subagent: uv run pytest tests/live/test_brief_live.py --live -s -q  (spend under USD 0.10)."""

import pytest

from signal_engine import brief, judges
from test_brief import make_ctx, seed

pytestmark = pytest.mark.live


def test_one_opportunity_brief_and_three_judges(live_gateway):
    store = live_gateway.store
    seed(store)
    ctx = make_ctx(live_gateway, store)
    brief.run(ctx)
    (b,) = store.select("brief")
    print("\n--- BRIEF", b["check_status"], b["check_failures_json"], "\n" + b["body_md"])
    judges.run(ctx)
    for j in store.select("judgement"):
        print(f"--- {j['judge']} on {j['target_type']}: {j['verdict']}\n{j['critique']}")
    assert {j["judge"] for j in store.select("judgement")} == {"signal", "faithfulness", "duplicate"}
    print(f"spend USD {live_gateway.spent:.4f}")
    assert live_gateway.spent < 0.10
