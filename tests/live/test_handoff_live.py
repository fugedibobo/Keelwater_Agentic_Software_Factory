"""Live smoke: one intent document and its factory job (validity and de-identification lines), plus the outtake drafts.
Run by a sonnet subagent: uv run pytest tests/live/test_handoff_live.py --live -s -q  (spend under USD 0.05)."""

import json

import pytest

from signal_engine import handoff, outtake
from test_handoff import OID, setup
from test_outtake import story
from test_brief import make_ctx

pytestmark = pytest.mark.live


def test_intent_document_factory_job_and_outtake_drafts(live_gateway):
    store = live_gateway.store
    setup(store)
    story(store, 4127)
    ctx = make_ctx(live_gateway, store)
    handoff.run(ctx)
    (h,) = store.select("handoff")
    print("\n--- INTENT DOCUMENT\n" + h["intent_doc_md"])
    print("--- FACTORY JOB\n" + json.dumps(h["factory_job_json"], indent=1))
    print(f"--- schema valid: {handoff.schema_errors(h['factory_job_json']) == []}; "
          f"de-identified: {handoff.deidentify_errors(h['factory_job_json'], store) == []}; errors: {h['errors_json']}")
    outtake.run(ctx)
    drafts = store.select("outtake")
    for d in drafts:
        print(f"--- OUTTAKE {d['kind']} ({d['story_ref']}, {d['status']})\n{d['body_md']}")
    assert OID and {d["kind"] for d in drafts} >= set(outtake.KINDS) and {d["status"] for d in drafts} == {"draft"}
    print(f"spend USD {live_gateway.spent:.4f}")
    assert live_gateway.spent < 0.05
