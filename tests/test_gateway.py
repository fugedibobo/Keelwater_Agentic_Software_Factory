import json
import logging
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import conftest
from signal_engine import config, gateway as gwm
from signal_engine.contracts import STAGE_OUTPUT
from signal_engine.gateway import Gateway, GatewayError, ReplayMiss, BudgetExceeded
from signal_engine.store import Store

FAKE_KEY = "sk-fake-0123456789-not-a-real-key"
LABEL = {"title": "T", "problem_statement": "P"}


class Resp:
    def __init__(self, d):
        self.d = d

    def model_dump(self):
        return self.d


class FakeClient:
    """Stands in for the openai SDK client; records the kwargs of every call."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda kw: {"choices": [{"message": {"content": json.dumps(LABEL)}}],
                                               "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001}})
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.embeddings = SimpleNamespace(create=self._emb)

    def _chat(self, **kw):
        self.calls.append(kw)
        return Resp(self.handler(kw))

    def _emb(self, **kw):
        self.calls.append(kw)
        return Resp({"data": [{"embedding": [0.5, 0.25]}], "usage": {"prompt_tokens": 7}})


def demo(tmp_path, client=None, **kw):
    store = Store.fresh(tmp_path / kw.pop("db", "g.sqlite"))
    return Gateway(store, kw.pop("profile", "demo"), tmp_path / "cache", run_id="r1", keys={"OPENROUTER_API_KEY": FAKE_KEY},
                   client=client or FakeClient(), sleep=lambda s: None, **kw)


def ask(gw, target="o1"):
    return gw.chat("cluster_label", [{"role": "user", "content": f"label {target}"}], target_type="opportunity", target_id=target)


def block_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network opened")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_read_through_records_then_hits_and_call_ids_agree_with_replay(tmp_path, monkeypatch):
    client = FakeClient()
    gw = demo(tmp_path, client)
    seen = []
    gwm.add_listener(lambda row, out: seen.append((row["call_id"], out)))
    try:
        assert ask(gw) == LABEL and len(client.calls) == 1
        assert ask(gw) == LABEL and len(client.calls) == 1  # hit
        (cache_file,) = list((tmp_path / "cache" / "cluster_label").glob("*.json"))
        assert set(json.loads(cache_file.read_text(encoding="utf-8"))) == {"request", "response"}  # bodies only
        live_id = gw.store.select("model_call")[0]["call_id"]
        replay = Gateway(gw.store, "replay", tmp_path / "cache", run_id="r2")
        block_network(monkeypatch)
        assert ask(replay) == LABEL
        row = gw.store.select("model_call")[0]
        assert row["call_id"] == live_id and row["cached"] == 1 and row["cost_usd"] == 0
        assert [s[0] for s in seen] == [live_id] * 3 and seen[0][1] == LABEL  # listeners get row and parsed output
    finally:
        gwm.clear_listeners()


def test_replay_miss_names_stage_and_request_hash_and_never_builds_a_client(tmp_path, monkeypatch):
    block_network(monkeypatch)
    monkeypatch.setattr(Gateway, "_make_client", lambda *a: pytest.fail("client built in replay"))
    gw = Gateway(None, "replay", tmp_path / "empty", run_id="r")
    with pytest.raises(ReplayMiss) as e:
        ask(gw)
    key = gwm.sha256(gwm.canonical(gw.chat_request("cluster_label", [{"role": "user", "content": "label o1"}])))
    assert "cluster_label" in str(e.value) and key in str(e.value)


def test_request_controls_and_probe_request(tmp_path):
    gw = demo(tmp_path)
    for stage in STAGE_OUTPUT:
        req = gw.chat_request(stage, gwm.PROBE_MESSAGES)
        assert req["provider"] == {"data_collection": "allow" if stage == "generate" else "deny", "require_parameters": True}
        assert req["response_format"]["type"] == "json_schema"
        probe = gw.probe_request(stage)
        assert probe["max_tokens"] == 32
        assert {k: v for k, v in probe.items() if k != "max_tokens"} == {k: v for k, v in req.items() if k != "max_tokens"}
    assert gw.probe_request("embed")["provider"]["data_collection"] == "deny"
    assert gw.probe_request("triage")["questions"].keys() == {"is_product_signal", "bucket", "severity", "signal_type"}


def test_budget_abort(tmp_path):
    gw = demo(tmp_path, client=FakeClient(lambda kw: {"choices": [{"message": {"content": json.dumps(LABEL)}}],
                                                      "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.6}}), max_usd=1.0)
    ask(gw, "a")
    with pytest.raises(BudgetExceeded, match="max-usd"):
        ask(gw, "b")


def test_cost_falls_back_to_token_prices(tmp_path):
    client = FakeClient(lambda kw: {"choices": [{"message": {"content": json.dumps(LABEL)}}],
                                    "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}})
    gw = demo(tmp_path, client, max_usd=100)
    ask(gw)
    assert gw.store.select("model_call")[0]["cost_usd"] == pytest.approx(0.10 + 0.90)


def test_retries_on_429_with_backoff(tmp_path):
    state = {"n": 0}

    class Busy(Exception):
        status_code = 429

    def handler(kw):
        state["n"] += 1
        if state["n"] < 3:
            raise Busy("slow down")
        return {"choices": [{"message": {"content": json.dumps(LABEL)}}], "usage": {}}

    assert ask(demo(tmp_path, FakeClient(handler))) == LABEL and state["n"] == 3


def test_fake_key_is_never_written_or_logged(tmp_path, caplog, monkeypatch):
    env = tmp_path / "keys.env"
    env.write_text(f"OPENROUTER_API_KEY={FAKE_KEY}\n", encoding="utf-8-sig")
    monkeypatch.setenv("KEELWATER_ENV_FILE", str(env))
    caplog.set_level(logging.DEBUG)

    def handler(kw):
        if kw["messages"][0]["content"] == "boom":
            raise RuntimeError(f"401 for key {FAKE_KEY}")
        return {"choices": [{"message": {"content": json.dumps(LABEL)}}], "usage": {"prompt_tokens": 1}}

    store = Store.fresh(tmp_path / "k.sqlite")
    gw = Gateway(store, "demo", tmp_path / "cache", run_id="r", client=FakeClient(handler))  # keys load from the env file
    assert gw.keys["OPENROUTER_API_KEY"] == FAKE_KEY
    ask(gw)
    with pytest.raises(GatewayError) as e:
        gw.chat("cluster_label", [{"role": "user", "content": "boom"}], target_type="o", target_id="x")
    assert FAKE_KEY not in str(e.value) and "[key]" in str(e.value)
    store.close()
    # a full demo-profile run writes db, report and logs: none may hold the key
    from signal_engine.cli import main
    assert main(["run", "--profile", "demo", "--stages", "connect,segment", "--data", "tests/fixtures/raw", "--db", str(tmp_path / "r.sqlite"),  # no model stage: no real network
                 "--cache-dir", str(tmp_path / "cache"), "--report-dir", str(tmp_path / "reports")]) == 0
    hits = [p for p in tmp_path.rglob("*") if p.is_file() and p != env and FAKE_KEY.encode() in p.read_bytes()]
    assert hits == [] and FAKE_KEY not in caplog.text


def test_aws_profile_sends_call_id_and_hosts_are_allow_listed(tmp_path, monkeypatch):
    models, vpc = config.load("models"), config.load("vpc_endpoints")
    assert gwm.host_violations(models, vpc) == []
    bad = json.loads(json.dumps(models))
    bad["profiles"]["aws"]["base_url"] = "https://openrouter.ai/api/v1"
    assert gwm.host_violations(bad, vpc) == [("aws", "https://openrouter.ai/api/v1")]
    bad["profiles"]["self-hosted"]["base_url"] = "https://api.typesafe.ai/v1"
    assert len(gwm.host_violations(bad, vpc)) == 2
    client = FakeClient()
    gw = demo(tmp_path, client, profile="aws")
    ask(gw)
    sent = client.calls[0]["extra_body"]
    assert sent["requestMetadata"] == {"call_id": gw.store.select("model_call")[0]["call_id"]} and "provider" not in sent
    assert not (tmp_path / "cache").exists()  # private-network data is not cached on disk
    monkeypatch.setenv("KEELWATER_AWS_BASE_URL", "https://openrouter.ai/api/v1")
    with pytest.raises(GatewayError, match="vpc_endpoints"):
        demo(tmp_path, profile="aws", db="g2.sqlite")


def test_decide_maps_clef_answers_to_triage_record(tmp_path):
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["Authorization"], json.loads(request.content)
        return httpx.Response(200, json={"model": "cloudflare/clef", "usage": {"input_tokens": 50, "cost": 0.00002}, "answers": {
            "is_product_signal": {"type": "noul", "noul": 0.8}, "bucket": {"type": "choice", "choice": "fnol_intake", "confidence": 0.9},
            "severity": {"type": "score", "score": 2.2}, "signal_type": {"type": "choice", "choice": "bug", "confidence": 0.7}}})

    store = Store.fresh(tmp_path / "j.sqlite")
    gw = Gateway(store, "demo", tmp_path / "cache", run_id="r", keys={"OPENROUTER_API_KEY": FAKE_KEY},
                 http=httpx.Client(transport=httpx.MockTransport(handler)))
    out = gw.decide("the claim form loses data", target_type="snippet", target_id="s1")
    assert out == {"is_signal_p": 0.8, "bucket": "fnol_intake", "bucket_conf": 0.9, "severity": 3, "signal_type": "bug"}
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions" and seen["auth"] == f"Bearer {FAKE_KEY}"
    assert seen["body"]["model"] == "cloudflare/clef" and seen["body"]["provider"]["data_collection"] == "deny"
    assert FAKE_KEY not in "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "cache").rglob("*.json"))
    (row,) = store.select("model_call")
    assert row["stage"] == "triage" and row["cost_usd"] == 0.00002


def test_embed_goes_through_the_cache(tmp_path):
    client = FakeClient()
    gw = demo(tmp_path, client)
    assert gw.embed("embed", ["a"], target_type="insight", target_id="i") == [[0.5, 0.25]]
    gw.embed("embed", ["a"], target_type="insight", target_id="i")
    assert len(client.calls) == 1


# ---- probe ----------------------------------------------------------------------------------------------------
def test_probe_table_fallback_and_missing_clef_key(fake_gateway):
    def brief(body):
        if body["model"] == "deepseek/deepseek-v3.2":
            raise GatewayError("model not served")
        return {"body_md": "x", "citations": []}

    gw = fake_gateway({"triage_fallback": {"is_product_signal": 0.5, "bucket": "fnol_intake", "bucket_confidence": 0.9, "severity": 1, "signal_type": "bug"},
                       "brief": brief})
    rows, ok = gwm.run_probe(gw, ["triage", "triage_fallback", "brief"], out=lambda s: None)
    assert ok
    assert rows[0] == ("triage", "cloudflare/clef", "-", "skipped (no key)", "-")
    assert [r[:4] for r in rows[1:]] == [("triage_fallback", "openai/gpt-oss-120b", "primary", "ok"),
                                         ("brief", "deepseek/deepseek-v3.2", "primary", "fail"),
                                         ("brief", "deepseek/deepseek-v4-pro-0813", "fallback", "ok")]
    assert gw.swaps == {"brief": "deepseek/deepseek-v4-pro-0813"}
    assert all(c[2].get("max_tokens", 32) == 32 for c in gw.calls if "questions" not in c[2])


def test_probe_main_without_key_exits_1_with_no_network(monkeypatch, capsys):
    block_network(monkeypatch)
    monkeypatch.setattr(Gateway, "_make_client", lambda *a: pytest.fail("client built"))
    assert gwm.probe_main(["--profile", "demo"]) == 1
    assert capsys.readouterr().out.strip() == "keys missing: OPENROUTER_API_KEY"


def test_key_usage_prints_usage_and_limit_only(tmp_path, capsys, monkeypatch):
    store = Store.fresh(tmp_path / "u.sqlite")
    gw = Gateway(store, "demo", keys={"OPENROUTER_API_KEY": FAKE_KEY},
                 http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {"usage": 0.12, "limit": 10, "label": "secret-ish"}}))))
    monkeypatch.setattr(gwm, "Gateway", lambda profile: gw)
    assert gwm.probe_main(["--key-usage"]) == 0
    out = capsys.readouterr().out
    assert "0.12" in out and "10" in out and FAKE_KEY not in out and "secret-ish" not in out


# ---- .env locator ---------------------------------------------------------------------------------------------
def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


def test_env_loader_finds_main_checkout_from_worktree_not_parents_or_clones(tmp_path, monkeypatch):
    monkeypatch.delenv("KEELWATER_ENV_FILE")
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    git(main, "commit", "-q", "--allow-empty", "-m", "x")
    (main / ".env").write_text("OPENROUTER_API_KEY=from-main\n", encoding="utf-8-sig")
    git(main, "worktree", "add", "-q", str(tmp_path / "wt"))
    assert config.find_env_file(tmp_path / "wt").resolve() == (main / ".env").resolve()
    assert config.load_keys(tmp_path / "wt")["OPENROUTER_API_KEY"] == "from-main"
    git(tmp_path, "clone", "-q", str(main), "clone")
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=from-parent\n", encoding="utf-8")  # parent of the clone
    assert config.find_env_file(tmp_path / "clone").resolve() == (tmp_path / "clone" / ".env").resolve()
    assert "OPENROUTER_API_KEY" not in config.load_keys(tmp_path / "clone")
    monkeypatch.setenv("KEELWATER_ENV_FILE", str(main / ".env"))
    assert config.find_env_file() == main / ".env"


# ---- --live option --------------------------------------------------------------------------------------------
def test_live_marker_skips_without_option_and_runs_with_it():
    for flag, expect in ((False, 1), (True, 0)):
        marks = []
        live = SimpleNamespace(keywords={"live": 1}, add_marker=marks.append)
        normal = SimpleNamespace(keywords={}, add_marker=lambda m: pytest.fail("skipped a normal test"))
        conftest.pytest_collection_modifyitems(SimpleNamespace(getoption=lambda name: flag), [live, normal])
        assert len(marks) == expect


# ---- cache prune ----------------------------------------------------------------------------------------------
def test_prune_keeps_demo_run_and_newest_eval_files(tmp_path):
    cache, rep = tmp_path / "cache", tmp_path / "reports"
    for key in ("a1", "b2", "c3", "d4", "e5"):
        (cache / "extract").mkdir(parents=True, exist_ok=True)
        (cache / "extract" / f"{key}.json").write_text("{}", encoding="utf-8")
    (rep / "runs").mkdir(parents=True)
    (rep / "eval" / "baseline").mkdir(parents=True)
    (rep / "runs" / "latest-demo.json").write_text(json.dumps({"manifest": {"cache_keys": ["extract/a1"]}}), encoding="utf-8")
    (rep / "runs" / "latest-replay.json").write_text(json.dumps({"manifest": {"cache_keys": ["extract/e5"]}}), encoding="utf-8")
    old = rep / "eval" / "ground-truth-r1.json"
    old.write_text(json.dumps({"cache_keys": ["extract/b2"]}), encoding="utf-8")
    new = rep / "eval" / "ground-truth-r2.json"
    new.write_text(json.dumps({"cache_keys": ["extract/c3"]}), encoding="utf-8")
    import os
    os.utime(old, (1, 1))
    (rep / "eval" / "baseline" / "x.json").write_text(json.dumps({"cache_keys": ["extract/e5"]}), encoding="utf-8")
    assert [p.stem for p in gwm.prune(cache, rep, dry_run=True)] == ["b2", "d4", "e5"]
    assert len(list((cache / "extract").glob("*.json"))) == 5
    gwm.prune(cache, rep)
    assert sorted(p.stem for p in (cache / "extract").glob("*.json")) == ["a1", "c3"]


def test_only_generate_allows_data_collection(tmp_path):
    gw = demo(tmp_path)
    for stage, c in gw.cfg["stages"].items():
        if "backend" in c or stage == "embed":
            continue
        want = "allow" if stage == "generate" else "deny"
        assert gw.chat_request(stage, gwm.PROBE_MESSAGES, schema={"type": "object"})["provider"]["data_collection"] == want
    assert gw.stage_cfg("generate")["price"] == {"in": 0, "out": 0}


def test_rpm_pacing_spaces_requests(tmp_path):
    sleeps = []
    gw = demo(tmp_path)
    gw._sleep = sleeps.append
    c = {"rpm": 20}
    for _ in range(3):
        gw._pace("generate", c)
    assert len(sleeps) == 2 and sleeps[0] == pytest.approx(3, abs=0.1) and sleeps[1] == pytest.approx(6, abs=0.1)


def test_invalid_response_keeps_finish_reason(tmp_path):
    client = FakeClient(lambda kw: {"choices": [{"message": {"content": ""}, "finish_reason": "length"}], "usage": {}})
    gw = demo(tmp_path, client)
    with pytest.raises(gwm.InvalidResponse, match="finish_reason=length"):
        ask(gw)


def test_reasoning_option_reaches_generate_requests_only(tmp_path):
    gw = demo(tmp_path)
    assert gw.chat_request("generate", gwm.PROBE_MESSAGES, schema={"type": "object"})["reasoning"] == {"enabled": False}
    assert "reasoning" not in gw.chat_request("extract", gwm.PROBE_MESSAGES)
