"""Pipeline runner. Every stage and hook is registered here up front as a lazy `module:function` string.

Later issues never edit this file: build the module, expose the function named below, done.
A stage function is `fn(ctx: RunContext)`; it reads and writes ctx.store and calls models only through ctx.gateway.
"""

import hashlib
import importlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from . import config, prompts
from .contracts import Run, RunManifest, RunReport
from .gateway import Gateway, GatewayError
from .store import Store

# name -> module:function (issue that builds it)
STAGES = {
    "connect": "signal_engine.ingest.connect:run",    # #3
    "segment": "signal_engine.ingest.segment:run",    # #3
    "triage": "signal_engine.triage:run",             # #4
    "extract": "signal_engine.extract:run",           # #5
    "cluster": "signal_engine.cluster:run",           # #5
    "tag": "signal_engine.tag:run",                   # #5
    "rank": "signal_engine.rank:run",                 # #5
    "brief": "signal_engine.brief:run",               # #6
    "judge": "signal_engine.judges:run",              # #6
    "review": "signal_engine.evals.labels:apply",     # #7
    "handoff": "signal_engine.handoff:run",           # #9
    "outtake": "signal_engine.outtake:run",           # #9
}
# Hooks take the same ctx (ctx.stage names the point). An unbuilt hook is skipped silently.
HOOKS = {
    "run_start": ["signal_engine.evals.labels:import_human"],   # #7: loads labels/human/*.jsonl
    "after_cluster": ["signal_engine.evals.labels:apply"],      # #7
    "after_tag": ["signal_engine.evals.labels:apply"],          # #7
    "tracing": ["signal_engine.telemetry:install"],        # #10: only with --phoenix; registers gateway.add_listener
}
DEFAULT_AS_OF = "03/11/2026"


def resolve(spec):
    """Import 'module:function'; None when the module or function is not built yet."""
    module_name, func = spec.split(":")
    try:
        return getattr(importlib.import_module(module_name), func, None)
    except ModuleNotFoundError as exc:
        if exc.name and (module_name == exc.name or module_name.startswith(exc.name + ".")):
            return None
        raise


@dataclass
class RunContext:
    store: Store
    gateway: Gateway
    run_id: str
    as_of: date
    data_dir: Path
    seed: int
    batch: str
    profile: str
    report_dir: Path
    config: dict
    args: object
    stage: str = ""


def data_hash(data_dir):
    """sha256 over every file under data_dir in sorted path order, LF line endings (docs/data.md 8.5)."""
    h = hashlib.sha256()
    d = Path(data_dir)
    for p in sorted(x for x in d.rglob("*") if x.is_file()) if d.is_dir() else []:
        h.update(p.relative_to(d).as_posix().encode("utf-8") + b"\0" + p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def report_path(report_dir, profile, seed, batch):
    suffix = ("-seed43" if seed == 43 else "") + ("" if batch == "all" else f"-{batch}")
    return Path(report_dir) / "runs" / f"latest-{profile}{suffix}.json"


def _call_hooks(name, ctx):
    for spec in HOOKS[name]:
        fn = resolve(spec)
        if fn:
            ctx.stage = name
            fn(ctx)


def run_pipeline(a):
    stages = a.stages.split(",") if a.stages else list(STAGES)
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        print(f"unknown stage(s): {', '.join(unknown)}; choose from {', '.join(STAGES)}")
        return 2
    as_of = datetime.strptime(a.as_of, "%d/%m/%Y").date()
    data_dir = Path(a.data or ("data/holdout/raw" if a.seed == 43 else "data/raw"))
    store = Store(a.db).init() if a.batch == "oct" else Store.fresh(a.db)
    run_id = uuid.uuid4().hex[:16]
    gw = Gateway(store, a.profile, a.cache_dir, run_id, a.max_usd)
    files = config.config_file_hashes()
    manifest = RunManifest(profile=a.profile, seed=a.seed, batch=a.batch, as_of=as_of, data_hash=data_hash(data_dir),
                           config_hash=config.config_hash(), config_files=files, prompt_versions=prompts.all_versions(),
                           model_ids=gw.model_ids())
    store.insert("run", Run(run_id=run_id, started_at=datetime.now(timezone.utc).isoformat(), as_of=as_of, profile=a.profile,
                            seed=a.seed, batch=a.batch, data_hash=manifest.data_hash, config_hash=manifest.config_hash,
                            prompt_versions=manifest.prompt_versions, model_ids=manifest.model_ids))
    path = report_path(a.report_dir, a.profile, a.seed, a.batch)
    if path.is_file():  # config change = audit event with old and new hash
        old = json.loads(path.read_text(encoding="utf-8"))["manifest"]["config_files"]
        for name, new in files.items():
            if old.get(name) != new:
                store.append_audit("system", "system", "config.changed", "config", name, {"old": old.get(name), "new": new})
    ctx = RunContext(store, gw, run_id, as_of, data_dir, a.seed, a.batch, a.profile, Path(a.report_dir),
                     {n: config.load(n) for n in config.CONFIG_FILES}, a)
    results = {}
    try:
        _call_hooks("run_start", ctx)
        if a.phoenix:
            _call_hooks("tracing", ctx)
        for name in stages:
            fn = resolve(STAGES[name])
            if fn is None:
                results[name] = "skipped (not built)"
            else:
                ctx.stage = name
                fn(ctx)
                results[name] = "done"
            print(f"{name}: {results[name]}")
            if f"after_{name}" in HOOKS:
                _call_hooks(f"after_{name}", ctx)
    except GatewayError as e:
        store.update("run", {"run_id": run_id}, {"status": "failed", "cost_usd": gw.spent})
        print(f"run failed: {e}")
        return 1
    if not store.verify_audit_chain():
        print("audit chain: BROKEN")
        return 1
    out = store.output_hash()
    manifest.cache_keys, manifest.model_ids, manifest.model_swaps = sorted(gw.used_keys), gw.model_ids(), dict(gw.swaps)
    store.update("run", {"run_id": run_id}, {"output_hash": out, "cost_usd": gw.spent, "status": "done",
                                             "model_ids": manifest.model_ids, "manifest_json": manifest.model_dump(mode="json")})
    report = RunReport(run_id=run_id, manifest=manifest, output_hash=out, stages=results, cost_usd=gw.spent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"output hash: {out}")
    if a.profile == "replay":
        ref = report_path(a.report_dir, "demo", a.seed, a.batch)
        if ref.is_file():
            print("MATCH" if json.loads(ref.read_text(encoding="utf-8"))["output_hash"] == out else "DIFF")
        else:
            print(f"no recorded demo run at {ref.as_posix()} to compare")
    print(f"report: {path.as_posix()}")
    store.close()
    return 0
