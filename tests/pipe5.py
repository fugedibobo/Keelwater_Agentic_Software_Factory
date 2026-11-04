"""Helpers for the extract, cluster, tag and rank tests: seed fixture rows, build a RunContext, fake embeddings."""

from datetime import date
from pathlib import Path

from signal_engine import contracts as c
from signal_engine.pipeline import RunContext
from signal_engine.store import raw_id, snippet_id

AS_OF = date(2026, 11, 3)


def ctx_for(store, gw, batch="all", run_id="r1", as_of=AS_OF):
    from signal_engine import config
    return RunContext(store, gw, run_id, as_of, Path("."), 42, batch, "demo", Path(".scratch"),
                      {n: config.load(n) for n in config.CONFIG_FILES}, None)


def seed_account(store, account_id, arr=None, renewal=None, tier="Enterprise"):
    store.insert("account", c.Account(account_id=account_id, name=f"Account {account_id}", arr_gbp=arr, tier=tier,
                                      renewal_date=renewal), replace=True)


def seed_snippet(store, key, text, *, source="intercom", route="support", account="A01", status="resolved",
                 occurred="2026-10-20T09:00:00Z", decision="keep", severity=3, bucket="documents_evidence",
                 context=None, run_id="r1"):
    rid = raw_id(source, key)
    store.insert("raw_record", c.RawRecord(raw_id=rid, source=source, route=route, source_id=key, account_id=account,
                                           account_status=status, occurred_at=occurred, payload_json={}), replace=True)
    sid = snippet_id(rid, 0, text)
    store.insert("snippet", c.Snippet(snippet_id=sid, raw_id=rid, text=text, context_text=context), replace=True)
    store.insert("triage", c.Triage(snippet_id=sid, run_id=run_id, backend="fallback", is_signal_p=0.9, bucket=bucket,
                                    bucket_conf=0.9, severity=severity if decision != "untriaged" else None,
                                    decision=decision), replace=True)
    return sid


def embedder(table, dim=4):
    """Canned embed response: each input text gets the vector of the first table key it contains."""
    def fn(body):
        out = []
        for t in body["input"]:
            out.append(next((v for k, v in table.items() if k in t), [0.0] * dim))
        return {"embeddings": out}
    return fn
