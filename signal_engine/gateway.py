"""The only place that calls a model: cache, replay, cost, budget, call logging, probe and cache prune."""

import argparse
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .contracts import STAGE_OUTPUT, SignalType
from .store import canonical, sha256

log = logging.getLogger("keelwater.gateway")
DEFAULT_CACHE = "fixtures/llm_cache"
PROVIDER = {"data_collection": "deny", "require_parameters": True}  # OpenRouter request controls (ADR-002)
PROBE_MAX_TOKENS = 32
PROBE_MESSAGES = [{"role": "user", "content": "Reply with a short JSON object."}]
RETRY_STATUS = (429, 529)
_LISTENERS = []


class GatewayError(Exception):
    pass


class ReplayMiss(GatewayError):
    pass


class BudgetExceeded(GatewayError):
    pass


class InvalidResponse(GatewayError):
    """Null, empty or unparseable model content: never cached, retried, then raised."""


class Unavailable(GatewayError):
    pass


def add_listener(fn):
    """fn(model_call_row, parsed_output) runs after every call (the hook #10 uses for spans)."""
    _LISTENERS.append(fn)


def clear_listeners():
    _LISTENERS.clear()


def call_id_for(stage, input_hash, target_type, target_id):
    return sha256(canonical([stage, input_hash, target_type, target_id]))[:16]


def resolve_profile(models, name):
    """Profile config with `extends` applied and stage_defaults merged into every stage."""
    prof = dict(models["profiles"][name])
    if "extends" in prof:
        base = resolve_profile(models, prof.pop("extends"))
        prof = {**base, **prof}
    prof["stages"] = {s: {**models.get("stage_defaults", {}), **c} for s, c in prof["stages"].items()}
    return prof


def host_violations(models, vpc):
    """Base URLs of the aws and self-hosted profiles outside vpc_endpoints, or naming typesafe or openrouter."""
    bad = []
    for name in ("aws", "self-hosted"):
        prof = resolve_profile(models, name)
        urls = [prof["base_url"]] + [c["base_url"] for c in prof["stages"].values() if "base_url" in c]
        for u in urls:
            host = urlparse(u).hostname or ""
            if host not in vpc["hosts"] or "typesafe" in u.lower() or "openrouter" in u.lower():
                bad.append((name, u))
    return bad


def strict_schema(model):
    s = model.model_json_schema()
    s["required"] = list(s.get("properties", {}))
    s["additionalProperties"] = False
    return s


class Gateway:
    def __init__(self, store=None, profile="replay", cache_dir=DEFAULT_CACHE, run_id=None, max_usd=1.0,
                 keys=None, client=None, http=None, models=None, vpc=None, sleep=time.sleep):
        self.store, self.profile, self.run_id, self.max_usd = store, profile, run_id, max_usd
        self.cache_dir = Path(cache_dir)
        self.models = models or config.load("models")
        self.cfg = resolve_profile(self.models, profile)
        self.cache_only = bool(self.cfg.get("cache_only"))
        self._keys, self._client, self._http, self._sleep = keys, client, http, sleep
        self.spent, self.used_keys, self.swaps = 0.0, set(), {}
        self._lock = threading.Lock()
        if profile in ("aws", "self-hosted"):  # env overrides included: egress is allow-listed, never open
            host = urlparse(self.stage_cfg("extract")["base_url"]).hostname
            if host not in (vpc or config.load("vpc_endpoints"))["hosts"]:
                raise GatewayError(f"host {host!r} is not in config/vpc_endpoints.yaml")

    # ---- config helpers -------------------------------------------------------------------------------------
    def stage_cfg(self, stage):
        if stage not in self.cfg["stages"]:
            raise GatewayError(f"profile {self.profile} has no stage {stage!r}")
        base = os.environ.get(self.cfg.get("base_url_env", ""), "") or self.cfg.get("base_url")
        return {"base_url": base, "key_env": self.cfg.get("key_env"), **self.cfg["stages"][stage]}

    def model_ids(self):
        return {s: self.swaps.get(s, c["model"]) for s, c in self.cfg["stages"].items()}

    @property
    def keys(self):
        if self._keys is None:
            self._keys = config.load_keys()
        return self._keys

    def key(self, env_name):
        if not self.keys.get(env_name):
            raise Unavailable(f"keys missing: {env_name}")
        return self.keys[env_name]

    def scrub(self, text):
        for v in self.keys.values():
            if v:
                text = str(text).replace(v, "[key]")
        return text

    # ---- request builders (the real request; probe reuses them) --------------------------------------------
    def _is_openrouter(self, stage):
        return "openrouter" in (self.stage_cfg(stage)["base_url"] or "")

    def chat_request(self, stage, messages, schema=None, max_tokens=None, model=None):
        c = self.stage_cfg(stage)
        schema = schema or STAGE_OUTPUT.get(stage)
        body = {"model": model or c["model"], "messages": messages, "temperature": c["temperature"],
                "max_tokens": max_tokens or c["max_tokens"]}
        if schema is not None:
            sch = schema if isinstance(schema, dict) else strict_schema(schema)
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": stage, "strict": True, "schema": sch}}
        if self._is_openrouter(stage):
            body["provider"] = dict(PROVIDER)
            body["usage"] = {"include": True}
        return body

    def embed_request(self, stage, texts, model=None):
        c = self.stage_cfg(stage)
        body = {"model": model or c["model"], "input": list(texts)}
        if self._is_openrouter(stage):
            body["provider"] = dict(PROVIDER)
        return body

    def decide_request(self, stage, text, model=None):
        # shortcut: question field names follow the vendor docs summary (docs/research), verify with `keelwater probe`.
        c = self.stage_cfg(stage)
        buckets = {b["id"]: b["description"] for b in config.load("taxonomy")["buckets"]}
        return {"model": model or c["model"], "state": text, "questions": {
            "is_product_signal": {"type": "noul", "instructions": "Is this a problem or request about the Keelwater product that a product squad could act on?"},
            "bucket": {"type": "choice", "instructions": "Which product area does it belong to?", "options": buckets},
            "severity": {"type": "score", "instructions": "How severe is the impact on the customer (1 low, 4 blocking)?", "levels": 4},
            "signal_type": {"type": "choice", "instructions": "What kind of signal is it?", "options": {t.value: t.value for t in SignalType}}}}

    def probe_request(self, stage, model=None):
        c = self.stage_cfg(stage)
        if stage == "embed":
            return self.embed_request(stage, ["probe"], model)
        if c.get("backend") == "jev":
            return self.decide_request(stage, "probe", model)
        return self.chat_request(stage, PROBE_MESSAGES, max_tokens=PROBE_MAX_TOKENS, model=model)

    # ---- the one call path ---------------------------------------------------------------------------------
    def _cache_path(self, stage, body):
        key = sha256(canonical(body))
        return key, self.cache_dir / stage / f"{key}.json"

    def _call(self, stage, kind, body, target_type, target_id, prompt_version=""):
        t0 = time.perf_counter()
        key, path = self._cache_path(stage, body)
        cached, raw = False, None
        if self.profile in ("replay", "demo") and path.is_file():
            try:
                raw, cached = json.loads(path.read_text(encoding="utf-8"))["response"], True
            except (ValueError, KeyError):  # half-written or corrupt file is a miss
                raw = None
        if raw is not None:
            pass
        elif self.cache_only:
            raise ReplayMiss(f"replay cache miss: stage={stage} request_hash={key}")
        else:
            raw = self._live_valid(stage, kind, body, call_id_for(stage, sha256(canonical(body)), target_type, target_id))
            if self.profile == "demo":  # aws and self-hosted data never goes to disk
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
                tmp.write_text(json.dumps({"request": body, "response": raw}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                try:
                    os.replace(tmp, path)  # atomic: a reader never sees a partial file
                except PermissionError:  # Windows: target is open by a reader; same key means same content, so keep it
                    tmp.unlink(missing_ok=True)
        if self.profile in ("replay", "demo"):
            self.used_keys.add(f"{stage}/{key}")
        usage = raw.get("usage", {})
        cost = 0.0 if cached else self._cost(stage, usage)
        row = {"call_id": call_id_for(stage, sha256(canonical(body)), target_type, target_id), "run_id": self.run_id,
               "stage": stage, "target_type": target_type, "target_id": target_id, "model": body["model"],
               "profile": self.profile, "endpoint": self.stage_cfg(stage)["base_url"], "prompt_version": prompt_version,
               "input_hash": sha256(canonical(body)), "output_hash": sha256(canonical({k: v for k, v in raw.items() if k != "usage"})),
               "tokens_in": usage.get("tokens_in", 0), "tokens_out": usage.get("tokens_out", 0), "cost_usd": cost,
               "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "cached": cached}
        parsed = raw.get("answers") or raw.get("embeddings") or json.loads(raw["content"])
        if self.store is not None:
            self.store.insert("model_call", row, replace=True)
        for fn in list(_LISTENERS):
            fn(row, parsed)
        log.info("call stage=%s target=%s/%s cached=%s ms=%s", stage, target_type, target_id, cached, row["latency_ms"])
        with self._lock:
            self.spent += cost
        if self.spent > self.max_usd:
            raise BudgetExceeded(f"spend USD {self.spent:.4f} passed --max-usd {self.max_usd}")
        return raw

    def _cost(self, stage, usage):
        if usage.get("cost_usd") is not None:
            return float(usage["cost_usd"])
        p = self.stage_cfg(stage).get("price", {"in": 0, "out": 0})
        return (usage.get("tokens_in", 0) * p["in"] + usage.get("tokens_out", 0) * p["out"]) / 1e6

    def chat(self, stage, messages, *, target_type, target_id, prompt_version="", schema=None):
        body = self.chat_request(stage, messages, schema)
        return json.loads(self._call(stage, "chat", body, target_type, target_id, prompt_version)["content"])

    def embed(self, stage, texts, *, target_type, target_id):
        return self._call(stage, "embed", self.embed_request(stage, texts), target_type, target_id)["embeddings"]

    def decide(self, text, *, target_type, target_id, stage="triage"):
        """Decision-model adapter: Jev answers four questions in one call; mapped to the triage record."""
        a = self._call(stage, "decide", self.decide_request(stage, text), target_type, target_id)["answers"]
        return map_jev_answers(a)

    def map(self, fn, items):
        """Run fn over items with the stage concurrency (8 by default)."""
        with ThreadPoolExecutor(max_workers=self.models.get("stage_defaults", {}).get("concurrency", 8)) as pool:
            return list(pool.map(fn, items))

    def _live_valid(self, stage, kind, body, call_id):
        attempts = self.stage_cfg(stage)["retries"] + 1
        for i in range(attempts):
            raw = self._live(stage, kind, body, call_id)
            if kind != "chat":
                return raw
            try:
                json.loads(raw.get("content") or "")
                return raw
            except (TypeError, ValueError):
                with self._lock:  # a bad response is still billed
                    self.spent += self._cost(stage, raw.get("usage", {}))
                if i < attempts - 1:
                    self._sleep(min(0.5 * 2 ** i, 8))
        raise InvalidResponse(f"{stage} call returned null, empty or unparseable content after {attempts} attempts")

    # ---- live transport ------------------------------------------------------------------------------------
    def _live(self, stage, kind, body, call_id):
        c = self.stage_cfg(stage)
        attempts = c["retries"] + 1
        for i in range(attempts):
            try:
                if c.get("backend") == "jev":
                    return self._jev(c, body)
                return self._openai(stage, c, kind, body, call_id)
            except Unavailable:
                raise
            except Exception as e:  # scrub: never let a key reach a log or a report
                status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
                if status in RETRY_STATUS and i < attempts - 1:
                    self._sleep(min(0.5 * 2 ** i, 8))
                    continue
                raise GatewayError(self.scrub(f"{stage} call failed: {type(e).__name__}: {e}")) from None

    def _openai(self, stage, c, kind, body, call_id):
        client = self._client or self._make_client(c)
        extra = {k: body[k] for k in ("provider", "usage") if k in body}
        if self.cfg.get("request_metadata"):
            extra["requestMetadata"] = {"call_id": call_id}
        kwargs = {k: v for k, v in body.items() if k not in ("provider", "usage")}
        if kind == "embed":
            r = client.embeddings.create(**kwargs, extra_body=extra, timeout=c["timeout_s"]).model_dump()
            u = r.get("usage") or {}
            return {"embeddings": [d["embedding"] for d in r["data"]],
                    "usage": {"tokens_in": u.get("prompt_tokens", 0), "tokens_out": 0, "cost_usd": u.get("cost")}}
        r = client.chat.completions.create(**kwargs, extra_body=extra, timeout=c["timeout_s"]).model_dump()
        u = r.get("usage") or {}
        return {"content": r["choices"][0]["message"]["content"],
                "usage": {"tokens_in": u.get("prompt_tokens", 0), "tokens_out": u.get("completion_tokens", 0), "cost_usd": u.get("cost")}}

    def _make_client(self, c):
        from openai import OpenAI
        return OpenAI(base_url=c["base_url"], api_key=self.key(c["key_env"]), max_retries=0)

    def _jev(self, c, body):
        import httpx
        http = self._http or httpx.Client()
        r = http.post(c["base_url"].rstrip("/") + "/v1/systemone", json=body, timeout=c["timeout_s"],
                      headers={"Authorization": f"Bearer {self.key(c['key_env'])}"})
        r.raise_for_status()
        d = r.json()
        u = d.get("usage") or {}
        return {"answers": d["answers"], "usage": {"tokens_in": u.get("input_tokens", u.get("prompt_tokens", 0)), "tokens_out": 0}}

    def probe_one(self, stage, model=None):
        """One real call with the stage's real parameters and max_tokens 32; returns latency in ms."""
        body = self.probe_request(stage, model)
        t0 = time.perf_counter()
        self._live(stage, "embed" if stage == "embed" else "decide" if "questions" in body else "chat", body, "probe")
        return round((time.perf_counter() - t0) * 1000)

    def key_usage(self):
        import httpx
        r = (self._http or httpx.Client()).get("https://openrouter.ai/api/v1/key", timeout=15,
                                               headers={"Authorization": f"Bearer {self.key('OPENROUTER_API_KEY')}"})
        r.raise_for_status()
        d = r.json().get("data", {})
        return {"usage": d.get("usage"), "limit": d.get("limit")}


def map_jev_answers(a):
    """Jev answers -> triage record. shortcut: answer shapes follow the vendor docs summary, verified by the live probe."""
    def num(v, *names):
        if isinstance(v, dict):
            for n in names:
                if n in v:
                    return float(v[n])
        return float(v)

    def pick(v):
        if isinstance(v, dict):
            return v.get("choice") or v.get("label") or v.get("answer"), float(v.get("confidence", 0))
        return v, 1.0

    bucket, conf = pick(a["bucket"])
    sev = a["severity"]
    sev = int(sev.get("score", sev.get("level"))) if isinstance(sev, dict) else int(sev)
    return {"is_signal_p": num(a["is_product_signal"], "probability", "yes", "p"), "bucket": bucket, "bucket_conf": conf,
            "severity": max(1, min(4, sev)), "signal_type": pick(a["signal_type"])[0]}


# ---- probe command -----------------------------------------------------------------------------------------

def run_probe(gw, stages, out=print):
    """Returns (rows, ok). Each row: (stage, model, served, status, latency_ms)."""
    rows = []
    for stage in stages:
        c = gw.stage_cfg(stage)
        if c.get("backend") == "jev" and not gw.keys.get(c["key_env"]):
            rows.append((stage, c["model"], "-", "skipped (no key)", "-"))
            continue
        for served, model in (("primary", c["model"]), ("fallback", c.get("fallback"))):
            if not model:
                continue
            try:
                rows.append((stage, model, served, "ok", gw.probe_one(stage, model)))
                if served == "fallback":
                    gw.swaps[stage] = model
                break
            except GatewayError as e:
                log.info("probe %s %s failed: %s", stage, served, e)
                rows.append((stage, model, served, "fail", "-"))
    out(f"{'stage':<16}{'model':<40}{'served':<10}{'status':<18}latency_ms")
    for r in rows:
        out(f"{r[0]:<16}{r[1]:<40}{r[2]:<10}{r[3]:<18}{r[4]}")
    # a primary fail followed by a fallback ok is a swap, not a failure
    ok = all(any(x[0] == s and x[3] in ("ok", "skipped (no key)") for x in rows) for s in stages)
    return rows, ok


def probe_main(argv):
    ap = argparse.ArgumentParser(prog="keelwater probe")
    ap.add_argument("--profile", default="demo", choices=["demo", "aws", "self-hosted"])
    ap.add_argument("--stages")
    ap.add_argument("--key-usage", action="store_true")
    a = ap.parse_args(argv)
    gw = Gateway(profile=a.profile)
    need = gw.cfg["key_env"]
    if not gw.keys.get(need):
        print(f"keys missing: {need}")
        return 1
    if a.key_usage:
        u = gw.key_usage()
        print(f"usage: {u['usage']}  limit: {u['limit']}")
        return 0
    stages = a.stages.split(",") if a.stages else list(gw.cfg["stages"])
    _, ok = run_probe(gw, stages)
    return 0 if ok else 1


# ---- cache prune -------------------------------------------------------------------------------------------

def keep_keys(report_dir):
    """Cache keys named by the latest demo run reports and the newest report of each eval suite."""
    report_dir = Path(report_dir)
    files = list((report_dir / "runs").glob("latest-demo*.json"))
    newest = {}
    for f in (report_dir / "eval").glob("*.json"):
        suite = f.stem.rsplit("-", 1)[0]
        if suite not in newest or f.stat().st_mtime > newest[suite].stat().st_mtime:
            newest[suite] = f
    keys = set()
    for f in files + list(newest.values()):
        d = json.loads(f.read_text(encoding="utf-8"))
        keys.update(d.get("cache_keys") or d.get("manifest", {}).get("cache_keys", []))
    return keys


def prune(cache_dir=DEFAULT_CACHE, report_dir="reports", dry_run=False):
    keep = keep_keys(report_dir)
    gone = [p for p in sorted(Path(cache_dir).glob("*/*.json")) if f"{p.parent.name}/{p.stem}" not in keep]
    if not dry_run:
        for p in gone:
            p.unlink()
    return gone


def cache_main(argv):
    ap = argparse.ArgumentParser(prog="keelwater cache")
    ap.add_argument("action", choices=["prune"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE)
    ap.add_argument("--report-dir", default="reports")
    a = ap.parse_args(argv)
    gone = prune(a.cache_dir, a.report_dir, a.dry_run)
    print(f"{'would delete' if a.dry_run else 'deleted'} {len(gone)} cache files")
    return 0
