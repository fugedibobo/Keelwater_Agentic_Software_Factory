"""Stage 1: speaker mapping, context turns, per-source segmentation and the reconciliation table."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from signal_engine import cli
from signal_engine.ingest import connect, segment

FIX = Path(__file__).resolve().parent / "fixtures" / "ingest"


@pytest.fixture
def seg(tmp_store, capsys):
    ctx = SimpleNamespace(store=tmp_store, data_dir=FIX)
    connect.run(ctx)
    segment.run(ctx)
    capsys.readouterr()
    return tmp_store


def snippets(store, source, sid):
    rid = next(r["raw_id"] for r in store.select("raw_record", {"source": source}) if r["source_id"] == sid)
    return store.select("snippet", {"raw_id": rid}, order_by="start_ms")


def test_gong_consecutive_sentences_one_snippet_with_context(seg):
    s = snippets(seg, "gong", "g1")
    assert [x["text"] for x in s] == ["Yes, exactly that. It loses the file type every time.", "Thanks.", "Sorry, a stray voice."]
    assert (s[0]["start_ms"], s[0]["end_ms"], s[0]["speaker_email"]) == (4000, 15000, "ben@client.example")
    assert s[0]["context_text"] == "So the document upload is still giving you trouble?"
    assert s[1]["context_text"] == "Noted."


def test_context_text_never_in_text(seg):
    for sn in seg.select("snippet"):
        if sn["context_text"]:
            assert sn["context_text"] not in sn["text"]


def test_unmapped_speaker_quarantined(seg):
    texts = [x["text"] for x in seg.select("snippet")]
    assert "Who is this?" not in texts and "I joined late." not in texts
    ev = [e["details_json"] for e in seg.select("audit_event") if e["action"] == "ingest.quarantine_speaker"]
    assert {(d["source_id"], d["speaker"]) for d in ev} == {("g1", "s9"), ("f1", "Dana Nobody")}
    assert snippets(seg, "gong", "g1")[2]["context_text"] == ""  # a quarantined turn is no context


def test_fireflies_ms_and_staff_mapping(seg):
    (s,) = snippets(seg, "fireflies", "f1")
    assert (s["text"], s["start_ms"], s["end_ms"]) == ("Slow. The import tool is confusing.", 2500, 9000)
    assert s["context_text"] == "How is onboarding going?" and s["speaker_email"] == "ben@client.example"


def test_intercom_parts_html_fin_and_notes(seg):
    s = snippets(seg, "intercom", "c1")
    assert [x["text"] for x in s] == ["Hello, my claims page is empty.", "Any claim, they all vanish. Thanks"]
    assert s[1]["start_ms"] == 150_000 and s[1]["context_text"] == "Can you tell me which claim?"
    assert s[0]["context_text"] == ""
    ev = next(e["details_json"] for e in seg.select("audit_event") if e["action"] == "segment.removed" and e["details_json"]["source"] == "intercom")
    assert (ev["fin"], ev["note"], ev["internal"]) == (1, 1, 1)


def test_intercom_lead_source_is_customer(seg):
    assert [x["text"] for x in snippets(seg, "intercom", "c2")] == ["Export is broken."]


def test_reconciliation_counts(seg):
    rows, (before, after) = segment.reconciliation(seg)
    assert rows["gong"] == dict(raw=2, quarantined=1, speaker_turns=1, snippets=4, internal=2, fin=0, notes=0)
    assert rows["intercom"]["fin"] == 1 and rows["intercom"]["notes"] == 1 and rows["intercom"]["snippets"] == 3
    assert rows["fireflies"]["speaker_turns"] == 1 and rows["fullstory"]["quarantined"] == 1
    assert before > 6000 and after == 180


def test_cli_prints_table_exit_0_and_writes_only_scratch(tmp_path, capsys):
    db, rep = tmp_path / "ingest.sqlite", tmp_path / "rep"
    rc = cli.main(["run", "--data", str(FIX), "--stages", "connect,segment", "--db", str(db), "--report-dir", str(rep)])
    out = capsys.readouterr().out
    assert rc == 0 and "q.speaker turns" in out and "FullStory session minutes: 116.5 before idle-strip, 3.0 after" in out
    assert {p.name for p in tmp_path.iterdir()} <= {"ingest.sqlite", "rep", "absent.env"}
