from pipe5 import AS_OF, ctx_for, embedder, seed_account, seed_snippet
from signal_engine import contracts as c, tag
from signal_engine.store import insight_id, raw_id

VEC = {"Bulk upload": [1, 0, 0, 0], "Milestone notifications": [0, 1, 0, 0], "Document type filter": [0.9, 0, 0.3, 0]}


def story(store, sid, name, completed=True, completed_at="2026-10-06T10:00:00Z", description=None):
    store.insert("raw_record", c.RawRecord(raw_id=raw_id("shortcut", str(sid)), source="shortcut", source_id=str(sid), payload_json={
        "id": sid, "name": name, "story_type": "feature", "completed": completed, "completed_at": completed_at,
        "description": description}))


def page(store, pid, name, status):
    store.insert("raw_record", c.RawRecord(raw_id=raw_id("notion", pid), source="notion", source_id=pid, payload_json={
        "id": pid, "properties": {"Name": {"title": [{"plain_text": name}]}, "Status": {"status": {"name": status}},
                                  "Target": {"date": None}, "Problem": {"rich_text": [{"plain_text": "Policyholders want updates."}]}}}))


def opportunity(store, oid, centroid, occurred, state=None):
    store.insert("opportunity", c.Opportunity(opportunity_id=oid, title=oid, problem_statement="p", bucket="documents_evidence",
                                              first_seen_as_of=AS_OF, centroid=centroid, tag_state=state))
    ids = []
    for n, when in enumerate(occurred):
        sid = seed_snippet(store, f"{oid}{n}", f"{oid} words number {n} about the problem here", occurred=when)
        iid = insight_id(sid, "q")
        store.insert("insight", c.Insight(insight_id=iid, snippet_id=sid, run_id="r1", problem="p", quote="a b c d e f",
                                          quote_match="exact", severity=2, account_id="A01", account_status="resolved"))
        store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id=oid, insight_id=iid, similarity=0.9))
        ids.append(iid)
    return ids


def post_ship(store):
    return {r["insight_id"]: bool(r["post_ship"]) for r in store.select("opportunity_insight")}


def test_tags_shipped_and_roadmap_and_flags_post_ship_by_date(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    story(tmp_store, 4127, "Bulk upload", description="Upload many documents at once")
    story(tmp_store, 4130, "Document type filter")  # same-bucket hard negative
    story(tmp_store, 4131, "Milestone notifications", completed=False, completed_at=None)  # not shipped: ignored
    page(tmp_store, "n1", "Milestone notifications", "In progress")
    page(tmp_store, "n2", "Bulk upload", "Released")  # not planned or in progress: ignored
    a = opportunity(tmp_store, "oppA", [1, 0.2, 0, 0], ["2026-10-01T09:00:00Z", "2026-10-20T09:00:00Z", "2026-10-06T10:00:00Z"])
    opportunity(tmp_store, "oppB", [0, 0.1, 1, 0], ["2026-10-20T09:00:00Z"])
    opportunity(tmp_store, "oppC", [0.1, 1, 0, 0], ["2026-10-20T09:00:00Z"])
    gw = fake_gateway({"embed": embedder(VEC)})
    tag.run(ctx_for(tmp_store, gw))
    got = {o["opportunity_id"]: o for o in tmp_store.select("opportunity")}
    assert (got["oppA"]["tag"], got["oppA"]["tag_ref"], got["oppA"]["tag_state"]) == ("shipped", "shortcut:4127", "proposed")
    assert (got["oppC"]["tag"], got["oppC"]["tag_ref"], got["oppC"]["tag_state"]) == ("on_roadmap", "notion:n1", "proposed")
    assert (got["oppB"]["tag"], got["oppB"]["tag_ref"], got["oppB"]["tag_state"]) == ("none", None, None)  # hard negative stays untagged
    flags = post_ship(tmp_store)
    assert [flags[i] for i in a] == [False, True, False]  # before, after, and exactly at completed_at (not after)
    assert not any(v for k, v in flags.items() if k not in a)


def test_pm_decision_is_not_overwritten(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    story(tmp_store, 4127, "Bulk upload")
    opportunity(tmp_store, "oppA", [1, 0.2, 0, 0], ["2026-10-20T09:00:00Z"], state="removed")
    tag.run(ctx_for(tmp_store, fake_gateway({"embed": embedder(VEC)})))
    assert tmp_store.select("opportunity")[0]["tag"] == "none"
