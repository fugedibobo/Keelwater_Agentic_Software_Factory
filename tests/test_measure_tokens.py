"""Tests for scripts/measure_tokens.py: the doc table equals the script output, and the CSV totals add up."""
import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("measure_tokens", ROOT / "scripts" / "measure_tokens.py")
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)


def real():
    return mt.load(mt.TOKENS_CSV), mt.load(mt.PRICES_CSV), mt.load(mt.OPENROUTER_CSV)


def between(path):
    text = path.read_text(encoding="utf-8")
    a, b = text.index(mt.START) + len(mt.START), text.index(mt.END)
    return text[a:b].strip()


def test_doc_blocks_equal_script_output():
    t, p, o = real()
    assert between(mt.USAGE_DOC) == mt.usage_block(t, p, o, mt.TELEMETRY_CSV)
    assert between(mt.DELEG_DOC) == mt.render_table(t, p, o)[0]
    assert between(mt.README_DOC) == mt.summary_line(t, p, o)


def test_csv_totals_add_up():
    t, p, o = real()
    assert [r["model"] for r in t] == mt.ORDER and {r["source"] for r in t} <= {"measured", "estimated"}
    for r in t:
        assert int(r["total"]) == sum(int(r[k]) for k in ("input", "cache_write", "cache_read", "output")), r["model"]
        assert 0 <= int(r["cache_write_1h"]) <= int(r["cache_write"])
    c = mt.costs(t, p, o)
    assert sum(x["total"] for x in c) == sum(int(r["total"]) for r in t)
    assert abs(sum(x["usd"] for x in c) - sum(
        x["blended"] * x["total"] / 1e6 for x in c)) < 1e-6  # blended rate x tokens gives the cost back
    assert int(next(r for r in t if r["model"] == "OpenRouter pipeline")["total"]) == sum(
        int(x["tokens_in"]) + int(x["tokens_out"]) for x in o)


def test_measure_counts_each_message_once_and_reads_no_text(tmp_path):
    import json
    folder = tmp_path / "x-keelwater-agentic-software-factory"
    folder.mkdir()
    msg = {"id": "m1", "model": "claude-opus-5-5", "content": "SECRET TEXT",
           "usage": {"input_tokens": 1, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100, "output_tokens": 5,
                     "cache_creation": {"ephemeral_1h_input_tokens": 4}}}
    lines = [{"timestamp": "2026-11-04T00:00:00Z", "message": msg}] * 2 + [
        {"timestamp": "2026-11-01T00:00:00Z", "message": {**msg, "id": "old"}}]  # before the cutoff
    (folder / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert mt.claude_rows(tmp_path) == {"Opus": [1, 10, 100, 5, 4]}


def _codex(path, lines):
    import json
    path.write_text("\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines), encoding="utf-8")


def _count(monkeypatch):
    import json
    calls, real = [], json.loads
    monkeypatch.setattr(mt.json, "loads", lambda s, *a, **k: calls.append(s) or real(s, *a, **k))
    return calls


def test_codex_session_in_another_folder_is_skipped_unparsed(tmp_path, monkeypatch):
    meta = {"type": "session_meta", "payload": {"cwd": "/other/project", "timestamp": "2026-11-04T00:00:00Z"}}
    _codex(tmp_path / "rollout-a.jsonl", [meta, 'token_count {not json "token_count"', '"turn_context" {also not json'])
    calls = _count(monkeypatch)
    assert mt.codex_rows(tmp_path) == {}
    assert len(calls) == 1  # only the session_meta line was parsed


def test_claude_line_without_usage_is_never_parsed(tmp_path, monkeypatch):
    folder = tmp_path / "x-keelwater-agentic-software-factory"
    folder.mkdir()
    (folder / "s.jsonl").write_text('{"type": "user", "message": {"content": "no counts here"}}\n', encoding="utf-8")
    calls = _count(monkeypatch)
    assert mt.claude_rows(tmp_path) == {} and calls == []


def test_codex_increments_go_to_the_model_of_each_turn(tmp_path):
    def tc(i, c, o):
        return {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": i, "cached_input_tokens": c, "output_tokens": o}}}}
    _codex(tmp_path / "rollout-b.jsonl", [
        {"type": "session_meta", "payload": {"cwd": "/x/Keelwater_Agentic_Software_Factory", "timestamp": "2026-11-04T00:00:00Z"}},
        {"type": "turn_context", "payload": {"model": "gpt-6.1-terra"}}, tc(100, 40, 10),
        {"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}, tc(300, 100, 30)])
    assert mt.codex_rows(tmp_path) == {"Codex Terra": [60, 0, 40, 10, 0], "Codex Sol": [140, 0, 60, 20, 0]}
