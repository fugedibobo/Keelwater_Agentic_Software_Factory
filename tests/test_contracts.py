import json
import sqlite3
from pathlib import Path

import jsonschema
import pytest
from pydantic import BaseModel, ValidationError

from signal_engine import config, contracts as c
from signal_engine.store import Store

ROOT = Path(__file__).resolve().parent.parent
Q = "one two three four five"


def test_every_model_is_listed_and_forbids_extras():
    declared = {m for m in vars(c).values() if isinstance(m, type) and issubclass(m, BaseModel) and m.__module__ == c.__name__}
    assert declared - {c.Row, c._Checked} == set(c.ALL_MODELS)
    assert all(m.model_config["extra"] == "forbid" for m in c.ALL_MODELS)


GOOD = [
    (c.Account, dict(account_id="a", name="n")),
    (c.Snippet, dict(snippet_id="s", raw_id="r", text="t")),
    (c.ExtractOutput, dict(problem="p", quote=Q, workflow="w", desired_outcome="o")),
    (c.TriageOutput, dict(is_product_signal=0.5, bucket="fnol_intake", bucket_confidence=0.9, severity=2, signal_type="bug")),
    (c.RejectBody, dict(reason_code="low_value")),
    (c.AcceptBody, dict(confirmed=True)),
    (c.UndoBody, dict(audit_event_id="e")),
]


@pytest.mark.parametrize("model,data", GOOD, ids=lambda x: getattr(x, "__name__", ""))
def test_extra_field_rejected(model, data):
    model(**data)
    with pytest.raises(ValidationError):
        model(**data, surprise=1)


def test_constraints():
    ok = dict(is_product_signal=0.5, bucket="fnol_intake", bucket_confidence=0.9, severity=2, signal_type="bug")
    for bad in (dict(bucket="nope"), dict(severity=5), dict(severity=0), dict(is_product_signal=1.2), dict(bucket_confidence=-0.1)):
        with pytest.raises(ValidationError):
            c.TriageOutput(**{**ok, **bad})
    base = dict(problem="p", workflow="w", desired_outcome="o")
    with pytest.raises(ValidationError):
        c.ExtractOutput(quote="one two three four", **base)
    with pytest.raises(ValidationError):
        c.ExtractOutput(quote=" ".join(["w"] * 61), **base)
    c.ExtractOutput(quote=" ".join(["w"] * 60), **base)
    with pytest.raises(ValidationError):
        c.JudgeOutput(verdict="pass", critique="x", extra=1)
    with pytest.raises(ValidationError):
        c.JudgeVersion(judge_version_id="x", judge="coherence", prompt_version="p", model="m")
    with pytest.raises(ValidationError):
        c.RejectBody(reason_code="other")  # note required


def test_enums_match_architecture_section_7():
    assert [s.value for s in c.Status] == "new proposed accepted merged rejected parked intent_drafted in_factory shipped enabled measured".split()
    assert [s.value for s in c.Judge] == ["faithfulness", "signal", "duplicate"]
    assert [s.value for s in c.Profile] == ["replay", "demo", "aws", "self-hosted"]
    assert {s.value for s in c.AnnotationAction} >= {"confirm_tag", "remove_tag", "undo", "split"}


def test_taxonomy_has_ten_buckets_and_five_squads():
    t = config.load("taxonomy")
    assert len(t["buckets"]) == 10 and len(t["squads"]) == 5
    assert {b["squad"] for b in t["buckets"]} == set(t["squads"])


def test_schema_columns_match_contract_fields(tmp_path):
    store = Store.fresh(tmp_path / "s.sqlite")
    for table, model in c.TABLES.items():
        cols = [r[1] for r in store.db.execute(f"PRAGMA table_info({table})")]
        assert sorted(cols) == sorted(model.model_fields), table
    assert {r[0] for r in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == set(c.TABLES)
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("INSERT INTO opportunity VALUES ('o','t','p','b','bogus','s','2026-11-03',NULL,NULL,'none',NULL,NULL)")


# ---- source export schemas ----------------------------------------------------------------------------------
SOURCES = {
    "gong_calls": ("gong/calls.json", lambda d: d["calls"][0]["metaData"].update(duration="ten")),
    "gong_transcripts": ("gong/transcripts.json", lambda d: d["callTranscripts"][0]["transcript"][0]["sentences"][0].update(start=1.5)),
    "intercom_conversation": ("intercom/c1.json", lambda d: d["conversation_parts"]["conversation_parts"][0]["author"].update(type="robot")),
    "fireflies_transcript": ("fireflies/f1.json", lambda d: d["sentences"][0].update(start_time="1.5")),
    "fullstory_event": ("fullstory/events.ndjson", lambda d: d.pop("event_type")),
    "fullstory_session": ("fullstory/sessions.json", lambda d: d.pop("userId")),
    "hubspot_companies": ("hubspot/companies.json", lambda d: d["results"][0]["properties"].update(keelwater_arr_gbp=1250000)),
    "shortcut_stories": ("shortcut/stories.json", lambda d: d["stories"][0].update(story_type="epic")),
    "notion_pages": ("notion/pages.json", lambda d: d["results"][0]["properties"].pop("Name")),
}


def _example(rel):
    text = (ROOT / "tests/fixtures/raw" / rel).read_text(encoding="utf-8")
    return json.loads(text.splitlines()[0]) if rel.endswith(".ndjson") else json.loads(text)


@pytest.mark.parametrize("name", SOURCES)
def test_source_schema_accepts_valid_and_rejects_invalid(name):
    rel, break_it = SOURCES[name]
    schema = json.loads((ROOT / "contracts/sources" / f"{name}.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    good = _example(rel)
    if name == "fullstory_session":
        good = good[0]
    jsonschema.validate(good, schema)
    bad = json.loads(json.dumps(good))
    break_it(bad)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_every_native_export_has_a_schema_and_the_factory_job_schema_loads():
    assert len(list((ROOT / "contracts/sources").glob("*.schema.json"))) == len(SOURCES)
    jsonschema.Draft202012Validator.check_schema(json.loads(config.FACTORY_JOB_SCHEMA.read_text(encoding="utf-8")))
