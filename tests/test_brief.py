import itertools
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from signal_engine import contracts as c, pipeline
from signal_engine.brief import fact_sheet, run
from signal_engine.store import insight_id, raw_id, snippet_id

AS_OF = date(2026, 11, 3)
QUOTES = {"A1": "the bulk upload keeps timing out", "A2": "we re-key every claim by hand", "A3": "adjusters lose an hour a day"}


def seed(store, extra_opps=()):
    """Three accounts, three insights (sales, support, support), opportunity O1 scored 9; extra_opps = [(id, total, tag)]."""
    accts = [("A1", "Northgate Mutual", 1200000.0, "2026-12-01"), ("A2", "Harbour Assurance", 750000.0, "2027-06-01"),
             ("A3", "Pennine Cover", 500000.0, None)]
    ids = {}
    for (a, name, arr, renewal), route in zip(accts, ["sales", "support", "support"]):
        source = "gong" if route == "sales" else "intercom"
        store.insert("account", c.Account(account_id=a, name=name, arr_gbp=arr, renewal_date=renewal))
        r = raw_id(source, a)
        store.insert("raw_record", c.RawRecord(raw_id=r, source=source, route=route, source_id=a, account_id=a,
                                               occurred_at="2026-10-01", payload_json={}))
        s = snippet_id(r, 0, QUOTES[a])
        store.insert("snippet", c.Snippet(snippet_id=s, raw_id=r, text=QUOTES[a]))
        ids[a] = insight_id(s, QUOTES[a])
        store.insert("insight", c.Insight(insight_id=ids[a], snippet_id=s, run_id="r1", problem="p", quote=QUOTES[a],
                                          quote_match="exact", severity=2, account_id=a))
    for oid, total, tag in [("O1", 9.0, "none"), *extra_opps]:
        store.insert("opportunity", c.Opportunity(opportunity_id=oid, title=f"Title {oid}", problem_statement="Bulk upload of claims fails",
                                                  bucket="fnol_intake", first_seen_as_of="2026-10-20", tag=tag))
        store.insert("score", c.Score(opportunity_id=oid, run_id="r1", total=total, breadth=0, severity=1, value=0, corroboration=0,
                                      recency=0, renewal=0, roadmap=0))
        for i in (ids.values() if oid == "O1" else [ids["A1"]]):
            store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id=oid, insight_id=i, similarity=0.9))
    return ids


def good_body(ids):
    a, b, cc = ids["A1"], ids["A2"], ids["A3"]
    return (f'# T\n## Problem\nUploads fail [i:{a}] [i:{b}] [i:{cc}].\n## Who is affected\n- 3 accounts, £2.5m of ARR [i:{a}] [i:{b}] [i:{cc}]\n'
            f'## Evidence\n- Northgate Mutual: "the bulk upload keeps timing out" [i:{a}]\n')


def make_ctx(gw, store, top_n=10):
    return pipeline.RunContext(store, gw, "r1", AS_OF, Path("."), 42, "all", "demo", Path("."), {"pipeline": {"top_n": top_n}}, None)


def test_fact_sheet_is_computed_from_the_store(tmp_store):
    seed(tmp_store)
    f = fact_sheet(tmp_store, "O1", AS_OF)
    assert (f["accounts_n"], f["mentions_n"], f["routes_n"], f["arr_total_gbp"], f["renewals_90d_n"]) == (3, 3, 2, 2450000.0, 1)
    assert f["mentions_by_route"] == {"sales": 1, "support": 2}


def test_fact_sheet_concurrent_reads_hold_lock(tmp_store, monkeypatch):
    seed(tmp_store, [("O2", 5.0, "none"), ("O3", 1.0, "none")])
    expected = {oid: fact_sheet(tmp_store, oid, AS_OF) for oid in ("O1", "O2", "O3")}
    connection = tmp_store.db

    class CheckedConnection:
        def execute(self, *args, **kwargs):
            assert tmp_store.lock._is_owned(), "shared connection accessed without lock"
            return connection.execute(*args, **kwargs)

    ids = ["O1", "O2", "O3"] * 134
    with monkeypatch.context() as patch:
        patch.setattr(tmp_store, "db", CheckedConnection())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda oid: fact_sheet(tmp_store, oid, AS_OF), ids))
    assert results == [expected[oid] for oid in ids]


def test_run_stores_passing_brief_and_proposes(tmp_store, fake_gateway):
    ids = seed(tmp_store)
    gw = fake_gateway({"brief": {"body_md": good_body(ids), "citations": []}})
    run(make_ctx(gw, tmp_store))
    (b,) = tmp_store.select("brief")
    assert b["check_status"] == "passed" and b["check_failures_json"] == [] and sorted(b["citations_json"]) == sorted(ids.values())
    assert b["call_id"] in {r["call_id"] for r in tmp_store.select("model_call")} and b["model"] == "qwen/qwen3.8-max-0902"
    assert tmp_store.select("opportunity", {"opportunity_id": "O1"})[0]["status"] == "proposed"
    (ev,) = tmp_store.select("audit_event")
    assert (ev["actor_kind"], ev["action"]) == ("system", "opportunity.transition")


def test_failing_brief_retries_once_then_stores_failed_checks(tmp_store, fake_gateway):
    ids = seed(tmp_store)
    gw = fake_gateway({"brief": {"body_md": good_body(ids).replace("£2.5m", "£2.9m"), "citations": []}})
    run(make_ctx(gw, tmp_store))
    assert len(gw.calls) == 2 and "numbers: " in gw.calls[1][2]["messages"][0]["content"]
    (b,) = tmp_store.select("brief")
    assert b["check_status"] == "failed_checks" and b["check_failures_json"][0]["rule"] == "numbers"


def test_retry_that_fixes_the_brief_passes(tmp_store, fake_gateway):
    ids = seed(tmp_store)
    drafts = itertools.cycle([good_body(ids).replace("£2.5m", "£2.9m"), good_body(ids)])
    gw = fake_gateway({"brief": lambda body: {"body_md": next(drafts), "citations": []}})
    run(make_ctx(gw, tmp_store))
    assert tmp_store.select("brief")[0]["check_status"] == "passed" and len(gw.calls) == 2


def test_top_n_by_score_skips_tagged(tmp_store, fake_gateway):
    ids = seed(tmp_store, [("O2", 5.0, "none"), ("O3", 1.0, "none"), ("O4", 99.0, "shipped")])
    gw = fake_gateway({"brief": {"body_md": good_body(ids), "citations": []}})
    run(make_ctx(gw, tmp_store, top_n=2))
    assert sorted(b["opportunity_id"] for b in tmp_store.select("brief")) == ["O1", "O2"]
