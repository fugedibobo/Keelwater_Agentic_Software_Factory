import pytest

from signal_engine import handoff
from signal_engine.store import now_iso, transition
from test_brief import good_body, make_ctx, seed

OID = "00000000000000a1"
GOOD = {
    "problem_statement": "Claims handlers cannot upload many documents to a claim at once without failures, which slows claim handling.",
    "acceptance_criteria": [{"given": "a claim with many documents", "when": "a handler uploads them together", "then": "every document is attached"}],
    "non_goals": ["Changing the document viewer"], "constraints": ["Keep existing file size limits"],
    "metric_name": "Bulk upload complaints", "metric_definition": "Insights about failed bulk upload after release",
}


def setup(store, status="accepted"):
    ids = seed(store)
    for t in ("opportunity", "opportunity_insight", "score"):
        store.db.execute(f"UPDATE {t} SET opportunity_id=? WHERE opportunity_id='O1'", (OID,))
    store.db.commit()
    steps = {"new": [], "proposed": [("proposed", "brief", "system")],
             "accepted": [("proposed", "brief", "system"), ("accepted", "pm@keelwater.example", "person")]}[status]
    for to, actor, kind in steps:
        transition(store, OID, to, actor, kind)
    return ids


def gw_for(fake_gateway, ids, **over):
    return fake_gateway({"handoff": lambda body: {"intent_doc_md": good_body(ids), **GOOD, **over}})


def status(store):
    return store.select("opportunity", {"opportunity_id": OID})[0]["status"]


def test_accepted_opportunity_gets_valid_job_and_moves_to_intent_drafted(tmp_store, fake_gateway):
    ids = setup(tmp_store)
    handoff.run(make_ctx(gw_for(fake_gateway, ids), tmp_store))
    (h,) = tmp_store.select("handoff")
    job = h["factory_job_json"]
    assert (h["status"], h["errors_json"]) == ("drafted", []) and handoff.schema_errors(job) == []
    assert status(tmp_store) == "intent_drafted"
    assert job["status"] == "draft" and sorted(h["evidence_snapshot"]) == sorted(ids.values()) == job["evidence"]["insight_ids"]
    assert job["gate_approvals"][0]["gate"] == "opportunity_accepted" and job["gate_approvals"][0]["actor"] == "pm@keelwater.example"
    assert job["evidence"]["intent_doc"]["sha256"] == handoff.sha256(h["intent_doc_md"]) and "Northgate Mutual" in h["intent_doc_md"]
    last = tmp_store.select("audit_event")[-1]
    assert (last["actor_kind"], last["details_json"]["to_status"]) == ("system", "intent_drafted")


def test_accepted_with_handoff_is_not_redrafted(tmp_store, fake_gateway):
    ids = setup(tmp_store)
    gw = gw_for(fake_gateway, ids)
    handoff.run(make_ctx(gw, tmp_store))
    n = len(gw.calls)
    handoff.run(make_ctx(gw, tmp_store))
    assert len(gw.calls) == n and handoff.pending(tmp_store) == []


@pytest.mark.parametrize("statement,needle", [
    ("Northgate Mutual cannot upload many documents to one claim at once without failures.", "account name"),
    ("Handlers report that the bulk upload keeps timing out whenever they attach documents.", "words of insight"),
])
def test_planted_name_or_quote_fails_and_opportunity_stays_accepted(tmp_store, fake_gateway, statement, needle):
    ids = setup(tmp_store)
    handoff.run(make_ctx(gw_for(fake_gateway, ids, problem_statement=statement), tmp_store))
    (h,) = tmp_store.select("handoff")
    assert any(needle in e for e in h["errors_json"]) and status(tmp_store) == "accepted"
    assert [o["opportunity_id"] for o in handoff.pending(tmp_store)] == [OID]  # retried on the next run


def test_schema_invalid_job_stores_errors(tmp_store, fake_gateway):
    ids = setup(tmp_store)
    handoff.run(make_ctx(gw_for(fake_gateway, ids, acceptance_criteria=[]), tmp_store))
    (h,) = tmp_store.select("handoff")
    assert any("acceptance_criteria" in e for e in h["errors_json"]) and status(tmp_store) == "accepted"


def test_failed_citation_checks_are_errors(tmp_store, fake_gateway):
    ids = setup(tmp_store)
    gw = fake_gateway({"handoff": lambda body: {"intent_doc_md": good_body(ids).replace("£2.5m", "£2.9m"), **GOOD}})
    handoff.run(make_ctx(gw, tmp_store))
    (h,) = tmp_store.select("handoff")
    assert len(gw.calls) == 2 and any(e.startswith("citation numbers") for e in h["errors_json"]) and status(tmp_store) == "accepted"


def test_preview_drafts_for_proposed_without_gate_or_person_event(tmp_store, fake_gateway):
    ids = setup(tmp_store, "proposed")
    ctx = make_ctx(gw_for(fake_gateway, ids), tmp_store)
    opp = tmp_store.select("opportunity", {"opportunity_id": OID})[0]
    with pytest.raises(ValueError, match="not accepted"):
        handoff.draft(ctx, opp)
    assert tmp_store.select("handoff") == []
    h = handoff.draft(ctx, opp, preview=True)
    assert h.errors_json == [] and status(tmp_store) == "proposed"
    assert not [e for e in tmp_store.select("audit_event") if e["actor_kind"] == "person"]
    assert "gate_approvals" not in h.factory_job_json and tmp_store.verify_audit_chain()


def test_submit_needs_the_trio_then_revalidates(tmp_store, fake_gateway):
    ids = setup(tmp_store)
    handoff.run(make_ctx(gw_for(fake_gateway, ids), tmp_store))
    (h,) = tmp_store.select("handoff")
    assert handoff.submit(tmp_store, h["handoff_id"], [])  # intent_approved missing
    assert tmp_store.select("handoff")[0]["status"] == "drafted"
    trio = [{"gate": "intent_approved", "actor": a, "role": r, "approved_at": now_iso()}
            for a, r in (("pm@keelwater.example", "pm"), ("des@keelwater.example", "designer"), ("tl@keelwater.example", "tech_lead"))]
    assert handoff.submit(tmp_store, h["handoff_id"], trio) == []
    (h,) = tmp_store.select("handoff")
    assert (h["status"], h["factory_job_json"]["status"], h["errors_json"]) == ("approved", "submitted", [])


def test_norm_follows_evals_32():
    assert handoff.norm("It’s “Fine” — £1,200.50!") == "it's fine £1,200.50"
