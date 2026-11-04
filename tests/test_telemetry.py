import json
import sys
from types import SimpleNamespace

import pytest

from signal_engine import gateway, telemetry
from signal_engine.store import Store



class FakeClient:
    def __init__(self):
        self.notes, self.datasets, self.experiments_run = [], {}, []
        self.spans = SimpleNamespace(add_span_annotation=lambda **kw: self.notes.append(kw))
        self.datasets = SimpleNamespace(create_dataset=self._create, add_examples_to_dataset=self._add, get_dataset=lambda dataset: dataset)
        self.experiments = SimpleNamespace(run_experiment=lambda **kw: self.experiments_run.append(kw))
        self.created, self.added = {}, {}

    def _create(self, name, inputs, outputs, metadata):
        if name in self.created:
            raise ValueError("exists")
        self.created[name] = inputs

    def _add(self, dataset, inputs, outputs, metadata):
        self.added[dataset] = inputs


ROW = dict(call_id="c1", run_id="r", stage="judge", target_type="brief", target_id="b1", model="m", profile="replay", endpoint="e",
           prompt_version="faithfulness@1.0.0+abcd1234", input_hash="i", output_hash="o", tokens_in=10, tokens_out=5, cost_usd=0.0,
           latency_ms=12.5, cached=True)
LABEL = dict(label_id="l1", judge="faithfulness", target_type="brief", target_id="b1", verdict="fail", critique="bad", origin="real_pm",
             blind=True, split="dev", weight=1.0, actor="pm", created_at="2026-11-03")


def test_phoenix_imports_are_optional(monkeypatch, capsys, tmp_path):
    for m in ("phoenix", "phoenix.client", "opentelemetry"):
        monkeypatch.setitem(sys.modules, m, None)
    ctx = SimpleNamespace(store=None, gateway=None, run_id="r", profile="replay", seed=42, batch="all")
    assert telemetry.install(ctx) is None
    assert telemetry.upload_datasets({"d": [{"input": {}, "output": {}, "metadata": {}}]}) == {}
    (tmp_path / "r.json").write_text("{}", encoding="utf-8")
    assert telemetry.log_experiment(tmp_path / "r.json") is None
    assert capsys.readouterr().out.count("Phoenix not installed") == 3


def test_spans_nest_carry_attributes_and_annotate(tmp_path):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    mem = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(mem))
    store = Store.fresh(tmp_path / "s.sqlite")
    store.insert("label", LABEL)
    client = FakeClient()
    ctx = SimpleNamespace(store=store, gateway=SimpleNamespace(stage_cfg=lambda s: {"backend": "clef"}), run_id="r", profile="replay", seed=42, batch="all")
    gateway.clear_listeners()
    tr = telemetry.install(ctx, provider=provider, client=client)
    for fn in gateway._LISTENERS:
        fn(ROW, {"verdict": "pass", "critique": "ok"})
        fn(dict(ROW, call_id="c2", stage="triage", target_type="snippet", target_id="s1", prompt_version=""),
           {"bucket": {"choice": "Reporting", "confidence": 0.8}})
    telemetry.uninstall()
    spans = {s.name: s for s in mem.get_finished_spans()}
    assert set(spans) == {"keelwater.run", "stage.judge", "stage.triage", "judge.call", "triage.call"}
    call = spans["judge.call"]
    assert call.parent.span_id == spans["stage.judge"].context.span_id
    assert spans["stage.judge"].parent.span_id == spans["keelwater.run"].context.span_id
    a = call.attributes
    assert (a["stage"], a["model"], a["prompt_version"], a["tokens_in"], a["cost_usd"], a["cached"], a["call_id"]) == \
        ("judge", "m", "faithfulness@1.0.0+abcd1234", 10, 0.0, True, "c1")
    assert (spans["triage.call"].attributes["backend"], spans["triage.call"].attributes["bucket"], spans["triage.call"].attributes["confidence"]) == ("clef", "Reporting", 0.8)
    assert {(n["annotation_name"], n["annotator_kind"], n["label"]) for n in client.notes} == \
        {("judge.faithfulness", "LLM", "pass"), ("human.faithfulness", "HUMAN", "fail")}
    assert not gateway._LISTENERS


def test_datasets_versioned_and_experiment_scores(tmp_path):
    store = Store.fresh(tmp_path / "s.sqlite")
    store.insert("label", LABEL)
    store.insert("label", dict(LABEL, label_id="l2", judge="signal", target_type="noise_audit", target_id="s9", verdict="pass"))
    seeds = tmp_path / "seed"
    seeds.mkdir()
    (seeds / "signal.jsonl").write_text(json.dumps({"evidence": "e", "verdict": "pass"}) + "\n", encoding="utf-8")
    sets = telemetry.build_label_datasets(store, seeds, {"themes": [{"id": "t1", "kind": "real"}]})
    assert set(sets) == {"keelwater-ground-truth", "keelwater-judge-seed-signal", "keelwater-labels-blind", "keelwater-noise-audit"}
    client = FakeClient()
    assert telemetry.upload_datasets(sets, client)["keelwater-labels-blind"] == 1
    telemetry.upload_datasets(sets, client)  # second upload: name taken, so a new version
    assert "keelwater-labels-blind" in client.added
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps({"suite": "judges", "run_id": "x", "seed": 42, "passed": True, "metrics": {"a": 0.5, "n": None}, "gates": {"a": False}}), encoding="utf-8")
    telemetry.log_experiment(rep, manifest={"prompt_versions": {"p": "1"}, "model_ids": {"m": "z"}}, client=client)
    run = client.experiments_run[0]
    assert run["experiment_metadata"]["prompt_versions"] == {"p": "1"} and run["experiment_name"] == "judges-x"
    assert [(e.__name__, e(None)) for e in run["evaluators"]] == [("a", {"score": 0.5, "label": "fail"})]
