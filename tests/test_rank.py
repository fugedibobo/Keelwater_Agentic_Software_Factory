import math

import pytest
from pipe5 import AS_OF, ctx_for, seed_account, seed_snippet
from signal_engine import contracts as c, rank
from signal_engine.store import insight_id

# Fixture: median customer ARR = 100,000 (A 1,000,000; B 100,000; C 10,000), nominal ARR = 50,000.
INSIGHTS = [  # key, account, severity, route source, date
    ("i1", "A", 4, "support", "2026-10-20T09:00:00Z"),
    ("i2", "B", 2, "sales", "2026-08-01T09:00:00Z"),
    ("i3", "P1", 3, "onboarding", "2026-10-30T09:00:00Z"),
    ("i4", None, 1, "support", "2026-10-31T09:00:00Z"),
]


def build(store, tag="none", post_ship=("i1", "i2", "i3", "i4"), state="proposed", insights=INSIGHTS):
    seed_account(store, "A", 1_000_000, "2026-12-01")
    seed_account(store, "B", 100_000, "2027-06-01")
    seed_account(store, "C", 10_000, None)
    seed_account(store, "P1", None, None, tier="prospect")
    store.insert("opportunity", c.Opportunity(opportunity_id="o1", title="t", problem_statement="p", bucket="documents_evidence",
                                              first_seen_as_of=AS_OF, tag=tag, tag_state=state if tag != "none" else None))
    for key, acct, sev, route, when in insights:
        sid = seed_snippet(store, key, f"{key} customer words about the problem here", account=acct, route=route, occurred=when,
                           status="resolved" if acct else "unresolved")
        iid = insight_id(sid, "q")
        store.insert("insight", c.Insight(insight_id=iid, snippet_id=sid, run_id="r1", problem="p", quote="a b c d e f",
                                          quote_match="exact", severity=sev, account_id=acct,
                                          account_status="resolved" if acct else "unresolved"))
        store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id="o1", insight_id=iid, similarity=0.9,
                                                                 post_ship=key in post_ship))


def score(store, fake_gateway):
    rank.run(ctx_for(store, fake_gateway()))
    return store.select("score")


def test_hand_computed_fixture_matches_to_1e_9(tmp_store, fake_gateway):
    build(tmp_store)
    (s,) = score(tmp_store, fake_gateway)
    want = {"breadth": 2.0,  # three accounts (A, B, P1): log2(4); the unresolved insight adds none
            "severity": 4_400_000 / 1_200_000,  # weights 1e6, 1e5, 5e4 (prospect), 5e4 (unresolved)
            "value": 1 + math.log10(1_150_000 / 100_000),  # unresolved adds 0 ARR; the prospect counts 50,000
            "corroboration": 1.5,  # support, sales, onboarding
            "recency": 0.75,  # i1, i3 and i4 within 30 days of 03/11/2026
            "renewal": 1 + 0.25 * (1_000_000 / 1_150_000),  # only A renews within 90 days
            "roadmap": 1.0}
    for k, v in want.items():
        assert s[k] == pytest.approx(v, abs=1e-9), k
    assert s["total"] == pytest.approx(math.prod(want.values()), abs=1e-9)
    assert s["unresolved_insights"] == 1
    assert s["total"] == pytest.approx(rank.total_of(s), abs=1e-9)  # recomputes from the stored factors


def test_on_roadmap_halves_the_score(tmp_store, fake_gateway):
    build(tmp_store, tag="on_roadmap")
    (s,) = score(tmp_store, fake_gateway)
    assert s["roadmap"] == 0.5 and s["total"] == pytest.approx(rank.total_of(s), abs=1e-9)


def test_removed_tag_scores_as_untagged(tmp_store, fake_gateway):
    build(tmp_store, tag="on_roadmap", state="removed")
    assert score(tmp_store, fake_gateway)[0]["roadmap"] == 1.0


def test_shipped_scores_only_post_ship_evidence(tmp_store, fake_gateway):
    build(tmp_store, tag="shipped", post_ship=("i1", "i3"))
    (s,) = score(tmp_store, fake_gateway)
    assert s["breadth"] == pytest.approx(math.log2(3), abs=1e-9)  # A and P1
    assert s["severity"] == pytest.approx((4_000_000 + 3 * 50_000) / 1_050_000, abs=1e-9)
    assert s["value"] == pytest.approx(1 + math.log10(10.5), abs=1e-9)
    assert s["corroboration"] == 1.3 and s["recency"] == 1.0 and s["unresolved_insights"] == 0
    assert s["renewal"] == pytest.approx(1 + 0.25 * 1_000_000 / 1_050_000, abs=1e-9)


def test_shipped_without_post_ship_evidence_has_no_score(tmp_store, fake_gateway):
    build(tmp_store, tag="shipped", post_ship=())
    assert score(tmp_store, fake_gateway) == []


def test_floors_recency_and_value(tmp_store, fake_gateway):
    build(tmp_store, insights=[("i1", "C", 1, "support", "2026-01-01T09:00:00Z")])
    (s,) = score(tmp_store, fake_gateway)
    assert s["recency"] == 0.2 and s["value"] == 0.5 and s["corroboration"] == 1.0  # 1 + log10(10,000/100,000) = 0 -> floor
    assert s["renewal"] == 1.0  # C has no renewal date: missing stays missing
