import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from signal_engine import contracts as c
from signal_engine import store as st
from signal_engine.store import Store


def opp(store, oid="o1", status="proposed", insights=("i2", "i1")):
    store.insert("opportunity", c.Opportunity(opportunity_id=oid, title="t", problem_statement="p", bucket="fnol_intake",
                                              status=status, squad="intake_claims", first_seen_as_of="2026-11-03"))
    for i in insights:
        store.insert("opportunity_insight", c.OpportunityInsight(opportunity_id=oid, insight_id=i, similarity=0.9))


def status(store, oid="o1"):
    return store.select("opportunity", {"opportunity_id": oid})[0]["status"]


def test_ids_are_content_hashes():
    assert st.raw_id("gong", "g1") == st.raw_id("gong", "g1") != st.raw_id("gong", "g2")
    ids = [st.raw_id("gong", "g1"), st.snippet_id("r", 0, "hello"), st.insight_id("s", "q"), st.opportunity_id("i")]
    assert all(len(i) == 16 and int(i, 16) >= 0 for i in ids) and len(set(ids)) == 4


def test_audit_triggers_and_chain(tmp_path):
    s = Store.fresh(tmp_path / "a.sqlite")
    s.append_audit("p", "person", "accept", "opportunity", "o", {"x": 1})
    s.append_audit("p", "person", "edit", "opportunity", "o", {})
    assert s.verify_audit_chain()
    for sql in ("UPDATE audit_event SET actor='x'", "DELETE FROM audit_event"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            s.db.execute(sql)
    s.db.commit()
    s.close()
    copy = tmp_path / "tampered.sqlite"
    shutil.copy(tmp_path / "a.sqlite", copy)
    t = Store(copy)
    t.db.execute("DROP TRIGGER audit_no_update")
    t.db.execute("UPDATE audit_event SET details_json='{}' WHERE rowid=1")
    t.db.commit()
    assert not t.verify_audit_chain()
    assert Store(tmp_path / "a.sqlite").verify_audit_chain()


def test_transition_rules(tmp_store):
    opp(tmp_store)
    with pytest.raises(ValueError, match="illegal"):
        st.transition(tmp_store, "o1", "shipped", "ann", "person")
    with pytest.raises(PermissionError):
        st.transition(tmp_store, "o1", "accepted", "pipeline", "system")
    assert status(tmp_store) == "proposed" and tmp_store.select("audit_event") == []  # refusals leave no trace
    ev = st.transition(tmp_store, "o1", "accepted", "ann", "person", {"run_id": "r"})
    (row,) = tmp_store.select("audit_event", {"event_id": ev})
    assert row["details_json"]["evidence_snapshot"] == ["i1", "i2"] and row["actor"] == "ann"
    st.transition(tmp_store, "o1", "intent_drafted", "pipeline", "system")  # system may pass non-gates
    assert tmp_store.verify_audit_chain()


def test_every_human_gate_refuses_system(tmp_store):
    for to in ("accepted", "merged", "rejected", "parked"):
        opp(tmp_store, f"o_{to}")
        with pytest.raises(PermissionError):
            st.transition(tmp_store, f"o_{to}", to, "bot", "system")
    opp(tmp_store, "pk", status="parked")
    with pytest.raises(PermissionError):
        st.transition(tmp_store, "pk", "proposed", "bot", "system")
    with pytest.raises(PermissionError):
        st.reassign(tmp_store, "pk", "platform_access", "bot", "system")


def test_undo_within_and_after_ten_seconds(tmp_store):
    opp(tmp_store)
    ev = st.transition(tmp_store, "o1", "rejected", "ann", "person")
    at = datetime.fromisoformat(tmp_store.select("audit_event", {"event_id": ev})[0]["at"])
    with pytest.raises(PermissionError):
        st.undo(tmp_store, ev, "bob", now=at + timedelta(seconds=2))
    with pytest.raises(ValueError, match="10 seconds"):
        st.undo(tmp_store, ev, "ann", now=at + timedelta(seconds=11))
    assert status(tmp_store) == "rejected"
    undo_ev = st.undo(tmp_store, ev, "ann", now=at + timedelta(seconds=9))
    assert status(tmp_store) == "proposed"
    assert tmp_store.select("annotation")[0]["action"] == "undo" and tmp_store.select("annotation")[0]["undo_of"] == ev
    assert len(tmp_store.select("audit_event")) == 2 and undo_ev  # nothing deleted, one new event
    with pytest.raises(ValueError, match="already"):
        st.undo(tmp_store, ev, "ann", now=at + timedelta(seconds=9))
    assert tmp_store.verify_audit_chain()


def test_reassign_and_undo(tmp_store):
    opp(tmp_store)
    ev = st.reassign(tmp_store, "o1", "platform_access", "ann", "person")
    assert tmp_store.select("opportunity")[0]["squad"] == "platform_access"
    st.undo(tmp_store, ev, "ann")
    assert tmp_store.select("opportunity")[0]["squad"] == "intake_claims"


def seed_outputs(store, run_id, stamp):
    store.insert("insight", c.Insight(insight_id="i1", snippet_id="s", run_id=run_id, problem="p", quote=" ".join(["q"] * 6),
                                      quote_match="exact", severity=3, embedding=[0.1, 0.2]))
    store.insert("brief", c.Brief(brief_id=f"b-{run_id}", opportunity_id="o1", run_id=run_id, body_md="b", citations_json=["i1"],
                                  check_status="passed", prompt_version="p", model="m"))
    store.insert("score", c.Score(opportunity_id="o1", run_id=run_id, total=1, breadth=1, severity=1, value=1, corroboration=1,
                                  recency=1, renewal=1, roadmap=1))
    store.insert("judge_version", c.JudgeVersion(judge_version_id="j", judge="signal", prompt_version="p", model="m", state_changed_at=stamp))
    store.insert("model_call", c.ModelCall(call_id=f"c-{run_id}", run_id=run_id, stage="x", target_type="t", target_id="i",
                                           model="m", profile="demo", input_hash="a", output_hash="b", cost_usd=run_id.__len__(),
                                           latency_ms=len(stamp), cached=run_id == "r2"))
    store.append_audit("sys", "system", "x", "t", "i", {}, at=stamp)


def test_output_hash_ignores_run_ids_timestamps_latency_cost_and_cached(tmp_path):
    a, b = Store.fresh(tmp_path / "a.sqlite"), Store.fresh(tmp_path / "b.sqlite")
    seed_outputs(a, "r1", "2026-01-01T00:00:00+00:00")
    seed_outputs(b, "r2", "2027-05-05T10:10:10.123+00:00")
    assert a.output_hash() == b.output_hash()
    b.update("insight", {"insight_id": "i1"}, {"problem": "changed"})
    assert a.output_hash() != b.output_hash()


def test_insert_validates_and_json_roundtrips(tmp_store):
    with pytest.raises(Exception):
        tmp_store.insert("insight", c.Insight.model_construct(insight_id="i"))
    seed_outputs(tmp_store, "r1", "t")
    assert tmp_store.select("insight")[0]["embedding"] == [0.1, 0.2]
    assert tmp_store.select("brief")[0]["citations_json"] == ["i1"]
