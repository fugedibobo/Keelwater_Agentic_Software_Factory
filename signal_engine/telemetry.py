"""Phoenix tracing, labelled datasets and eval experiments (issue #10, ADR-010, docs/evals.md 8.2).

Local Phoenix only (127.0.0.1:6006 unless PHOENIX_URL says otherwise). Every Phoenix import is lazy, so without the
`phoenix` extra every entry point prints "Phoenix not installed" and the command carries on. `model_call` and
`audit_event` stay the audit record; spans only mirror them and never change an output.
"""

import atexit
import json
import os
import threading
import time
from pathlib import Path

from . import gateway

DEFAULT_URL = "http://127.0.0.1:6006"
PROJECT = "keelwater"
NOT_INSTALLED = "Phoenix not installed"
_ACTIVE = None


def base_url():
    return (os.environ.get("PHOENIX_URL") or DEFAULT_URL).rstrip("/")


def _client(client=None):
    """A Phoenix client, or None (message printed) when the extra is missing."""
    if client is not None:
        return client
    try:
        from phoenix.client import Client
    except ImportError:
        print(NOT_INSTALLED)
        return None
    return Client(base_url=base_url())


# ---- tracing -----------------------------------------------------------------------------------------------

def _make_provider():
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    provider = TracerProvider(resource=Resource.create({"openinference.project.name": PROJECT}))
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=base_url() + "/v1/traces")))
    return provider


def _reachable():
    import httpx
    try:
        return httpx.get(base_url() + "/healthz", timeout=3).status_code < 500
    except httpx.HTTPError:
        return False


class RunTracer:
    """One root span per run, one span per stage, one span per gateway call; judge and human annotations go out at finish."""

    def __init__(self, provider, run_attrs, backend_of=lambda stage: None, labels=(), client=None):
        from opentelemetry import trace
        self._trace, self.provider, self.tracer = trace, provider, provider.get_tracer("keelwater")
        self.backend_of, self.labels, self.client = backend_of, list(labels), client
        self.lock = threading.Lock()
        self.root = self.tracer.start_span("keelwater.run", attributes={"openinference.span.kind": "CHAIN", **run_attrs})
        self.stage_name, self.stage_span, self.done = None, None, False
        self.by_call, self.by_target, self.judged = {}, {}, []

    def _stage(self, name):
        if name != self.stage_name:
            if self.stage_span:
                self.stage_span.end()
            ctx = self._trace.set_span_in_context(self.root)
            self.stage_span = self.tracer.start_span(f"stage.{name}", context=ctx, attributes={"openinference.span.kind": "CHAIN", "stage": name})
            self.stage_name = name
        return self.stage_span

    def on_call(self, row, parsed):
        """gateway listener: fn(model_call_row, parsed_output)."""
        end = time.time_ns()
        attrs = {"openinference.span.kind": "LLM", "stage": row["stage"], "model": row["model"], "llm.model_name": row["model"],
                 "prompt_version": row["prompt_version"] or "", "tokens_in": row["tokens_in"], "tokens_out": row["tokens_out"],
                 "llm.token_count.prompt": row["tokens_in"], "llm.token_count.completion": row["tokens_out"],
                 "cost_usd": row["cost_usd"], "latency_ms": row["latency_ms"], "cached": row["cached"], "call_id": row["call_id"],
                 "target_type": row["target_type"], "target_id": row["target_id"]}
        if isinstance(parsed, dict) and isinstance(parsed.get("bucket"), dict):  # Decisions API answers
            attrs.update(backend=self.backend_of(row["stage"]) or "", bucket=str(parsed["bucket"].get("choice")),
                         confidence=float(parsed["bucket"].get("confidence") or 0))
        with self.lock:
            ctx = self._trace.set_span_in_context(self._stage(row["stage"]))
            span = self.tracer.start_span(f"{row['stage']}.call", context=ctx, start_time=end - int(row["latency_ms"] * 1e6), attributes=attrs)
            span.end(end_time=end)
            sid = format(span.get_span_context().span_id, "016x")
            self.by_call[row["call_id"]] = sid
            self.by_target.setdefault((row["target_type"], row["target_id"]), []).append(sid)
            if row["stage"] == "judge" and isinstance(parsed, dict) and "verdict" in parsed:
                self.judged.append((sid, (row["prompt_version"] or "judge").split("@")[0], parsed["verdict"], parsed.get("critique")))

    def finish(self):
        """End the spans, flush them, then send judge verdicts (LLM) and human labels (HUMAN) as span annotations."""
        with self.lock:
            if self.done:
                return
            self.done = True
            if self.stage_span:
                self.stage_span.end()
            self.root.end()
        self.provider.force_flush()
        client = self.client
        notes = [(sid, f"judge.{judge}", "LLM", verdict, critique) for sid, judge, verdict, critique in self.judged]
        for lab in self.labels:
            for sid in self.by_target.get((lab["target_type"], lab["target_id"]), [])[:1]:
                notes.append((sid, f"human.{lab['judge']}", "HUMAN", lab["verdict"], lab.get("critique")))
        for sid, name, kind, label, why in notes:
            try:
                client.spans.add_span_annotation(span_id=sid, annotation_name=name, annotator_kind=kind, label=label,
                                                 score=1.0 if label == "pass" else 0.0, explanation=why, sync=True)
            except Exception as e:  # tracing must never fail a run
                print(f"Phoenix annotation failed: {type(e).__name__}")
                return


def install(ctx, provider=None, client=None):
    """Pipeline hook (HOOKS['tracing']): register the gateway listener. A second install ends the first run's trace."""
    global _ACTIVE
    client = _client(client)  # imported now: importing at interpreter exit fails
    if client is None:
        return None
    if provider is None:  # an injected provider (tests) skips the live checks
        try:
            provider = _make_provider()
        except ImportError:
            print(NOT_INSTALLED)
            return None
        if not _reachable():
            print(f"Phoenix not reachable at {base_url()}; tracing off")
            return None
    uninstall()
    labels = ctx.store.select("label") if ctx.store is not None else []
    tr = RunTracer(provider, {"run_id": ctx.run_id, "profile": ctx.profile, "seed": ctx.seed, "batch": ctx.batch},
                   lambda s: ctx.gateway.stage_cfg(s).get("backend"), labels, client)
    gateway.add_listener(tr.on_call)
    _ACTIVE = tr
    atexit.register(uninstall)
    print(f"phoenix: tracing run {ctx.run_id} to {base_url()}")
    return tr


def uninstall():
    """Detach the listener and finish the active tracer."""
    global _ACTIVE
    tr, _ACTIVE = _ACTIVE, None
    if tr:
        if tr.on_call in gateway._LISTENERS:
            gateway._LISTENERS.remove(tr.on_call)
        tr.finish()


# ---- datasets ----------------------------------------------------------------------------------------------

def _examples(rows, input_keys, output_keys):
    """[{input, output, metadata}] from dict rows: named keys go to input or output, the rest to metadata."""
    out = []
    for r in rows:
        out.append({"input": {k: r[k] for k in input_keys if k in r}, "output": {k: r[k] for k in output_keys if k in r},
                    "metadata": {k: v for k, v in r.items() if k not in input_keys and k not in output_keys}})
    return out


def build_label_datasets(store=None, seed_dir="labels/seed", truth=None):
    """{dataset name: examples}: planted ground truth, judge seeds, blind labels, noise-audit verdicts (evals.md 5.4, 8.2).

    # shortcut: ground truth is one example per planted theme, as the file stores it; upgrade to per-snippet labels if experiments need them
    """
    sets = {}
    if truth:  # the loaded ground-truth dict: only signal_engine/evals reads the file (tests/test_leaks.py), so the caller passes it in
        sets["keelwater-ground-truth"] = _examples([t for t in truth.get("themes", []) if isinstance(t, dict)], ("id", "title", "kind"), ("kind",))
    for f in sorted(Path(seed_dir).glob("*.jsonl")) if Path(seed_dir).is_dir() else []:
        rows = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        sets[f"keelwater-judge-seed-{f.stem}"] = _examples(rows, ("evidence", "input"), ("verdict",))
    labels = store.select("label") if store is not None else []
    blind = [l for l in labels if l["blind"] and l["target_type"] != "noise_audit"]
    audit = [l for l in labels if l["target_type"] == "noise_audit"]
    if blind:
        sets["keelwater-labels-blind"] = _examples(blind, ("judge", "target_type", "target_id"), ("verdict", "critique"))
    if audit:
        sets["keelwater-noise-audit"] = _examples(audit, ("target_id",), ("verdict", "critique"))
    return sets


def upload_datasets(datasets, client=None):
    """Create each dataset in Phoenix, or add a new version when the name exists. Returns {name: example count}."""
    client = _client(client)
    if client is None:
        return {}
    done = {}
    for name, ex in datasets.items():
        if not ex:
            continue
        kw = dict(inputs=[e["input"] for e in ex], outputs=[e["output"] for e in ex], metadata=[e["metadata"] for e in ex])
        try:
            client.datasets.create_dataset(name=name, **kw)
        except Exception:  # name taken: a new version of the same dataset
            client.datasets.add_examples_to_dataset(dataset=name, **kw)
        done[name] = len(ex)
    print("phoenix datasets: " + (", ".join(f"{n} ({c})" for n, c in done.items()) or "none to upload"))
    return done


def export_datasets(store=None, seed_dir="labels/seed", truth=None, client=None):
    """For `keelwater labels export --phoenix`: build and upload every label dataset."""
    return upload_datasets(build_label_datasets(store, seed_dir, truth), client)


# ---- experiments -------------------------------------------------------------------------------------------

SUITE_DATASET = {"ground-truth": "keelwater-ground-truth", "holdout": "keelwater-ground-truth", "stability": "keelwater-ground-truth",
                 "judges": "keelwater-labels-blind"}


def manifest_for(run_id, run_dirs=("reports/runs", ".scratch/eval/rep/runs")):
    """The run manifest (prompt and model versions) of run_id from a run report, else {}."""
    for d in run_dirs:
        for f in sorted(Path(d).glob("*.json")) if Path(d).is_dir() else []:
            rep = json.loads(f.read_text(encoding="utf-8"))
            if rep.get("run_id") == run_id:
                return rep.get("manifest", {})
    return {}


def log_experiment(report_path, dataset=None, manifest=None, client=None):
    """For `keelwater eval --phoenix`: log one suite report as a Phoenix experiment; never calls a model.

    The task returns the report's stored outcome; each numeric metric is an evaluator score (gate name = label pass/fail).
    # shortcut: metrics are suite-wide, so each example repeats the same score; upgrade to per-example outputs when stored per item
    """
    client = _client(client)
    if client is None:
        return None
    rep = json.loads(Path(report_path).read_text(encoding="utf-8"))
    name = dataset or SUITE_DATASET.get(rep["suite"], "keelwater-ground-truth")
    manifest = manifest if manifest is not None else manifest_for(rep["run_id"])
    gates = rep.get("gates", {})

    def evaluator(metric, value):
        def ev(output):
            return {"score": float(value), "label": "pass" if gates.get(metric, True) else "fail"}
        ev.__name__ = metric
        return ev

    evals = [evaluator(k, v) for k, v in rep.get("metrics", {}).items() if isinstance(v, (int, float))]
    evals += [evaluator(k, v) for k, v in gates.items() if k not in rep.get("metrics", {})]
    meta = {"suite": rep["suite"], "run_id": rep["run_id"], "seed": rep.get("seed"), "passed": rep["passed"],
            "prompt_versions": manifest.get("prompt_versions"), "model_ids": manifest.get("model_ids")}
    ds = client.datasets.get_dataset(dataset=name)
    exp = client.experiments.run_experiment(
        dataset=ds, task=lambda example: {"run_id": rep["run_id"], "passed": rep["passed"]}, evaluators=evals,
        experiment_name=f"{rep['suite']}-{rep['run_id']}", experiment_metadata=meta, print_summary=False)
    print(f"phoenix experiment: {rep['suite']}-{rep['run_id']} over {name} ({len(evals)} evaluators)")
    return exp
