"""Live smoke for #5: 10 snippets through extract, embed, cluster label, tag and rank. uv run pytest tests/live/test_extract_live.py --live -s -q"""

import pytest
from pipe5 import ctx_for, seed_account, seed_snippet
from signal_engine import cluster, extract, rank, tag
from signal_engine import contracts as c
from signal_engine.store import raw_id

pytestmark = pytest.mark.live

SNIPPETS = [  # (text, source, route, account)
    ("Every time we get a repair estimate we have to upload the photos and PDFs one by one, it takes forever.", "intercom", "support", "A01"),
    ("We have forty documents per claim and can only attach a single file per click, which is painful.", "gong", "sales", "A02"),
    ("Uploading a whole folder of evidence at once would save my team hours every week.", "fireflies", "account_management", "A03"),
    ("The layout of the claims screen changed overnight and nobody told us, so my handlers made mistakes.", "intercom", "support", "A04"),
    ("You moved the reserve button without any warning and we had to retrain the whole team on Monday.", "gong", "sales", "A05"),
    ("We would like a heads up before interface changes, ideally a preview in a test environment first.", "fireflies", "onboarding", "A06"),
    ("Our policyholders keep phoning to ask where their claim is, they should get a text at each milestone.", "intercom", "support", "A07"),
    ("It would be great if customers got automatic email updates when the claim moves to a new stage.", "gong", "sales", "A08"),
    ("The export to CSV totals do not match the dashboard, finance no longer trusts the numbers.", "fireflies", "account_management", "A09"),
    ("Can you add dark mode to the claims screen, my eyes get tired in the evening.", "intercom", "support", "A10"),
]


def test_smoke_extract_cluster_tag_rank(live_gateway):
    store = live_gateway.store
    for n, (text, source, route, account) in enumerate(SNIPPETS):
        seed_account(store, account, 100_000 * (n + 1), "2027-01-15")
        seed_snippet(store, f"live{n}", text, source=source, route=route, account=account, occurred="2026-10-20T09:00:00Z",
                     run_id="live")
    store.insert("raw_record", c.RawRecord(raw_id=raw_id("shortcut", "1"), source="shortcut", source_id="1", payload_json={
        "id": 1, "name": "Bulk upload", "story_type": "feature", "completed": True, "completed_at": "2026-10-06T10:00:00Z",
        "description": "Upload many documents to a claim at once."}))
    store.insert("raw_record", c.RawRecord(raw_id=raw_id("notion", "n1"), source="notion", source_id="n1", payload_json={
        "id": "n1", "properties": {"Name": {"title": [{"plain_text": "Policyholder milestone notifications"}]},
                                   "Status": {"status": {"name": "In progress"}}, "Target": {"date": None},
                                   "Problem": {"rich_text": [{"plain_text": "Automatic SMS and email updates at claim milestones."}]}}}))
    ctx = ctx_for(store, live_gateway, run_id="live")
    for stage in (extract, cluster, tag, rank):
        stage.run(ctx)
    for i in store.select("insight"):
        print("insight", i["insight_id"], i["quote_match"], "|", i["quote"])
    for o in store.select("opportunity"):
        print("opportunity", o["opportunity_id"], o["title"], "| tag", o["tag"], o["tag_ref"], o["tag_state"])
    for s in store.select("score"):
        print("score", {k: round(v, 3) for k, v in s.items() if isinstance(v, float)}, "unresolved", s["unresolved_insights"])
    print("spend USD", round(live_gateway.spent, 5))
    assert len(store.select("insight")) == len(SNIPPETS)
    assert live_gateway.spent < 0.10
