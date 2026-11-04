"""Shared fixtures: FakeGateway, tmp_store, --live option. Tests never read the real .env."""

import json
from pathlib import Path

import pytest

from signal_engine.gateway import Gateway
from signal_engine.store import Store


def pytest_configure(config):
    # --basetemp in pyproject points at git-ignored .scratch/, absent on a fresh checkout
    Path(".scratch").mkdir(exist_ok=True)

ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="run tests marked live (need real keys)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_real_env(request, tmp_path, monkeypatch):
    """Point the key loader at a file that does not exist, so the main checkout's .env is never opened (live tests excepted)."""
    if "live" in request.keywords:
        return
    monkeypatch.setenv("KEELWATER_ENV_FILE", str(tmp_path / "absent.env"))
    for k in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def tmp_store(tmp_path):
    s = Store.fresh(tmp_path / "test.sqlite")
    yield s
    s.close()


class FakeGateway(Gateway):
    """Canned responses per stage; records calls; writes model_call rows like the real gateway.

    canned[stage] is a raw response dict ({"content": json_text} | {"embeddings": ...} | {"answers": ...}),
    a plain dict or list (wrapped by call kind), or a callable(body) returning either.
    """

    def __init__(self, store=None, canned=None, tmp=None, profile="demo", **kw):
        kw.setdefault("cache_dir", (tmp or Path(".scratch/fake_cache")))
        kw.setdefault("keys", {})
        super().__init__(store, profile, **kw)
        self.canned, self.calls = canned or {}, []

    def _live(self, stage, kind, body, call_id):
        self.calls.append((stage, kind, body))
        v = self.canned[stage]
        v = v(body) if callable(v) else v
        if isinstance(v, dict) and {"content", "embeddings", "answers"} & set(v):
            return {"usage": {"tokens_in": 10, "tokens_out": 5, **v.get("usage", {})}, **{k: x for k, x in v.items() if k != "usage"}}
        key = {"chat": "content", "embed": "embeddings", "decide": "answers"}[kind]
        return {key: json.dumps(v) if kind == "chat" else v, "usage": {"tokens_in": 10, "tokens_out": 5}}


@pytest.fixture
def fake_gateway(tmp_store, tmp_path):
    def make(canned=None, **kw):
        return FakeGateway(tmp_store, canned, tmp=tmp_path / "cache", run_id="r1", **kw)
    return make


@pytest.fixture
def live_gateway(request):
    """Profile demo with db, cache and reports under .scratch/; only used by tests under tests/live/."""
    scratch = ROOT / ".scratch" / "live"
    store = Store.fresh(scratch / "keelwater.sqlite")
    gw = Gateway(store, "demo", scratch / "llm_cache", run_id="live", max_usd=0.25)
    gw.report_dir = scratch / "reports"
    yield gw
    store.close()
