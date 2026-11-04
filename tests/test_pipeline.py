import json
import sys
from pathlib import Path

import pytest

from signal_engine import cli, contracts as c, pipeline, prompts
from signal_engine.gateway import ReplayMiss, BudgetExceeded
from signal_engine.store import Store, insight_id, raw_id, snippet_id

ROOT = Path(__file__).resolve().parent.parent

STAGE_MODULE = '''
from signal_engine import contracts as c
from signal_engine.store import raw_id, snippet_id, insight_id

def idle(ctx):
    pass

def run(ctx):
    s = ctx.store
    rid = raw_id("gong", "g1")
    s.insert("account", c.Account(account_id=ctx.batch, name="A"))
    s.insert("raw_record", c.RawRecord(raw_id=rid, source="gong", route="sales", source_id="g1", payload_json={"x": 1}), replace=True)
    sid = snippet_id(rid, 0, "hello")
    s.insert("snippet", c.Snippet(snippet_id=sid, raw_id=rid, text="hello"), replace=True)
    iid = insight_id(sid, "q")
    s.insert("insight", c.Insight(insight_id=iid, snippet_id=sid, run_id=ctx.run_id, problem="p", quote="a b c d e f",
                                  quote_match="exact", severity=2), replace=True)
'''


def args(tmp_path, *extra):
    return cli.run_parser().parse_args(["--data", str(ROOT / "tests/fixtures/raw"), "--db", str(tmp_path / "k.sqlite"),
                                        "--report-dir", str(tmp_path / "rep"), *extra])


def report(tmp_path, name="latest-replay.json"):
    return json.loads((tmp_path / "rep" / "runs" / name).read_text(encoding="utf-8"))


@pytest.fixture
def fake_stage(tmp_path, monkeypatch):
    (tmp_path / "fake_stage_mod.py").write_text(STAGE_MODULE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(pipeline.STAGES, "connect", "fake_stage_mod:run")
    monkeypatch.setitem(pipeline.STAGES, "triage", "fake_stage_mod:idle")  # the real triage needs the model cache
    for name in ("cluster", "tag"):  # built stages would need cached model replies for the stub insight
        monkeypatch.setitem(pipeline.STAGES, name, "absent_stage_mod:run")
    monkeypatch.setitem(pipeline.STAGES, "segment", "no_such_module:run")  # the real segment would read the fake raw rows
    yield
    sys.modules.pop("fake_stage_mod", None)


def test_two_runs_give_identical_ids_and_output_hash_with_different_run_ids(tmp_path, fake_stage):
    assert pipeline.run_pipeline(args(tmp_path)) == 0
    first = report(tmp_path)
    store = Store(tmp_path / "k.sqlite")
    ids = [store.select(t)[0][k] for t, k in (("raw_record", "raw_id"), ("snippet", "snippet_id"), ("insight", "insight_id"))]
    store.close()
    assert pipeline.run_pipeline(args(tmp_path)) == 0
    second = report(tmp_path)
    assert first["run_id"] != second["run_id"] and first["output_hash"] == second["output_hash"]
    store = Store(tmp_path / "k.sqlite")
    assert ids == [store.select(t)[0][k] for t, k in (("raw_record", "raw_id"), ("snippet", "snippet_id"), ("insight", "insight_id"))]
    rid = raw_id("gong", "g1")
    assert ids == [rid, snippet_id(rid, 0, "hello"), insight_id(snippet_id(rid, 0, "hello"), "q")]
    assert first["stages"]["connect"] == "done" and first["stages"]["segment"] == "skipped (not built)"


def test_run_recreates_the_store_but_oct_appends(tmp_path, fake_stage):
    pipeline.run_pipeline(args(tmp_path, "--batch", "sep"))
    s = Store(tmp_path / "k.sqlite")
    s.db.execute("INSERT INTO account VALUES ('junk','j',1,'t',NULL)")
    s.db.commit()
    s.close()
    assert pipeline.run_pipeline(args(tmp_path, "--batch", "oct")) == 0
    s = Store(tmp_path / "k.sqlite")
    assert sorted(a["account_id"] for a in s.select("account")) == ["junk", "oct", "sep"] and len(s.select("run")) == 2
    s.close()
    pipeline.run_pipeline(args(tmp_path, "--batch", "sep"))
    s = Store(tmp_path / "k.sqlite")
    assert [a["account_id"] for a in s.select("account")] == ["sep"]
    assert (tmp_path / "rep" / "runs" / "latest-replay-oct.json").is_file()


def test_stage_subset_and_unknown_stage(tmp_path, capsys):
    assert pipeline.run_pipeline(args(tmp_path, "--stages", "review,handoff")) == 0
    out = capsys.readouterr().out
    assert "review: done" in out and "handoff: done" in out and "connect" not in out
    assert pipeline.run_pipeline(args(tmp_path, "--stages", "bogus")) == 2


def test_match_and_diff_against_the_recorded_demo_run(tmp_path, capsys):
    pipeline.run_pipeline(args(tmp_path))
    out_hash = report(tmp_path)["output_hash"]
    demo = tmp_path / "rep" / "runs" / "latest-demo.json"
    demo.write_text(json.dumps({"output_hash": out_hash}), encoding="utf-8")
    pipeline.run_pipeline(args(tmp_path))
    assert "MATCH" in capsys.readouterr().out
    demo.write_text(json.dumps({"output_hash": "0" * 64}), encoding="utf-8")
    pipeline.run_pipeline(args(tmp_path))
    assert "DIFF" in capsys.readouterr().out


def test_changed_config_file_is_an_audit_event_with_old_and_new_hash(tmp_path):
    pipeline.run_pipeline(args(tmp_path))
    path = tmp_path / "rep" / "runs" / "latest-replay.json"
    rep = json.loads(path.read_text(encoding="utf-8"))
    old = rep["manifest"]["config_files"]["ranking"]
    rep["manifest"]["config_files"]["ranking"] = "0" * 64
    path.write_text(json.dumps(rep), encoding="utf-8")
    pipeline.run_pipeline(args(tmp_path))
    s = Store(tmp_path / "k.sqlite")
    (ev,) = [e for e in s.select("audit_event") if e["action"] == "config.changed"]
    assert ev["action"] == "config.changed" and ev["target_id"] == "ranking"
    assert ev["details_json"] == {"old": "0" * 64, "new": old} and s.verify_audit_chain()


def test_hooks_run_in_order_and_unbuilt_ones_are_silent(tmp_path, monkeypatch):
    (tmp_path / "hook_mod.py").write_text("calls = []\ndef hook(ctx):\n    calls.append(ctx.stage)\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    for h in ("run_start", "after_cluster", "after_tag"):
        monkeypatch.setitem(pipeline.HOOKS, h, ["hook_mod:hook", "no_such_module:hook"])
    pipeline.run_pipeline(args(tmp_path))
    import hook_mod
    assert hook_mod.calls == ["run_start", "after_cluster", "after_tag"]


def test_every_stage_and_hook_is_a_lazy_module_function_string():
    assert list(pipeline.STAGES) == "connect segment triage extract cluster tag rank brief judge review handoff outtake".split()
    for spec in list(pipeline.STAGES.values()) + [s for v in pipeline.HOOKS.values() for s in v]:
        mod, func = spec.split(":")
        assert mod.startswith("signal_engine.") and func.isidentifier()
    assert pipeline.STAGES["review"] == "signal_engine.evals.labels:apply"
    assert pipeline.HOOKS["run_start"] == ["signal_engine.evals.labels:import_human"]


def test_gateway_errors_fail_the_run_cleanly(tmp_path, monkeypatch, capsys):
    (tmp_path / "bad_stage.py").write_text(
        "def run(ctx):\n    ctx.gateway.chat('cluster_label', [{'role': 'user', 'content': 'x'}], target_type='o', target_id='1')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(pipeline.STAGES, "connect", "bad_stage:run")
    a = args(tmp_path, "--cache-dir", str(tmp_path / "empty"))
    assert pipeline.run_pipeline(a) == 1
    out = capsys.readouterr().out
    assert "replay cache miss: stage=cluster_label request_hash=" in out


def test_data_hash_is_line_ending_independent_and_content_sensitive(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d, nl in ((a, b"\n"), (b, b"\r\n")):
        (d / "x").mkdir(parents=True)
        (d / "x" / "f.json").write_bytes(b"{" + nl + b"}" + nl)
    assert pipeline.data_hash(a) == pipeline.data_hash(b) != pipeline.data_hash(tmp_path / "missing")
    (a / "x" / "f.json").write_bytes(b"{}")
    assert pipeline.data_hash(a) != pipeline.data_hash(b)


def test_report_path_names():
    p = pipeline.report_path
    assert p("r", "replay", 42, "all").as_posix() == "r/runs/latest-replay.json"
    assert p("r", "demo", 43, "sep").as_posix() == "r/runs/latest-demo-seed43-sep.json"


def test_prompt_versions(tmp_path):
    d = tmp_path / "extract"
    d.mkdir()
    (d / "main.md").write_text("---\nversion: 1.2.0\n---\nBody\n", encoding="utf-8")
    (d / "bare.md").write_text("no front matter", encoding="utf-8")
    body, version = prompts.load_prompt("extract", "main", tmp_path)
    assert body == "Body\n" and version.startswith("main@1.2.0+") and len(version.split("+")[1]) == 8
    (d / "main.md").write_text("---\nversion: 1.2.0\n---\nBody changed\n", encoding="utf-8")
    assert prompts.load_prompt("extract", "main", tmp_path)[1] != version
    with pytest.raises(ValueError):
        prompts.load_prompt("extract", "bare", tmp_path)
    (d / "bare.md").unlink()
    assert list(prompts.all_versions(tmp_path)) == ["extract/main"] and prompts.all_versions(tmp_path / "none") == {}
