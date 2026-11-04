from pipe5 import ctx_for, embedder, seed_account, seed_snippet
from signal_engine import cluster, contracts as c
from signal_engine.store import Store, insight_id, opportunity_id

VEC = {"AAA1": [1, .10, 0, 0], "AAA2": [1, .20, 0, 0], "AAA3": [1, .15, 0, 0], "AAA4": [1, .12, 0, 0],
       "BBB1": [0, 1, .10, 0], "BBB2": [0, 1, .20, 0], "CCC1": [0, 0, 1, 0]}
LABEL = {"title": "A title", "problem_statement": "A statement"}


def add(store, tag, match="exact", bucket="documents_evidence"):
    sid = seed_snippet(store, tag, f"{tag} customer words about the problem here", bucket=bucket)
    quote = f"{tag} customer words about the problem here"
    iid = insight_id(sid, quote)
    store.insert("insight", c.Insight(insight_id=iid, snippet_id=sid, run_id="r1", problem="p", quote=quote, quote_match=match,
                                      severity=3, account_id="A01", account_status="resolved"), replace=True)
    return iid


def gateway(fake_gateway):
    return fake_gateway({"embed": embedder(VEC), "cluster_label": LABEL})


def members(store):
    out = {}
    for r in store.select("opportunity_insight"):
        out.setdefault(r["opportunity_id"], set()).add(r["insight_id"])
    return out


def test_first_batch_clusters_with_stable_content_ids(tmp_store, fake_gateway, tmp_path):
    seed_account(tmp_store, "A01", 1000)
    a = [add(tmp_store, t) for t in ("AAA1", "AAA2", "AAA3")]
    b = [add(tmp_store, t) for t in ("BBB1", "BBB2")]
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway)))
    got = members(tmp_store)
    assert got == {opportunity_id(min(a)): set(a), opportunity_id(min(b)): set(b)}
    opp = tmp_store.select("opportunity", {"opportunity_id": opportunity_id(min(a))})[0]
    assert opp["title"] == "A title" and opp["status"] == "new" and opp["squad"] == "handling_payments"
    assert opp["bucket"] == "documents_evidence" and len(opp["centroid"]) == 4

    other = Store.fresh(tmp_path / "again.sqlite")  # same inputs, new store: identical ids
    seed_account(other, "A01", 1000)
    for t in ("BBB2", "AAA3", "AAA1", "BBB1", "AAA2"):
        add(other, t)
    cluster.run(ctx_for(other, fake_gateway_for(other)))
    assert set(members(other)) == set(got)
    other.close()


def fake_gateway_for(store):
    from conftest import FakeGateway
    return FakeGateway(store, {"embed": embedder(VEC), "cluster_label": LABEL}, run_id="r1", tmp=store.path.parent / "cache2")


def test_failed_quotes_are_not_clustered(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    ok = add(tmp_store, "AAA1")
    add(tmp_store, "AAA2", match="failed")
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway)))
    assert members(tmp_store) == {opportunity_id(ok): {ok}}


def test_second_batch_adds_without_moving_first_batch(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    a = [add(tmp_store, t) for t in ("AAA1", "AAA2")]
    b = [add(tmp_store, t) for t in ("BBB1", "BBB2")]
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway)))
    first = members(tmp_store)
    before = {o["opportunity_id"]: o["centroid"] for o in tmp_store.select("opportunity")}
    new_a = [add(tmp_store, t) for t in ("AAA3", "AAA4")]
    new_c = add(tmp_store, "CCC1")
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway), batch="oct"))
    second = members(tmp_store)
    for oid, ids in first.items():
        assert ids <= second[oid]  # additions only
    assert second[opportunity_id(min(a))] == set(a) | set(new_a) and second[opportunity_id(min(b))] == set(b)
    assert second[opportunity_id(new_c)] == {new_c} and len(second) == 3
    assert tmp_store.select("opportunity", {"opportunity_id": opportunity_id(min(a))})[0]["centroid"] != before[opportunity_id(min(a))]
    assert tmp_store.select("opportunity", {"opportunity_id": opportunity_id(min(b))})[0]["centroid"] == before[opportunity_id(min(b))]


def test_join_uses_threshold(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    a = add(tmp_store, "AAA1")
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway)))
    far = add(tmp_store, "BBB1")  # cosine similarity to AAA1 is about 0.1, far below 1 - 0.35
    cluster.run(ctx_for(tmp_store, gateway(fake_gateway), batch="oct"))
    assert members(tmp_store) == {opportunity_id(a): {a}, opportunity_id(far): {far}}
