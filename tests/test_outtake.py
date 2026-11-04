from datetime import date

from signal_engine import contracts as c, outtake
from signal_engine.store import raw_id, snippet_id
from test_brief import make_ctx


def story(store, sid, **kw):
    s = {"id": sid, "name": f"Story {sid}", "story_type": "feature", "completed": True, "completed_at": "2026-10-06T09:00:00Z",
         "description": "Upload many documents to a claim at once", **kw}
    store.insert("raw_record", c.RawRecord(raw_id=raw_id("shortcut", str(sid)), source="shortcut", source_id=str(sid), payload_json=s))


def call(store, sid, acct, when, texts):
    r = raw_id("gong", sid)
    store.insert("raw_record", c.RawRecord(raw_id=r, source="gong", route="sales", source_id=sid, account_id=acct, occurred_at=when, payload_json={}))
    for i, (who, t) in enumerate(texts):
        store.insert("snippet", c.Snippet(snippet_id=snippet_id(r, i, t), raw_id=r, speaker_email=who, text=t, start_ms=i))


def seed(store):
    story(store, 4127)
    story(store, 4133, story_type="bug")
    story(store, 4140, completed=False, completed_at=None)
    story(store, 4150, completed_at="2026-12-01T00:00:00Z")  # after as_of
    store.insert("account", c.Account(account_id="A1", name="Northgate Mutual", arr_gbp=1.0))
    store.insert("account", c.Account(account_id="P1", name="Prospect Co"))
    call(store, "old", "A1", "2026-09-01", [("x@northgate.example", "old call")])
    call(store, "new", "A1", "2026-10-20", [("ada@keelwater.example", "staff talk"), ("x@northgate.example", "we upload documents one by one")])
    call(store, "newer-prospect", "P1", "2026-10-30", [("y@prospect.example", "prospect talk")])


def test_drafts_three_kinds_for_shipped_feature_only_and_never_accepts(tmp_store, fake_gateway):
    seed(tmp_store)
    gw = fake_gateway({"outtake": {"body_md": "draft text"}})
    outtake.run(make_ctx(gw, tmp_store))
    rows = tmp_store.select("outtake")
    story_rows = [r for r in rows if r["kind"] != "followup_brief"]
    assert sorted((r["story_ref"], r["kind"]) for r in story_rows) == [("4127", k) for k in sorted(outtake.KINDS)]
    assert {r["status"] for r in rows} == {"draft"}
    calls = {m["call_id"] for m in tmp_store.select("model_call")}
    assert all(r["call_id"] in calls for r in rows)
    assert all("feature flag" in b["messages"][0]["content"] for _, _, b in gw.calls)  # ADR-012 wording is in every prompt


def test_second_run_adds_nothing(tmp_store, fake_gateway):
    seed(tmp_store)
    gw = fake_gateway({"outtake": {"body_md": "draft text"}})
    outtake.run(make_ctx(gw, tmp_store))
    n, rows = len(gw.calls), len(tmp_store.select("outtake"))
    outtake.run(make_ctx(gw, tmp_store))
    assert len(gw.calls) == n and len(tmp_store.select("outtake")) == rows


def test_followup_uses_latest_existing_customer_call_and_customer_words(tmp_store, fake_gateway):
    seed(tmp_store)
    gw = fake_gateway({"outtake": {"body_md": "draft text"}})
    outtake.run(make_ctx(gw, tmp_store))
    (f,) = [r for r in tmp_store.select("outtake") if r["kind"] == "followup_brief"]
    assert f["story_ref"] == "call:new" and f["status"] == "draft"
    prompt = next(b["messages"][0]["content"] for s, k, b in gw.calls if "<customer_said>" in b["messages"][0]["content"])
    assert "one by one" in prompt and "staff talk" not in prompt and "4127" in prompt and "4133" not in prompt


def test_story_after_as_of_is_not_shipped(tmp_store):
    seed(tmp_store)
    ctx = make_ctx(None, tmp_store)
    assert ctx.as_of == date(2026, 11, 3) and [s["id"] for s in outtake.shipped_stories(ctx)] == [4127]
