import copy
import hashlib
import re
from datetime import date
from pathlib import Path

import pytest

from signal_engine import config, triage
from signal_engine.contracts import Snippet
from signal_engine.gateway import BudgetExceeded, GatewayError
from signal_engine.pipeline import RunContext

ROOT = Path(__file__).resolve().parent.parent


def answers(p, conf=0.9, bucket="fnol_intake", score=1, kind="bug"):
    return {"is_product_signal": {"type": "noul", "noul": p}, "bucket": {"type": "choice", "choice": bucket, "confidence": conf},
            "severity": {"type": "score", "score": score}, "signal_type": {"type": "choice", "choice": kind}}


def fb(p, conf=0.9):
    return {"is_product_signal": p, "bucket": "fnol_intake", "bucket_confidence": conf, "severity": 2, "signal_type": "bug"}


def boom(body):
    raise GatewayError("down")


def setup(store, gw_factory, canned, texts, **kw):
    for sid, text in texts.items():
        store.insert("snippet", Snippet(snippet_id=sid, raw_id="raw", text=text))
    gw = gw_factory(canned, **kw)
    cfg = {n: config.load(n) for n in config.CONFIG_FILES}
    ctx = RunContext(store, gw, "r1", date(2026, 11, 3), Path("."), 42, "all", "demo", Path("."), cfg, None, "triage")
    return ctx, gw


def rows(store):
    return {r["snippet_id"]: r for r in store.select("triage")}


@pytest.mark.parametrize("p,conf,want", [(0.25, 0.9, "drop"), (0.0, 0.0, "drop"), (0.50, 0.70, "keep"), (0.95, 0.9, "keep"),
                                          (0.50, 0.69, "low_confidence"), (0.26, 0.9, "low_confidence"), (0.49, 0.99, "low_confidence")])
@pytest.mark.parametrize("backend", ["clef", "fallback"])
def test_gating_bands_per_backend(p, conf, want, backend):
    assert triage.gate(p, conf, config.load("pipeline")["triage"]["backends"][backend]) == want


def test_one_decide_call_asks_four_questions_and_every_row_has_a_call(tmp_store, fake_gateway):
    ctx, gw = setup(tmp_store, fake_gateway, {"triage": lambda b: answers(0.8)}, {"s1": "the form loses data"})
    triage.run(ctx)
    (c,) = gw.calls
    assert c[:2] == ("triage", "decide") and set(c[2]["questions"]) == {"is_product_signal", "bucket", "severity", "signal_type"}
    assert c[2]["model"] == "cloudflare/clef" and c[2]["provider"]["data_collection"] == "deny"
    r = rows(tmp_store)["s1"]
    assert (r["backend"], r["decision"], r["severity"], r["signal_type"]) == ("clef", "keep", 2, "bug") and r["latency_ms"] is not None
    assert r["call_id"] == tmp_store.select("model_call")[0]["call_id"]


def test_clef_failure_falls_back_to_clef_flash_through_the_decisions_api_and_loses_nothing(tmp_store, fake_gateway, capsys):
    texts = {f"s{i}": f"text {i}" for i in range(5)}
    ctx, gw = setup(tmp_store, fake_gateway, {"triage": boom, "triage_fallback": answers(0.9)}, texts)  # the probe fails too
    triage.run(ctx)
    rs = rows(tmp_store)
    assert len(rs) == 5 and {r["backend"] for r in rs.values()} == {"fallback"} and {r["decision"] for r in rs.values()} == {"keep"}
    kind, call = next(c for c in gw.calls if c[0] == "triage_fallback")[1:]
    assert kind == "decide" and call["model"] == "cloudflare/clef-flash" and "response_format" not in call and "messages" not in call
    assert call["provider"]["data_collection"] == "deny" and set(call["questions"]) == {"is_product_signal", "bucket", "severity", "signal_type"}
    assert tmp_store.select("model_call", {"stage": "triage_fallback"})
    assert capsys.readouterr().out.count("cloudflare/clef unavailable, using cloudflare/clef-flash") == 1


def test_a_profile_without_a_decision_fallback_still_falls_back_to_a_chat_model(tmp_store, fake_gateway):
    models = copy.deepcopy(config.load("models"))
    models["profiles"]["demo"]["stages"]["triage_fallback"] = {"model": "vendor/chat-model", "max_tokens": 256}  # no backend: a chat model
    texts = {f"s{i}": f"text {i}" for i in range(3)}
    ctx, gw = setup(tmp_store, fake_gateway, {"triage": boom, "triage_fallback": fb(0.9)}, texts, models=models)
    triage.run(ctx)
    rs = rows(tmp_store)
    assert {r["backend"] for r in rs.values()} == {"fallback"} and {r["decision"] for r in rs.values()} == {"keep"}
    kind, call = next(c for c in gw.calls if c[0] == "triage_fallback")[1:]
    assert kind == "chat" and call["response_format"]["type"] == "json_schema" and call["model"] == "vendor/chat-model"


def test_both_backends_fail_gives_untriaged_never_dropped(tmp_store, fake_gateway, capsys):
    ctx, _ = setup(tmp_store, fake_gateway, {"triage": boom, "triage_fallback": boom}, {"s1": "a", "s2": "b"})
    counts = triage.run(ctx)
    assert counts["untriaged"] == 2 and all(r["backend"] == "none" and r["is_signal_p"] is None for r in rows(tmp_store).values())
    assert "ALERT" in capsys.readouterr().out


def test_one_bad_snippet_falls_back_while_clef_stays_primary(tmp_store, fake_gateway):
    def clef(body):
        if body["state"] == "bad":
            raise GatewayError("x")
        return answers(0.9)

    ctx, _ = setup(tmp_store, fake_gateway, {"triage": clef, "triage_fallback": answers(0.3)}, {"a": "good", "b": "bad"})
    triage.run(ctx)
    rs = rows(tmp_store)
    assert (rs["a"]["backend"], rs["b"]["backend"], rs["b"]["decision"]) == ("clef", "fallback", "low_confidence")


def test_unknown_bucket_from_the_model_is_a_failed_call(tmp_store, fake_gateway):
    ctx, _ = setup(tmp_store, fake_gateway, {"triage": lambda b: answers(0.9, bucket="not_a_bucket"), "triage_fallback": answers(0.9)}, {"s1": "x"})
    triage.run(ctx)
    assert rows(tmp_store)["s1"]["backend"] == "fallback"


def test_budget_exceeded_is_not_swallowed(tmp_store, fake_gateway):
    def over(body):
        raise BudgetExceeded("over")

    ctx, _ = setup(tmp_store, fake_gateway, {"triage": over, "triage_fallback": answers(0.9)}, {"s1": "x"})
    with pytest.raises(BudgetExceeded):
        triage.run(ctx)


def test_reconciliation_and_a_decision_per_band(tmp_store, fake_gateway, capsys):
    p = {"keep": 0.9, "drop": 0.02, "mid": 0.3, "keep too": 0.9}  # distinct texts: equal texts share one cache file that a parallel read can see half-written
    ctx, _ = setup(tmp_store, fake_gateway, {"triage": lambda b: answers(p[b["state"]])}, {"s1": "keep", "s2": "drop", "s3": "mid", "s4": "keep too"})
    counts = triage.run(ctx)
    assert counts == {"keep": 2, "drop": 1, "low_confidence": 1, "untriaged": 0}
    assert "4 snippets = 2 keep + 1 drop + 1 low_confidence + 0 untriaged" in capsys.readouterr().out
    assert len(rows(tmp_store)) == 4


def test_replay_cache_miss_is_an_untriaged_row_and_reconciles_to_snippets_in(tmp_store, fake_gateway, capsys):
    for sid in ("s1", "s2", "s3"):
        tmp_store.insert("snippet", Snippet(snippet_id=sid, raw_id="raw", text=sid))
    warm = fake_gateway({"triage": lambda b: answers(0.9)})  # records s1 and s2 only
    for sid in ("s1", "s2"):
        warm.decide(sid, target_type="snippet", target_id=sid)
    gw = fake_gateway({}, profile="replay")
    cfg = {n: config.load(n) for n in config.CONFIG_FILES}
    ctx = RunContext(tmp_store, gw, "r1", date(2026, 11, 3), Path("."), 42, "all", "replay", Path("."), cfg, None, "triage")
    counts = triage.run(ctx)
    assert counts == {"keep": 2, "drop": 0, "low_confidence": 0, "untriaged": 1} and sum(counts.values()) == 3
    r = rows(tmp_store)["s3"]
    assert (r["backend"], r["decision"], r["call_id"]) == ("none", "untriaged", None) and gw.triage_cache_misses == 1
    assert "3 snippets = 2 keep + 0 drop + 0 low_confidence + 1 untriaged" in capsys.readouterr().out


def test_noise_audit_is_stratified_weighted_and_deterministic(tmp_store, fake_gateway):
    near, far = [f"n{i}" for i in range(40)], [f"f{i}" for i in range(10)]
    p = {**{s: 0.08 for s in near}, **{s: 0.01 for s in far}, "k": 0.9}
    ctx, _ = setup(tmp_store, fake_gateway, {"triage": lambda b: answers(p[b["state"]])}, {s: s for s in p})
    triage.run(ctx)
    w = {sid: r["audit_weight"] for sid, r in rows(tmp_store).items() if r["audit_weight"] is not None}
    assert sum(k.startswith("n") for k in w) == 25 and sum(k.startswith("f") for k in w) == 10  # all of a small stratum
    assert {v for k, v in w.items() if k.startswith("n")} == {40 / 25} and {v for k, v in w.items() if k.startswith("f")} == {1.0}
    assert rows(tmp_store)["k"]["audit_weight"] is None
    expected = sorted(near, key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:25]
    assert {k for k in w if k.startswith("n")} == set(expected)
    again = triage.audit_sample(list(rows(tmp_store).values()), config.load("pipeline")["noise_audit"]["strata"])
    assert again == w


def test_stage_is_registered_and_no_typesafe_path_exists():
    from signal_engine.pipeline import STAGES, resolve
    assert resolve(STAGES["triage"]) is triage.run
    for f in [*(ROOT / "signal_engine").glob("*.py"), *(ROOT / "config").glob("*.yaml"), ROOT / ".env.example"]:
        assert not re.search(r"TYPESAFE_API_KEY|api\.typesafe\.ai|jev-latest", f.read_text(encoding="utf-8"), re.I), f
