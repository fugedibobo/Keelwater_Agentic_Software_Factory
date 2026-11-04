"""`labels seed`: 60 constructed items per judge, 30 pass and 30 fail, origin synthetic_seed (docs/evals.md 5.5 and 7).

Built by construction from ground truth and a finished run's store; nothing is hand-labelled, and seed labels never grant trust.
Evidence is stored with each item so `eval --suite judges` can run the judge over it from the cache.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .. import brief as brief_mod, config, judges, pipeline
from ..contracts import Opportunity, OpportunityInsight
from ..gateway import Gateway
from ..store import Store, content_id
from .ground_truth import GT_PATH, Analysis, Truth, load_gt

FIXED_AT = "2026-11-03T00:00:00+00:00"
PASS_KINDS = ("real", "contradictory", "probe")
DEV_SHARE = 0.30
DEFECTS = {
    "unsupported_claim": "add one sentence stating a specific fact that no cited insight supports",
    "changed_number": "change one number about accounts, mentions or ARR to a different value",
    "misattributed_quote": "attribute one quoted sentence to a different customer than the one who said it",
    "flipped_stance": "reverse the meaning of one customer's position",
    "inflated_scope": "widen one claim to all customers or all motor insurers when only the cited accounts support it",
    "removed_contrary_evidence": "delete the sentence that cites contrary or conflicting evidence, or if none exists, state the evidence is unanimous",
}
DEFECT_SYSTEM = ("You create test data for a product-feedback checker. Rewrite the brief with exactly one controlled defect of the "
                 "requested kind and change nothing else. Return JSON: body_md is the full rewritten brief, changed_span is the exact "
                 "new or changed text as it appears in body_md.")
DEFECT_SCHEMA = {"type": "object", "properties": {"body_md": {"type": "string"}, "changed_span": {"type": "string"}},
                 "required": ["body_md", "changed_span"], "additionalProperties": False}


def theme_splits(keys):
    """{theme: 'dev'|'held_out'}: by theme, so no theme sits in two splits; 30% (at least one) of a pool's themes are dev."""
    ranked = sorted(keys, key=lambda k: hashlib.sha256(k.encode("utf-8")).hexdigest())
    n_dev = max(1, round(DEV_SHARE * len(ranked))) if len(ranked) > 1 else 0
    return {k: "dev" if i < n_dev else "held_out" for i, k in enumerate(ranked)}


def allocate(keys, n):
    keys = sorted(keys)
    return {k: n // len(keys) + (i < n % len(keys)) for i, k in enumerate(keys)} if keys else {}


def pick(items, j, size):
    size = min(size, len(items))
    start = (j * size) % len(items)
    return (items[start:] + items[:start])[:size]


def record(judge, n, verdict, theme, splits, evidence, meta=None):
    return {"kind": "label", "label_id": content_id("seed", judge, n), "judge": judge, "target_type": "seed",
            "target_id": f"seed-{judge}-{n:03d}", "verdict": verdict, "critique": "constructed from ground truth",
            "origin": "synthetic_seed", "blind": False, "split": splits[theme], "weight": 1.0, "actor": "seed",
            "created_at": FIXED_AT, "evidence": evidence, "meta": meta or {}}


def _words(text, n=60):
    return " ".join(str(text).split()[:n])


def _quote(item):
    raw = item["raw"] or {}
    return {"quote": item.get("quote") or _words(item["text"]), "route": raw.get("route"), "date": raw.get("occurred_at")}


def _bundles(pool, n):
    """n (theme, members) pairs, allocated across themes, member counts cycling 3 to 8."""
    out = []
    for key, count in allocate([k for k, v in pool.items() if v], n).items():
        for j in range(count):
            out.append((key, pick(pool[key], j, 3 + len(out) % 6)))
    return out


def _signal_evidence(members):
    first = members[0]
    problem = first.get("problem") or _words(first["text"], 40)
    return {"title": _words(problem, 12), "problem_statement": problem, "quotes": [_quote(m) for m in members[:12]]}


def signal_records(an, half):
    ok = [i for i in an.ins.values() if i["quote_match"] != "failed"]
    good, bad = {}, {}
    for i in sorted(ok, key=lambda i: i["insight_id"]):
        if an.truth.themes.get(i["theme"], {}).get("kind") in PASS_KINDS:
            good.setdefault(i["theme"], []).append(i)
    for s in sorted(an.snip.values(), key=lambda s: s["snippet_id"]):
        if s["label"].startswith("noise") and len(s["text"].split()) >= 5:
            bad.setdefault(theme_of(s["label"]) if s["label"] != "noise" else "noise", []).append(s)
    return _both("signal", good, bad, half, lambda ms: _signal_evidence(ms))


def theme_of(label):
    return label.split(":", 1)[1]


def _both(judge, good, bad, half, evidence):
    """half pass bundles from `good` and half fail bundles from `bad`, each class split by its own themes."""
    out = []
    for verdict, pool in (("pass", good), ("fail", bad)):
        splits = theme_splits([k for k, v in pool.items() if v])
        for n, (theme, members) in enumerate(_bundles(pool, half)):
            out.append(record(judge, len(out), verdict, theme, splits, evidence(members)))
    return out


def duplicate_records(store, an, half):
    good, bad = {}, {}
    for i in sorted((i for i in an.ins.values() if i["quote_match"] != "failed"), key=lambda i: i["insight_id"]):
        kind = an.truth.themes.get(i["theme"], {}).get("kind")
        (bad if kind in ("shipped", "roadmap") else good if kind in PASS_KINDS else {}).setdefault(i["theme"], []).append(i)

    def evidence(members):
        theme = members[0]["theme"]
        ref = (an.truth.themes[theme].get("product_ref") or {}).get("id")
        return {"problem_statement": members[0]["problem"], "similar": judges.similar_items(store, members[0]["problem"], str(ref) if ref else None)}

    out = []
    for verdict, pool in (("pass", good), ("fail", bad)):
        splits = theme_splits([k for k, v in pool.items() if v])
        for key, count in allocate([k for k, v in pool.items() if v], half).items():
            for j in range(count):
                out.append(record("duplicate", len(out), verdict, key, splits, evidence([pool[key][j % len(pool[key])]])))
    return out


def faithfulness_records(store, an, a, half):
    scratch = Store.fresh(Path(a.scratch) / "seed.sqlite")
    pool = {}
    for i in sorted((i for i in an.ins.values() if i["quote_match"] != "failed"), key=lambda i: i["insight_id"]):
        if an.truth.themes.get(i["theme"], {}).get("kind") in PASS_KINDS:
            pool.setdefault(i["theme"], []).append(i)
    bundles = _bundles(pool, half + 6)  # spare bundles for any brief that fails a deterministic check
    for table in ("account", "raw_record", "snippet"):
        for r in store.select(table):
            scratch.insert(table, r)
    for insight_id in {i["insight_id"] for _, ms in bundles for i in ms}:
        scratch.insert("insight", {k: v for k, v in store.select("insight", {"insight_id": insight_id})[0].items()})
    gw = Gateway(scratch, a.profile, a.cache_dir, "seed", a.max_usd)
    as_of = datetime.strptime(pipeline.DEFAULT_AS_OF, "%d/%m/%Y").date()
    ctx = pipeline.RunContext(scratch, gw, "seed", as_of, Path("."), 42, "all", a.profile, Path(a.scratch),
                              {n: config.load(n) for n in config.CONFIG_FILES}, a)
    theme_of_opp = {}
    for k, (theme, ms) in enumerate(bundles):
        oid = content_id("seed-opp", k)
        theme_of_opp[oid] = theme
        problem = ms[0]["problem"]
        scratch.insert("opportunity", Opportunity(opportunity_id=oid, title=_words(problem, 12), problem_statement=problem,
                                                  bucket=an.truth.themes[theme]["bucket"], first_seen_as_of=as_of))
        for m in ms:
            scratch.insert("opportunity_insight", OpportunityInsight(opportunity_id=oid, insight_id=m["insight_id"], similarity=1.0))
    gw.map(lambda o: brief_mod.write_brief(ctx, o), scratch.select("opportunity", order_by="opportunity_id"))
    evidence = {j[2]: j[3] for j in judges.jobs(ctx) if j[0] == "faithfulness"}
    good = [b for b in scratch.select("brief", order_by="opportunity_id") if b["check_status"] == "passed"]
    splits = theme_splits(sorted(set(theme_of_opp.values())))
    passes, fails = [], []
    for b in good:
        if len(fails) >= half:
            break
        kind = list(DEFECTS)[len(fails) % len(DEFECTS)]
        out = gw.chat("generate", [{"role": "system", "content": DEFECT_SYSTEM},
                                   {"role": "user", "content": json.dumps({"defect": kind, "instruction": DEFECTS[kind], "brief": b["body_md"]})}],
                      target_type="brief", target_id=b["brief_id"], prompt_version="seed-defect@1", schema=DEFECT_SCHEMA)
        span = str(out.get("changed_span", ""))
        if out.get("body_md") == b["body_md"] or not span or span not in out.get("body_md", ""):
            continue  # shortcut: an unusable defect is skipped, not retried; a spare brief takes its place
        theme = theme_of_opp[b["opportunity_id"]]
        n = len(passes) + len(fails)
        passes.append(record("faithfulness", n, "pass", theme, splits, evidence[b["brief_id"]], {"defect": None}))
        fails.append(record("faithfulness", n + 1, "fail", theme, splits, dict(evidence[b["brief_id"]], brief=out["body_md"]),
                            {"defect": kind, "changed_span": span}))
    scratch.close()
    return passes + fails


def main(a):
    gt_path = GT_PATH
    if not gt_path.is_file() or not Path(a.db).is_file():
        print(f"need ground truth at {gt_path.as_posix()} and a finished run's store at {a.db} (run: keelwater run --profile demo)")
        return 2
    store = Store(a.db)
    an = Analysis(store, Truth(load_gt(gt_path)))
    half = a.n // 2
    sets = {"signal": signal_records(an, half), "duplicate": duplicate_records(store, an, half), "faithfulness": faithfulness_records(store, an, a, half)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for judge, rows in sets.items():
        (out / f"{judge}.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8", newline="\n")
        by = {(v, s): sum(r["verdict"] == v and r["split"] == s for r in rows) for v in ("pass", "fail") for s in ("dev", "held_out")}
        print(f"{judge}: {len(rows)} items | pass dev {by['pass', 'dev']} held_out {by['pass', 'held_out']} | fail dev {by['fail', 'dev']} held_out {by['fail', 'held_out']}")
    store.close()
    return 0
