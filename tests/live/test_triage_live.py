"""Live triage smoke over 20 fixture snippets (needs OPENROUTER_API_KEY): uv run pytest tests/live/test_triage_live.py --live -s -q"""

from datetime import date
from pathlib import Path

import pytest

from signal_engine import config, triage
from signal_engine.contracts import Snippet
from signal_engine.pipeline import RunContext

pytestmark = pytest.mark.live
TEXTS = [
    "The claim form loses everything I typed when the session times out.", "Can we move the call to Thursday afternoon?",
    "We cannot attach photos larger than 5 MB to a claim, adjusters are emailing them instead.", "Thanks, that was a great demo.",
    "Reserve changes do not show up in the weekly payments report until the next day.", "How is the weather over there?",
    "Our suppliers never get the instruction email after we assign a repairer.", "I will send the invoice by Friday.",
    "Bulk reassigning claims to another handler is impossible, we do it one by one.", "Lunch at one?",
    "The customer letter template cannot include the claim reference.", "Let me share my screen.",
    "Admins cannot see who last edited a user's permissions.", "Great, talk next week.",
    "The API rejects claims with more than 50 line items without a useful error.", "Sorry, my microphone was muted.",
    "Release notes arrive after the change is already live and our handlers are confused.", "Happy new year to the team.",
    "Fraud referral cannot be started from the mobile view.", "Is this recording?",
]


def test_triage_smoke_20_snippets(live_gateway):
    store = live_gateway.store
    for i, t in enumerate(TEXTS):
        store.insert("snippet", Snippet(snippet_id=f"live{i:02d}", raw_id="raw", text=t))
    cfg = {n: config.load(n) for n in config.CONFIG_FILES}
    ctx = RunContext(store, live_gateway, "live", date(2026, 11, 3), Path("."), 42, "all", "demo", Path("."), cfg, None, "triage")
    triage.run(ctx)
    rows = store.select("triage")
    print(f"\n{'snippet':<8}{'backend':<10}{'p':<7}{'bucket':<20}{'sev':<4}{'type':<18}{'decision':<16}ms")
    for r in rows:
        print(f"{r['snippet_id']:<8}{r['backend']:<10}{r['is_signal_p'] or 0:<7.2f}{r['bucket'] or '-':<20}{r['severity'] or 0:<4}"
              f"{r['signal_type'] or '-':<18}{r['decision']:<16}{r['latency_ms']}")
    print("active backend:", {r["backend"] for r in rows}, "spent USD", round(live_gateway.spent, 5))
    assert len(rows) == 20 and live_gateway.spent < 0.05
