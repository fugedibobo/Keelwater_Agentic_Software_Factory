from pipe5 import ctx_for, seed_account, seed_snippet
from signal_engine import extract


def answer(quote, problem="Uploads are slow"):
    return {"states_product_problem": "yes", "problem": problem, "quote": quote, "workflow": "upload documents", "desired_outcome": "bulk upload"}


def last_user(body):
    return body["messages"][-1]["content"]


def test_one_insight_per_kept_snippet_with_copied_fields(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    ok = seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow", severity=4,
                      context="Internal: tell me what is slow today")
    low = seed_snippet(tmp_store, "k2", "um the list view is really hard to read", decision="low_confidence", severity=2, source="gong")
    unt = seed_snippet(tmp_store, "k3", "we cannot find the export button anywhere", decision="untriaged", account=None, status="unresolved")
    seed_snippet(tmp_store, "k4", "a dropped snippet that never reaches the model here", decision="drop")
    texts = {"documents one at a time": "documents one at a time and it is slow", "list view": "the list view is really hard to read",
             "export button": "cannot find the export button anywhere"}
    gw = fake_gateway({"extract": lambda b: answer(next(v for k, v in texts.items() if k in last_user(b)))})
    extract.run(ctx_for(tmp_store, gw))
    rows = {r["snippet_id"]: r for r in tmp_store.select("insight")}
    assert set(rows) == {ok, low, unt} and len(gw.calls) == 3
    assert rows[ok]["severity"] == 4 and rows[low]["severity"] == 2 and rows[unt]["severity"] == 2
    assert rows[ok]["account_id"] == "A01" and rows[unt]["account_id"] is None and rows[unt]["account_status"] == "unresolved"
    assert all(r["quote_match"] == "exact" and r["call_id"] for r in rows.values())
    assert tmp_store.select("model_call", {"call_id": rows[ok]["call_id"]})[0]["target_id"] == ok
    body = next(b for _, _, b in gw.calls if "tell me what is slow" in last_user(b))
    assert "CONTEXT (internal, do not quote)" in last_user(body)
    s, e = rows[ok]["quote_span_start"], rows[ok]["quote_span_end"]
    assert "we upload documents one at a time and it is slow"[s:e] == rows[ok]["quote"]


def test_failed_quote_retries_once_then_recovers(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    sid = seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")

    def reply(body):
        return answer("documents are uploaded singly and slowly" if "copy it verbatim" not in last_user(body)
                      else "upload documents one at a time")
    gw = fake_gateway({"extract": reply})
    extract.run(ctx_for(tmp_store, gw))
    (row,) = tmp_store.select("insight")
    assert len(gw.calls) == 2 and row["quote_match"] == "exact" and row["snippet_id"] == sid


def test_quote_failing_twice_is_stored_failed_and_counted(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow", context="Internal: please tell us what hurts most")
    seed_snippet(tmp_store, "k2", "the list view is really hard to read for us", source="fullstory")
    gw = fake_gateway({"extract": lambda b: answer("please tell us what hurts most" if "upload documents" in last_user(b)
                                                    else "list view is really HARD to read for us")})  # fullstory: exact only
    extract.run(ctx_for(tmp_store, gw))
    rows = tmp_store.select("insight")
    assert len(gw.calls) == 4 and sorted(r["quote_match"] for r in rows) == ["failed", "failed"]
    assert all(r["quote_span_start"] is None for r in rows)  # insights = verified (0) + failed (2)


def test_rerun_skips_snippets_that_already_have_insights(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")
    gw = fake_gateway({"extract": answer("documents one at a time and it is slow")})
    extract.run(ctx_for(tmp_store, gw))
    extract.run(ctx_for(tmp_store, gw))
    assert len(gw.calls) == 1 and len(tmp_store.select("insight")) == 1


def test_replay_skips_untriaged_snippets_instead_of_raising_a_replay_miss(tmp_store, fake_gateway):
    seed_snippet(tmp_store, "k1", "we cannot find the export button anywhere", decision="untriaged")
    gw = fake_gateway({}, profile="replay")
    extract.run(ctx_for(tmp_store, gw))
    assert tmp_store.select("insight") == []


def with_flag(quote, flag):
    return {**answer(quote), "states_product_problem": flag}


def test_no_answer_stores_no_insight_and_is_audited_and_counted(tmp_store, fake_gateway, capsys):
    seed_account(tmp_store, "A01", 1000)
    yes = seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")
    no = seed_snippet(tmp_store, "k2", "thanks so much for the call today, speak next week")
    gw = fake_gateway({"extract": lambda b: with_flag("documents one at a time and it is slow", "yes") if "upload documents" in last_user(b)
                       else with_flag("thanks so much for the call today", "no")})
    extract.run(ctx_for(tmp_store, gw))
    assert [r["snippet_id"] for r in tmp_store.select("insight")] == [yes]
    (ev,) = tmp_store.select("audit_event", {"action": "extract.dropped"})
    assert ev["target_type"] == "snippet" and ev["target_id"] == no and "product problem" in ev["details_json"]["reason"]
    assert len(gw.calls) == 2  # a 'no' is not retried for its quote
    assert "extract: 2 kept for extract = 1 insights + 1 dropped_at_extract + 0 failed" in capsys.readouterr().out
    assert extract.run(ctx_for(tmp_store, gw)) is None and len(gw.calls) == 2  # rerun does not re-ask dropped snippets
    assert len(tmp_store.select("audit_event", {"action": "extract.dropped"})) == 1


def test_yes_answer_behaves_as_before(tmp_store, fake_gateway):
    seed_account(tmp_store, "A01", 1000)
    sid = seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")
    gw = fake_gateway({"extract": with_flag("documents one at a time and it is slow", "yes")})
    extract.run(ctx_for(tmp_store, gw))
    (row,) = tmp_store.select("insight")
    assert row["snippet_id"] == sid and row["quote_match"] == "exact"
    assert tmp_store.select("audit_event", {"action": "extract.dropped"}) == []


def test_request_schema_and_prompt_carry_the_typed_field(tmp_store, fake_gateway):
    from signal_engine import prompts
    seed_account(tmp_store, "A01", 1000)
    seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")
    gw = fake_gateway({"extract": with_flag("documents one at a time and it is slow", "yes")})
    extract.run(ctx_for(tmp_store, gw))
    body = gw.calls[0][2]
    sch = body["response_format"]["json_schema"]["schema"]
    assert sch["properties"]["states_product_problem"]["enum"] == ["yes", "no"] and "states_product_problem" in sch["required"]
    system, version = prompts.load_prompt("extract", "extract")
    assert "states_product_problem" in system and version.startswith("extract@2+")


def test_replay_miss_is_counted_per_snippet_and_never_crashes(tmp_store, fake_gateway, capsys):
    seed_account(tmp_store, "A01", 1000)
    seed_snippet(tmp_store, "k1", "we upload documents one at a time and it is slow")
    gw = fake_gateway({}, profile="replay")
    extract.run(ctx_for(tmp_store, gw))
    assert tmp_store.select("insight") == []
    assert "extract: 1 kept for extract = 0 insights + 0 dropped_at_extract + 1 failed (1 not in the replay cache)" in capsys.readouterr().out


def test_reconciliation_counts_short_snippets_as_failed(tmp_store, fake_gateway, capsys):
    seed_account(tmp_store, "A01", 1000)
    seed_snippet(tmp_store, "k1", "export is slow")
    gw = fake_gateway({"extract": with_flag("export is slow", "yes")})
    extract.run(ctx_for(tmp_store, gw))
    assert "= 0 insights + 0 dropped_at_extract + 1 failed" in capsys.readouterr().out
