"""Ground-truth suite metrics on a small hand-built store and ground-truth dict."""

import pytest
from pipe5 import AS_OF, ctx_for, seed_account, seed_snippet
from signal_engine import config, contracts as c, rank
from signal_engine.evals import ground_truth as gt
from signal_engine.store import insight_id

CFG = config.load("ranking")


def mention(key, account="A01", stance=None, post=False, at=0):
    return {"id": f"m-{key}", "source": "intercom", "route": "support", "source_id": key, "locator": {}, "at_ms": at, "account": account,
            "occurred_at": "2026-10-20T09:00:00Z", "stance": stance, "post_ship": post}


def theme(tid, kind, keys, bucket="documents_evidence", **kw):
    return {"id": tid, "kind": kind, "title": tid, "bucket": bucket, "severity": 3, "stances": [], "product_ref": None, "hard_negatives": [],
            "expected": {}, "mentions": [mention(k, **kw.get(k, {})) for k in keys]}


def truth_dict():
    themes = [theme("rt-a", "real", ["a1", "a2", "a3", "a4"]), theme("rt-b", "real", ["b1", "b2", "b3", "b4"], "reserves_payments"),
              theme("nz-n", "noise", ["n1", "n2"], None),
              {**theme("cx-c", "contradictory", ["c1", "c2"], "triage_assignment", c1={"stance": "more"}, c2={"stance": "less"}), "stances": ["more", "less"]},
              {**theme("sh-s", "shipped", ["s1", "s2"], s2={"post": True}), "product_ref": {"source": "shortcut", "id": 4127}}]
    return {"schema_version": 1, "accounts": {"A01": {"hubspot_id": "H1", "name": "One"}, "A02": {"hubspot_id": "H2", "name": "Two"}},
            "themes": themes, "noise": [{"source": "intercom", "source_id": "z1", "at_ms": 0, "category": "pricing"}],
            "join_traps": [{"source": "intercom", "source_id": "t1", "expected_account": None, "reason": "personal email"}]}


DROPPED = {"a4": 1.0, "n2": 3.0}
GROUPS = {"OA": ["a1", "a2", "a3"], "OB1": ["b1", "b2"], "OB2": ["b3", "b4"], "ON": ["n1"], "OC": ["c1", "c2"], "OS": ["s1", "s2"]}
TOTALS = {"OA": 20, "OB1": 10, "OB2": 9, "OC": 8, "OS": 3, "ON": 1, "OP": 5}


def add_opp(store, oid, ids, keys, tag="none", total=None):
    store.insert("opportunity", c.Opportunity(opportunity_id=oid, title=oid, problem_statement=oid, bucket="documents_evidence", first_seen_as_of=AS_OF,
                                              tag=tag, tag_ref="shortcut:4127" if tag == "shipped" else None, tag_state="proposed" if tag == "shipped" else None))
    for k in keys:
        store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id=oid, insight_id=ids[k], similarity=0.9, post_ship=oid == "OS" and k == "s2"))
    store.insert("score", c.Score(opportunity_id=oid, run_id="r1", total=total or TOTALS[oid], breadth=1, severity=1, value=1, corroboration=1,
                                  recency=1, renewal=1, roadmap=1))


def build(store, groups=GROUPS, extra=()):
    """Snippets and insights for every mention (a4, n2, z1 and t1 are dropped, so have no insight), then the opportunities of `groups`."""
    seed_account(store, "H1", 1_000_000, "2026-12-01")
    seed_account(store, "H2", 500_000, None)
    bucket = {"a": "documents_evidence", "b": "reserves_payments"}
    ids = {}
    for key in sorted({k for ks in groups.values() for k in ks} | set(DROPPED) | {"z1", "t1", *extra}):
        acct = None if key == "t1" else "H1"
        dropped = key in DROPPED or key in ("z1", "t1")
        sid = seed_snippet(store, key, f"{key} words about the problem here today", account=acct, status="resolved" if acct else "unresolved",
                           decision="drop" if dropped else "keep", bucket=bucket.get(key[0], "documents_evidence"))
        if dropped:
            store.update("triage", {"snippet_id": sid}, {"is_signal_p": 0.05, "audit_weight": DROPPED.get(key, 1.0)})
            continue
        ids[key] = insight_id(sid, "q")
        store.insert("insight", c.Insight(insight_id=ids[key], snippet_id=sid, run_id="r1", problem=f"problem {key}", quote=f"{key} quote words one two three",
                                          quote_match="exact", severity=3, account_id=acct, account_status="resolved" if acct else "unresolved"))
    for oid, keys in groups.items():
        add_opp(store, oid, ids, keys, "shipped" if oid == "OS" else "none")
    return ids


@pytest.fixture
def an(tmp_store):
    build(tmp_store)
    return gt.Analysis(tmp_store, gt.Truth(truth_dict()))


def test_snippet_labels_follow_evals_4_1(an):
    raw = lambda s: {"source": "intercom", "source_id": s}  # noqa: E731
    assert an.truth.label(raw("a1"), 0, 0)[0] == "signal:rt-a"
    assert an.truth.label(raw("n1"), 0, 100)[0] == "noise_theme:nz-n"
    assert an.truth.label(raw("z1"), 0, 0)[0] == "noise"
    assert an.truth.label(raw("a1"), 500, 900)[0] == "unlabelled"       # the mention is outside the snippet window
    assert an.truth.label(raw("nobody"), 0, 0)[0] == "unlabelled"


def test_triage_metrics_and_weighted_audit_estimate(an):
    m = gt.triage_metrics(an)
    assert m["signal_recall"] == pytest.approx(11 / 12)           # 12 signal mentions, a4 dropped
    assert m["noise_drop_rate"] == pytest.approx(2 / 3)           # n1 kept; n2 and z1 dropped
    assert m["bucket_accuracy"] == pytest.approx(9 / 11)           # the two contradictory snippets carry a different bucket
    # drops: a4 (signal, weight 1), n2 (noise, 3), z1 (noise, 1), t1 (join trap, 1): estimate 1/6, exact 1/4
    assert m["noise_audit_estimate"] == pytest.approx(1 / 6) and m["noise_audit_exact"] == pytest.approx(1 / 4)


def test_extract_metrics_counts_join_traps_and_attribution(an):
    assert gt.extract_metrics(an) == {"quote_verification": 1.0, "attribution": 1.0}
    an.store.update("insight", {"insight_id": an.store.select("insight")[0]["insight_id"]}, {"account_id": "H9"})
    assert gt.extract_metrics(gt.Analysis(an.store, an.truth))["attribution"] < 1.0


def test_cluster_recovered_split_purity(an):
    m, recovered = gt.cluster_metrics(an)
    assert set(recovered) == {"rt-a", "rt-b"} and m["themes_total"] == 2
    assert m["split_themes"] == 1 and m["over_merges"] == 0       # rt-b is held 50/50 by two opportunities
    assert m["mean_purity"] == 1.0


def test_over_merge_counts_two_real_themes_in_one_opportunity(tmp_store):
    build(tmp_store, {**GROUPS, "OA": ["a1", "a2", "a3", "b1", "b2"], "OB1": [], "OB2": ["b3", "b4"]})
    m, _ = gt.cluster_metrics(gt.Analysis(tmp_store, gt.Truth(truth_dict())))
    assert m["over_merges"] == 1 and m["mean_purity"] < 1.0


def brief(store, oid, ids):
    store.insert("brief", c.Brief(brief_id="B" + oid, opportunity_id=oid, run_id="r1", body_md="x", citations_json=ids, check_status="passed",
                                  prompt_version="w@1", model="m"))


def test_contradictory_pass_warn_fail(tmp_store):
    ids = build(tmp_store)
    truth = gt.Truth(truth_dict())
    brief(tmp_store, "OC", [ids["c1"], ids["c2"]])
    assert gt.contradictory(gt.Analysis(tmp_store, truth)) == "PASS"
    tmp_store.db.execute("DELETE FROM brief")
    brief(tmp_store, "OC", [ids["c1"]])                           # one opportunity, one stance cited: a stance lost
    assert gt.contradictory(gt.Analysis(tmp_store, truth)) == "FAIL"
    tmp_store.db.execute("DELETE FROM opportunity_insight WHERE insight_id=?", (ids["c2"],))
    assert gt.contradictory(gt.Analysis(tmp_store, truth)) == "FAIL"   # the stance is in no opportunity
    add_opp(tmp_store, "OC2", ids, ["c2"], total=7)
    assert gt.contradictory(gt.Analysis(tmp_store, truth)) == "WARN"   # split by stance


def test_tag_metrics_shipped_and_post_ship(tmp_store):
    build(tmp_store)
    truth = gt.Truth(truth_dict())
    m, problems = gt.tag_metrics(gt.Analysis(tmp_store, truth))
    assert m["tag_ok"] and m["post_ship_found"] == 1 and m["post_ship_total"] == 1 and not problems
    tmp_store.update("opportunity", {"opportunity_id": "OS"}, {"tag": "none"})
    assert not gt.tag_metrics(gt.Analysis(tmp_store, truth))[0]["tag_ok"]


def test_rank_metrics_top_set_equals_real_themes(tmp_store):
    build(tmp_store)
    r = gt.rank_metrics(gt.Analysis(tmp_store, gt.Truth(truth_dict())), CFG, AS_OF, top=3)
    assert r["top_labels"] == ["rt-a", "rt-b", "rt-b"] and r["top_set"] is None  # three slots but two real themes: no verdict
    r2 = gt.rank_metrics(gt.Analysis(tmp_store, gt.Truth(truth_dict())), CFG, AS_OF, top=2)
    assert r2["top_set"] is True and r2["noise_in_top10"] == 1 and r2["probe_below_six"] is None and -1.0 <= r2["kendall_tau"] <= 1.0


def test_probe_must_rank_below_all_real(tmp_store):
    d = truth_dict()
    d["themes"].append(theme("lt-p", "probe", ["p1"]))
    ids = build(tmp_store, extra=("p1",))
    add_opp(tmp_store, "OP", ids, ["p1"])
    assert gt.rank_metrics(gt.Analysis(tmp_store, gt.Truth(d)), CFG, AS_OF, top=2)["probe_below_six"] is True
    tmp_store.update("score", {"opportunity_id": "OP"}, {"total": 15})
    assert gt.rank_metrics(gt.Analysis(tmp_store, gt.Truth(d)), CFG, AS_OF, top=2)["probe_below_six"] is False


def test_score_recompute_flags_a_wrong_total(tmp_store, fake_gateway):
    build(tmp_store)
    rank.run(ctx_for(tmp_store, fake_gateway(), run_id="r1"))  # replaces the fixture totals with the real formula
    assert gt.recompute_scores(tmp_store, CFG, AS_OF) == []
    tmp_store.update("score", {"opportunity_id": "OA"}, {"total": 99.0})
    assert gt.recompute_scores(tmp_store, CFG, AS_OF) == ["OA"]


def test_deterministic_audit_chain_and_trigger(tmp_store):
    build(tmp_store)
    tmp_store.append_audit("system", "system", "x", "t", "1", {})
    det = gt.deterministic(tmp_store, CFG, AS_OF)
    assert det["audit_chain"] is True and det["vpc"] == 0 and det["accounts"] == 0
    assert tmp_store.verify_audit_chain()  # the trigger probe rolled back and left the chain whole


def test_score_gates_and_floors(tmp_store):
    build(tmp_store)
    m, detail, gates = gt.score(tmp_store, truth_dict(), AS_OF, floors=gt.FLOORS_42, bools=gt.BOOLS_42, top=2)
    assert gates["signal_recall"] is True and gates["noise_drop_rate"] is True   # 0.92 and 0.67 meet floors 0.90 and 0.60
    assert gates["themes_recovered"] is True and gates["split_themes"] is True    # one split is within the floor of 1
    assert "deterministic" in gates and detail["contradictory"] in ("PASS", "WARN", "FAIL")


def test_leak_check_finds_theme_text_in_exposed_files(tmp_path, monkeypatch):
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "themes.yaml").write_text('# c\n{"themes": [{"id": "rt-x", "title": "Quirky title", "facts": ["a secret fact"], "synonyms": ["odd word"]}]}\n', encoding="utf-8")
    monkeypatch.setitem(gt.SPEC_DIRS, 42, spec)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "raw" / "a.json").write_text("a Secret Fact here", encoding="utf-8")
    (tmp_path / "config" / "ok.yaml").write_text("nothing", encoding="utf-8")
    (tmp_path / "config" / "syn.yaml").write_text("an odd word", encoding="utf-8")
    assert gt.leak_check((42,), tmp_path) == ["data/raw/a.json", "config/syn.yaml"]
