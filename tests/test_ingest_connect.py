"""Stage 0: schema quarantine, routes, account resolution (evals 3.3) and the HubSpot account table."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from signal_engine.ingest import accounts as acc
from signal_engine.ingest import connect

FIX = Path(__file__).resolve().parent / "fixtures" / "ingest"


@pytest.fixture
def conn(tmp_store):
    connect.run(SimpleNamespace(store=tmp_store, data_dir=FIX))
    return tmp_store


def raw(store, source, sid):
    return next(r for r in store.select("raw_record", {"source": source}) if r["source_id"] == sid)


@pytest.mark.parametrize("given,want", [("2400000", 2400000.0), ("1,250,000", 1250000.0), ("£610k", 610000.0),
                                        ("540000.00", 540000.0), (None, None), ("tbc", None)])
def test_parse_arr(given, want):
    assert acc.parse_arr(given) == want


def test_account_table(conn):
    a = {r["account_id"]: r for r in conn.select("account")}
    assert set(a) == {"100", "102", "103", "104", "105"}  # duplicate 101 not an account
    assert a["100"]["arr_gbp"] == 1250000.0 and a["100"]["name"] == "Fixture Insurance"  # not annualrevenue 99999999
    assert a["102"]["tier"] == "Enterprise" and a["102"]["arr_gbp"] == 610000.0  # case-normalised, pound-k form
    assert a["103"]["renewal_date"] is None  # missing stays missing
    assert a["105"]["arr_gbp"] is None and a["105"]["tier"] is None


def test_renewal_within_90_days_at_as_of():
    as_of = date(2026, 11, 3)
    assert acc.renewal_within_days(date(2026, 12, 12), as_of)
    assert acc.renewal_within_days(date(2027, 2, 1), as_of)  # day 90
    assert not acc.renewal_within_days(date(2027, 2, 2), as_of)
    assert not acc.renewal_within_days(date(2026, 11, 2), as_of)
    assert not acc.renewal_within_days(None, as_of)


def test_gong_hubspot_object_resolves_duplicate_to_canonical(conn):
    r = raw(conn, "gong", "g1")  # context object is the stale duplicate 101
    assert (r["account_id"], r["account_status"]) == ("100", "resolved")


def test_gong_external_email_fallback_ignores_broker(conn):
    r = raw(conn, "gong", "g2")  # no CRM object; broker and customer attend
    assert (r["account_id"], r["account_status"]) == ("103", "resolved")


def test_intercom_personal_email_unresolved(conn):
    r = raw(conn, "intercom", "c1")
    assert (r["account_id"], r["account_status"]) == (None, "unresolved")


def test_www_stripped_in_hubspot_domain(conn):
    r = raw(conn, "intercom", "c2")  # amy@second.example vs HubSpot domain www.second.example
    assert (r["account_id"], r["account_status"]) == ("102", "resolved")


def test_fireflies_two_customer_domains_ambiguous(conn):
    r = raw(conn, "fireflies", "f1")
    assert (r["account_id"], r["account_status"]) == (None, "ambiguous")


def test_fullstory_account_from_user_id(conn):
    assert raw(conn, "fullstory", "7741203")["account_id"] == "100"


def test_routes(conn):
    assert raw(conn, "gong", "g1")["route"] == "sales"
    assert raw(conn, "intercom", "c1")["route"] == "support"
    assert raw(conn, "fireflies", "f1")["route"] == "onboarding"  # host ada
    assert raw(conn, "fireflies", "f2")["route"] == "account_management"  # host grace
    assert raw(conn, "fullstory", "7741203")["route"] == "sessions"
    for s, sid in (("hubspot", "100"), ("shortcut", "1"), ("notion", "n1")):
        assert raw(conn, s, sid)["route"] is None


def test_schema_failure_is_quarantined(conn):
    assert not [r for r in conn.select("raw_record", {"source": "gong"}) if r["source_id"] == "g3"]
    q = [e for e in conn.select("audit_event") if e["action"] == "ingest.quarantine"]
    gong = next(e for e in q if e["details_json"]["source"] == "gong")
    assert gong["details_json"]["source_id"] == "g3" and "duration" in gong["details_json"]["reason"]
    assert any(e["details_json"]["source"] == "fullstory" for e in q)  # the bad event line
    assert conn.verify_audit_chain()


def test_raw_id_is_content_hash_and_rerun_is_idempotent(conn):
    n = len(conn.select("raw_record"))
    connect.run(SimpleNamespace(store=conn, data_dir=FIX))
    assert len(conn.select("raw_record")) == n


def test_teams_fall_back_to_default_domain(tmp_path):
    t = acc.load_teams(tmp_path)  # no teams.yaml in the data root; config/teams.yaml may or may not exist
    assert acc.is_internal("x@keelwater.example", t) and not acc.is_internal("x@client.example", t)
