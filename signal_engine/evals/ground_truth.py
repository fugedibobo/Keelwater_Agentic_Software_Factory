"""Suite 1 (and the scoring core of the held-out suite): match the store to planted ground truth (docs/evals.md 3.5, 4.1, 4.2, 6).

Only signal_engine/evals may read data/ground_truth.yaml. `score` is pure over a store and a ground-truth dict, so tests use tiny fixtures.
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

import yaml

from .. import config, gateway, rank
from ..contracts import TABLES
from .common import f2
from .stats import kendall_tau

SIGNAL_KINDS = {"real", "contradictory", "shipped", "roadmap", "probe", "one_off"}
GT_PATH = config.ROOT / "data" / "ground_truth.yaml"
SPEC_DIRS = {42: config.ROOT / "generator" / "spec", 43: config.ROOT / "generator" / "spec" / "holdout"}
CLOSE_PAIR_RATIO = 1.10   # shortcut: adjacent oracle scores within 10% count as a designed close pair, upgrade if the generator exports them
SPLIT_SHARE = 0.25        # evals.md 4.2: split and over-merge thresholds
RECOVER_PURITY, RECOVER_SHARE = 0.6, 0.5   # evals.md 4.1

# metric -> (target, floor, comparison); None floor = reported only. Gates compare value against the floor.
FLOORS_42 = {
    "signal_recall": (0.95, 0.90, ">="), "noise_drop_rate": (0.75, 0.60, ">="), "bucket_accuracy": (0.85, 0.75, ">="),
    "quote_verification": (0.97, 0.93, ">="), "attribution": (1.0, 1.0, ">="), "themes_recovered": (6, "all", ">="),
    "mean_purity": (0.85, 0.75, ">="),
    "split_themes": (0, 1, "<="), "over_merges": (0, 1, "<="), "noise_in_top10": (0, 0, "<="), "citation_failures": (0, 0, "<="),
}
BOOLS_42 = ("tag_ok", "top_set", "probe_below_six")
FLOORS_43 = {"signal_recall": (0.85, 0.85, ">="), "quote_verification": (0.93, 0.93, ">="), "attribution": (1.0, 1.0, ">="),
             "themes_recovered": (3, 2, ">="), "mean_purity": (0.75, 0.75, ">="), "noise_in_top10": (0, 0, "<=")}


def load_gt(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


class Truth:
    """Index of a ground-truth file by raw record."""

    def __init__(self, gt):
        self.gt = gt
        self.themes = {t["id"]: t for t in gt["themes"]}
        self.keys = {k: str(v["hubspot_id"]) for k, v in gt.get("accounts", {}).items()}
        self.by_raw, self.noise = {}, {}
        for t in gt["themes"]:
            for m in t.get("mentions", []):
                self.by_raw.setdefault((m["source"], str(m["source_id"])), []).append((t, m))
        for n in gt.get("noise", []):
            self.noise.setdefault((n["source"], str(n["source_id"])), []).append(n)
        self.traps = {(j["source"], str(j["source_id"])): j.get("expected_account") for j in gt.get("join_traps", [])}

    def account_of(self, mention):
        return self.keys.get(mention["account"]) if mention.get("account") else None

    def label(self, raw, start, end):
        """(label, (theme, mention) or None) per evals.md 4.1 rule 1."""
        key, start, end = (raw["source"], raw["source_id"]), start or 0, end or start or 0
        hits = [(t, m) for t, m in self.by_raw.get(key, []) if start <= m["at_ms"] <= end]
        sig = [h for h in hits if h[0]["kind"] in SIGNAL_KINDS]
        if sig:
            return "signal:" + sig[0][0]["id"], sig[0]
        if hits:
            return "noise_theme:" + hits[0][0]["id"], hits[0]
        if any(start <= n["at_ms"] <= end for n in self.noise.get(key, [])):
            return "noise", None
        return "unlabelled", None


def latest_run_id(store):
    rows = store.db.execute("SELECT run_id FROM run ORDER BY rowid DESC LIMIT 1").fetchall()
    return rows[0][0] if rows else None


def theme_of(label):
    return label.split(":", 1)[1] if ":" in label else label


class Analysis:
    """Everything the metrics need, read once from the store: snippet labels, insight themes, opportunities, ranking."""

    def __init__(self, store, truth):
        self.store, self.truth = store, truth
        self.run_id = latest_run_id(store)
        raws = {r["raw_id"]: r for r in store.select("raw_record")}
        self.raws = raws
        tri = [t for t in store.select("triage") if self.run_id is None or t["run_id"] == self.run_id]
        self.triage = {t["snippet_id"]: t for t in tri}
        self.snip = {}
        for s in store.select("snippet"):
            lab, hit = truth.label(raws[s["raw_id"]], s["start_ms"], s["end_ms"])
            self.snip[s["snippet_id"]] = dict(s, label=lab, hit=hit, raw=raws[s["raw_id"]])
        self.ins = {}
        for i in store.select("insight"):
            sn = self.snip.get(i["snippet_id"])
            lab = sn["label"] if sn else "unlabelled"
            self.ins[i["insight_id"]] = dict(i, label=lab, theme=theme_of(lab) if lab.startswith(("signal", "noise_theme")) else lab,
                                             hit=sn["hit"] if sn else None, raw=sn["raw"] if sn else None)
        self.opps = {o["opportunity_id"]: o for o in store.select("opportunity") if o["merged_into"] is None}
        members = {}
        for link in store.select("opportunity_insight"):
            if link["opportunity_id"] in self.opps and link["insight_id"] in self.ins:
                members.setdefault(link["opportunity_id"], []).append(link["insight_id"])
        self.members = members
        self.label, self.purity = {}, {}
        for oid, ids in members.items():
            c = Counter(self.ins[i]["theme"] for i in ids)
            best = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            self.label[oid], self.purity[oid] = best[0], best[1] / len(ids)
        self.theme_total = Counter(i["theme"] for i in self.ins.values())
        scores = [s for s in store.select("score") if s["opportunity_id"] in self.opps and (self.run_id is None or s["run_id"] == self.run_id)]
        self.ranking = [s["opportunity_id"] for s in sorted(scores, key=lambda s: (-s["total"], s["opportunity_id"]))]
        self.total = {s["opportunity_id"]: s["total"] for s in scores}
        self.briefs = {b["opportunity_id"]: b for b in store.select("brief") if self.run_id is None or b["run_id"] == self.run_id}

    def theme_share(self, theme):
        """{opportunity_id: share of the theme's insights it holds}."""
        n = len(self.truth.themes.get(theme, {}).get("mentions") or []) or self.theme_total[theme] or 1  # planted mentions, not extracted ones
        out = {}
        for oid, ids in self.members.items():
            k = sum(1 for i in ids if self.ins[i]["theme"] == theme)
            if k:
                out[oid] = k / n
        return out

    def ranked_themes(self):
        seen = []
        for oid in self.ranking:
            t = self.label.get(oid)
            if t and t not in seen:
                seen.append(t)
        return seen


def _kind(truth, theme):
    return truth.themes.get(theme, {}).get("kind")


def _ratio(num, den):
    return num / den if den else None


def triage_metrics(a):
    sig = [(t, m) for t in a.truth.gt["themes"] if t["kind"] in SIGNAL_KINDS for m in t.get("mentions", [])]
    kept, bucket_ok, bucket_n = 0, 0, 0
    snip_of = {}
    for sid, s in a.snip.items():
        if s["label"].startswith("signal:") and s["hit"]:
            snip_of.setdefault(s["hit"][1]["id"], sid)
    for t, m in sig:
        sid = snip_of.get(m["id"])
        tr = a.triage.get(sid)
        if tr and tr["decision"] != "drop":
            kept += 1
            if tr["bucket"]:
                bucket_n += 1
                bucket_ok += tr["bucket"] == t["bucket"]
    noise = [sid for sid, s in a.snip.items() if s["label"].startswith("noise") and sid in a.triage]
    dropped = sum(a.triage[sid]["decision"] == "drop" for sid in noise)
    drops = [(sid, t) for sid, t in a.triage.items() if t["decision"] == "drop" and sid in a.snip]
    missed = [a.snip[sid]["label"].startswith("signal:") for sid, _ in drops]
    sample = [(a.snip[sid]["label"].startswith("signal:"), t["audit_weight"]) for sid, t in drops if t["audit_weight"]]
    w = sum(x for _, x in sample)
    est = sum(x for hit, x in sample if hit) / w if w else None
    return {"signal_recall": _ratio(kept, len(sig)), "noise_drop_rate": _ratio(dropped, len(noise)),
            "bucket_accuracy": _ratio(bucket_ok, bucket_n), "noise_audit_estimate": est,
            "noise_audit_exact": _ratio(sum(missed), len(missed)), "noise_audit_sampled": len(sample)}


def extract_metrics(a):
    ok = [i for i in a.ins.values() if i["quote_match"] != "failed"]
    right = total = 0
    for i in a.ins.values():
        if i["hit"]:
            total += 1
            right += i["account_id"] == a.truth.account_of(i["hit"][1])
    for key, expected in a.truth.traps.items():
        raws = [r for r in a.raws.values() if (r["source"], r["source_id"]) == key]
        for r in raws:
            total += 1
            right += r["account_id"] == (a.truth.keys.get(expected, expected) if expected else None)
    return {"quote_verification": _ratio(len(ok), len(a.ins)), "attribution": _ratio(right, total)}


def cluster_metrics(a):
    real = [t["id"] for t in a.truth.gt["themes"] if t["kind"] == "real"]
    recovered, split, over = [], 0, 0
    for th in real:
        shares = a.theme_share(th)
        if any(a.label[o] == th and a.purity[o] >= RECOVER_PURITY and s >= RECOVER_SHARE for o, s in shares.items()):
            recovered.append(th)
        split += sum(s >= SPLIT_SHARE for s in shares.values()) >= 2
    for oid, ids in a.members.items():
        held = {th for th in real if a.theme_share(th).get(oid, 0) >= SPLIT_SHARE}
        over += len(held) >= 2
    pur = [p for o, p in a.purity.items() if a.label[o] in real]
    return {"themes_recovered": len(recovered), "themes_total": len(real), "mean_purity": sum(pur) / len(pur) if pur else None,
            "split_themes": split, "over_merges": over}, recovered


def contradictory(a):
    """PASS one opportunity with both stances cited; WARN split by stance; FAIL a stance lost (evals.md 4.2)."""
    themes = [t for t in a.truth.gt["themes"] if t["kind"] == "contradictory"]
    if not themes:
        return None
    verdicts = []
    for t in themes:
        stance = {m["id"]: m.get("stance") for m in t["mentions"]}
        stances = set(s for s in stance.values() if s)
        held = {o: {stance[a.ins[i]["hit"][1]["id"]] for i in ids if a.ins[i]["theme"] == t["id"] and a.ins[i]["hit"]} - {None}
                for o, ids in a.members.items()}
        held = {o: s for o, s in held.items() if s}
        if set().union(*held.values()) != stances if held else True:
            verdicts.append("FAIL")
            continue
        big = [o for o, s in a.theme_share(t["id"]).items() if s >= SPLIT_SHARE]
        if len(big) != 1:
            verdicts.append("WARN")
            continue
        brief = a.briefs.get(big[0])
        cited = set(brief["citations_json"]) if brief else set()
        got = {stance[a.ins[i]["hit"][1]["id"]] for i in cited if i in a.ins and a.ins[i]["hit"] and a.ins[i]["theme"] == t["id"]}
        verdicts.append("PASS" if stances <= got else "FAIL")
    return "FAIL" if "FAIL" in verdicts else "WARN" if "WARN" in verdicts else "PASS"


def tag_metrics(a):
    """Shipped and roadmap themes tagged, hard negatives untagged, post-ship mentions flagged (evals.md 4.2 Tag)."""
    problems, post_ship_found, post_ship_n = [], 0, 0
    link = {(l["opportunity_id"], l["insight_id"]): l for l in a.store.select("opportunity_insight")}
    for t in a.truth.gt["themes"]:
        want = {"shipped": "shipped", "roadmap": "on_roadmap"}.get(t["kind"])
        shares = a.theme_share(t["id"])
        main = max(shares, key=shares.get) if shares else None
        if want:
            o = a.opps.get(main)
            if not o or o["tag"] != want:
                problems.append(f"{t['id']} not tagged {want}")
            if t["kind"] == "shipped":
                post = {m["id"] for m in t["mentions"] if m.get("post_ship")}
                post_ship_n += len(post)
                for oid, ids in a.members.items():
                    for i in ids:
                        hit = a.ins[i]["hit"]
                        if a.ins[i]["theme"] == t["id"] and hit:
                            flagged = bool(link[(oid, i)]["post_ship"])
                            if hit[1]["id"] in post:
                                post_ship_found += flagged
                            elif flagged:
                                problems.append(f"{t['id']} pre-ship mention flagged post-ship")
        elif t["kind"] == "real" and t.get("hard_negatives") and main and a.opps[main]["tag"] != "none":
            problems.append(f"{t['id']} hard negative tagged {a.opps[main]['tag']}")
    if post_ship_found < post_ship_n:
        problems.append(f"post-ship feedback {post_ship_found}/{post_ship_n}")
    return {"tag_ok": not problems, "post_ship_found": post_ship_found, "post_ship_total": post_ship_n}, problems


def oracle_order(a, ranking_cfg, as_of):
    """The same ranking code over the true inputs (evals.md 4.1 rule 4). Returns [(theme_id, total)] best first."""
    import statistics
    accounts = {x["account_id"]: x for x in a.store.select("account")}
    arrs = [x["arr_gbp"] for x in accounts.values() if x["arr_gbp"] is not None]
    median = statistics.median(arrs) if arrs else 0.0
    out = []
    for t in a.truth.gt["themes"]:
        if t["kind"] not in ("real", "contradictory", "probe", "roadmap", "shipped"):
            continue
        ms = [m for m in t["mentions"] if t["kind"] != "shipped" or m.get("post_ship")]
        if not ms:
            continue
        members = [{"severity": t["severity"], "account_id": a.truth.account_of(m), "route": m["route"],
                    "occurred_at": str(m["occurred_at"]), "day": rank.day(str(m["occurred_at"]))} for m in ms]
        tag = {"roadmap": "on_roadmap", "shipped": "shipped"}.get(t["kind"], "none")
        out.append((t["id"], rank.factors(members, accounts, ranking_cfg, as_of, median, tag)["total"]))
    return sorted(out, key=lambda x: (-x[1], x[0]))


def rank_metrics(a, ranking_cfg, as_of, top=6):
    real = {t["id"] for t in a.truth.gt["themes"] if t["kind"] == "real"}
    top_labels = [a.label[o] for o in a.ranking[:top]]
    oracle = oracle_order(a, ranking_cfg, as_of)
    pipe = a.ranked_themes()
    tau = kendall_tau([t for t, _ in oracle], pipe)
    probe = [t["id"] for t in a.truth.gt["themes"] if t["kind"] == "probe"]
    best_real = max((a.total[o] for o in a.ranking if a.label[o] in real), default=0)
    probe_totals = [a.total[o] for o in a.ranking if a.label[o] in probe]
    lowest_real = min((a.total[o] for o in a.ranking if a.label[o] in real), default=0)
    close = []
    realo = [(t, s) for t, s in oracle if t in real]
    for (t1, s1), (t2, s2) in zip(realo, realo[1:]):
        if s1 / s2 < CLOSE_PAIR_RATIO and t1 in pipe and t2 in pipe:
            close.append(f"{t1}>{t2}:{'kept' if pipe.index(t1) < pipe.index(t2) else 'swapped'}")
    noise_top = sum(1 for o in a.ranking[:10] if _kind(a.truth, a.label[o]) == "noise")
    return {"top_set": set(top_labels) == real if len(real) == top else None, "kendall_tau": tau, "noise_in_top10": noise_top,
            "probe_below_six": (not probe_totals or max(probe_totals) < lowest_real) if probe else None,
            "close_pairs": close, "top_labels": top_labels, "best_real": best_real}


def brief_metrics(a):
    briefs = list(a.briefs.values())
    judged = [j for j in a.store.select("judgement") if j["judge"] == "faithfulness" and (a.run_id is None or j["run_id"] == a.run_id)]
    return {"citation_failures": sum(b["check_status"] == "failed_checks" for b in briefs),
            "faithfulness_pass_rate": _ratio(sum(j["verdict"] == "pass" for j in judged), len(judged))}


# ---- deterministic summary (evals.md 3.5) ---------------------------------------------------------------------------

def deterministic(store, ranking_cfg, as_of, run_id=None):
    run_id = run_id or latest_run_id(store)
    out = {"schema": 0, "scores": 0, "lineage": 0, "reconciliation": 0, "accounts": 0, "vpc": 0}
    for table in ("triage", "insight", "opportunity", "opportunity_insight", "score", "brief", "judgement"):
        for row in store.select(table):
            try:
                TABLES[table].model_validate(row)
            except Exception:  # noqa: BLE001 - any validation error is one schema failure
                out["schema"] += 1
    ins = store.select("insight")
    out["quotes_ok"], out["quotes_n"] = sum(i["quote_match"] != "failed" for i in ins), len(ins)
    raws = {r["raw_id"]: r for r in store.select("raw_record")}
    snip_raw = {s["snippet_id"]: s["raw_id"] for s in store.select("snippet")}
    out["accounts"] = sum(1 for i in ins if i["snippet_id"] in snip_raw and i["account_id"] != raws[snip_raw[i["snippet_id"]]]["account_id"])
    out["citations"] = sum(b["check_status"] == "failed_checks" for b in store.select("brief"))
    out["scores"] = len(recompute_scores(store, ranking_cfg, as_of, run_id))
    calls = {c["call_id"]: c for c in store.select("model_call")}
    targets = {"triage": ("snippet_id", "snippet"), "insight": ("snippet_id", "snippet"), "brief": ("opportunity_id", "opportunity"),
               "judgement": ("target_id", None), "outtake": (None, None)}
    for table, (col, _) in targets.items():
        for row in store.select(table):
            call = calls.get(row.get("call_id"))
            if row.get("call_id") is None and table == "triage" and row.get("decision") == "untriaged":
                continue
            if call is None or (col and call["target_id"] != row[col]):
                out["lineage"] += 1
    tri = [t for t in store.select("triage") if run_id is None or t["run_id"] == run_id]
    if len(tri) != len(snip_raw) or any(t["decision"] not in ("keep", "drop", "low_confidence", "untriaged") for t in tri):
        out["reconciliation"] += 1
    out["audit_chain"] = store.verify_audit_chain()
    try:  # the append-only trigger must reject an UPDATE
        with store.lock:
            row = store.db.execute("SELECT event_id FROM audit_event LIMIT 1").fetchone()
            if row:
                store.db.execute("UPDATE audit_event SET actor='x' WHERE event_id=?", (row[0],))
                out["audit_chain"] = False
    except sqlite3.DatabaseError:
        pass
    finally:
        store.db.rollback()
    out["vpc"] = len(gateway.host_violations(config.load("models"), config.load("vpc_endpoints")))
    out["ok"] = (out["audit_chain"] and not any(out[k] for k in ("schema", "scores", "lineage", "reconciliation", "accounts", "citations", "vpc")))
    return out


def recompute_scores(store, ranking_cfg, as_of, run_id=None):
    """Opportunity ids whose stored score differs from the formula over stored members (evals.md 3.5), tolerance 1e-9."""
    import statistics
    accounts = {x["account_id"]: x for x in store.select("account")}
    arrs = [x["arr_gbp"] for x in accounts.values() if x["arr_gbp"] is not None]
    median = statistics.median(arrs) if arrs else 0.0
    ins = {i["insight_id"]: i for i in store.select("insight")}
    snip = {s["snippet_id"]: s["raw_id"] for s in store.select("snippet")}
    raws = {r["raw_id"]: r for r in store.select("raw_record")}
    opps = {o["opportunity_id"]: o for o in store.select("opportunity")}
    links = {}
    for link in store.select("opportunity_insight"):
        links.setdefault(link["opportunity_id"], []).append(link)
    bad = []
    for s in store.select("score"):
        if run_id and s["run_id"] != run_id:
            continue
        o = opps[s["opportunity_id"]]
        tag = "none" if o["tag_state"] == "removed" else o["tag"]
        members = []
        for link in links.get(s["opportunity_id"], []):
            if tag == "shipped" and not link["post_ship"]:
                continue
            i = ins[link["insight_id"]]
            raw = raws[snip[i["snippet_id"]]]
            members.append({"severity": i["severity"], "account_id": i["account_id"], "route": raw["route"],
                            "occurred_at": raw["occurred_at"], "day": rank.day(raw["occurred_at"])})
        f = rank.factors(members, accounts, ranking_cfg, as_of, median, tag) if members else None
        if f is None or abs(f["total"] - s["total"]) > 1e-9 or abs(rank.total_of(s) - s["total"]) > 1e-9:
            bad.append(s["opportunity_id"])
    return bad


# ---- leak check ---------------------------------------------------------------------------------------------------

def leak_check(seeds=(42,), root=None):
    """Count exposed files containing a theme id, title or fact phrase (synonyms too in prompts and config). Mirrors tests/test_leaks.py."""
    root = Path(root or config.ROOT)
    hits = []
    for folder in ("data/raw", "data/holdout/raw", "generator/prompts", "config", "prompts"):
        terms = []
        for seed in seeds:
            spec = SPEC_DIRS[seed] / "themes.yaml"
            if not spec.is_file():
                continue
            lines = [ln for ln in spec.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
            for t in json.loads("\n".join(lines))["themes"]:
                terms += [t["id"], t["title"], *t["facts"]] + (list(t["synonyms"]) if folder != "data/raw" and folder != "data/holdout/raw" else [])
        base = root / folder
        for p in (sorted(base.rglob("*")) if base.is_dir() else []):
            if p.is_file():
                text = p.read_text(encoding="utf-8", errors="replace").casefold()
                if any(term and term.casefold() in text for term in terms):
                    hits.append(p.relative_to(root).as_posix())
    return hits


# ---- the suite ----------------------------------------------------------------------------------------------------

def score(store, gt, as_of, ranking_cfg=None, floors=None, bools=(), top=6):
    """-> (metrics, detail, gates). floors: {metric: (target, floor, op)}, floor "all" meaning every theme; bools: metric names that must be True."""
    ranking_cfg = ranking_cfg or config.load("ranking")
    a = Analysis(store, Truth(gt))
    m, recovered = cluster_metrics(a)
    m.update(triage_metrics(a), **extract_metrics(a))
    r = rank_metrics(a, ranking_cfg, as_of, top)
    tag, tag_problems = tag_metrics(a) if any(t["kind"] in ("shipped", "roadmap") for t in gt["themes"]) else ({}, [])
    m.update(tag, **brief_metrics(a))
    m.update({"top_set" if top == 6 else "top3_set": r["top_set"]}, kendall_tau=r["kendall_tau"], noise_in_top10=r["noise_in_top10"],
             probe_below_six=r["probe_below_six"])
    contra, det = contradictory(a), deterministic(store, ranking_cfg, as_of, a.run_id)
    gates = {}
    for k, (_, floor, op) in (floors or {}).items():
        v = m.get(k)
        if v is not None:
            floor = m["themes_total"] if floor == "all" else floor
            gates[k] = v >= floor if op == ">=" else v <= floor
    for k in bools:
        if m.get(k) is not None:
            gates[k] = bool(m[k])
    if contra is not None:
        gates["contradictory"] = contra != "FAIL"
    gates["deterministic"] = det["ok"]
    detail = {"contradictory": contra, "close_pairs": r["close_pairs"], "tag_problems": tag_problems, "top_labels": r["top_labels"],
              "recovered": recovered, "deterministic": det, "noise_audit_sampled": m.pop("noise_audit_sampled")}
    return m, detail, gates


# ---- suite runner and report (evals.md 9) --------------------------------------------------------------------------

def evaluate_seed(a, seed):
    """Replay `seed` (or open --db), score it. Returns (store, run report dict, metrics, detail, gates, leaks) or an error string."""
    from datetime import datetime
    from ..store import Store
    from . import common
    gt_path = GT_PATH if seed == 42 else config.ROOT / "data" / "holdout" / "ground_truth.yaml"
    if not gt_path.is_file():
        return f"ground truth missing: {gt_path.as_posix()} (run: keelwater generate --seed {seed})"
    if a.db and seed == 42:  # --db scores an existing store; seed 43 always replays
        store, report = Store(a.db), {}
    else:
        rc, out, report = common.replay(a, seed=seed)
        if rc != 0:
            return f"replay failed (exit {rc}):\n{out}"
        store = Store(Path(a.scratch) / f"seed{seed}-all.sqlite")
    as_of = datetime.strptime(a.as_of, "%d/%m/%Y").date()
    floors, bools, top = (FLOORS_42, BOOLS_42, 6) if seed == 42 else (FLOORS_43, (), 3)
    m, detail, gates = score(store, load_gt(gt_path), as_of, floors=floors, bools=bools, top=top)
    leaks = leak_check((42,) if seed == 42 else (42, 43))
    gates["leak_check"] = not leaks
    detail["leaks"] = leaks
    return store, report, m, detail, gates


def lines(seed, run_id, report, m, d, g):
    det = d["deterministic"]
    f = f2
    top = "top-6" if seed == 42 else "top-3"
    tp = m.get("top_set", m.get("top3_set"))
    yn = lambda v: "n/a" if v is None else "yes" if v else "no"  # noqa: E731
    man = report.get("manifest", {})
    out = [f"run {run_id}  profile={man.get('profile', 'replay')}  seed={seed}  as_of={man.get('as_of', '')}  data=sha256:{str(man.get('data_hash', ''))[:12]}",
           f"leak check     {'PASS' if g['leak_check'] else 'FAIL'}  {len(d['leaks'])} theme ids or fact phrases in data/raw, prompts/ or config/",
           f"deterministic  {'PASS' if det['ok'] else 'FAIL'}  schema {det['schema']} | quotes {det['quotes_ok']}/{det['quotes_n']} | citations {det['citations']} "
           f"| accounts {det['accounts']} | scores {det['scores']} | lineage {det['lineage']} | reconciliation {det['reconciliation']} "
           f"| audit chain {'ok' if det['audit_chain'] else 'BROKEN'}",
           f"triage   recall {f(m['signal_recall'])} | noise-drop {f(m['noise_drop_rate'])} | bucket {f(m['bucket_accuracy'])} "
           f"| audit est {f(m['noise_audit_estimate'])} vs exact {f(m['noise_audit_exact'])} ({d['noise_audit_sampled']} sampled)",
           f"cluster  recovered {m['themes_recovered']}/{m['themes_total']} | purity {f(m['mean_purity'])} | split {m['split_themes']} "
           f"| over-merged {m['over_merges']} | contradictory {d['contradictory'] or 'n/a'}"]
    if "tag_ok" in m:
        out.append(f"tag      {'ok' if m['tag_ok'] else 'PROBLEM'} | post-ship {m['post_ship_found']}/{m['post_ship_total']}"
                   + (" | " + "; ".join(d["tag_problems"]) if d["tag_problems"] else ""))
    out.append(f"rank     {top} set {yn(tp)} | probe below six {yn(m['probe_below_six'])} | noise in top 10 {m['noise_in_top10']} | tau {f(m['kendall_tau'])} (reported)"
               + (f" | close pairs {', '.join(d['close_pairs'])}" if d["close_pairs"] else ""))
    out.append(f"brief    citation failures {m['citation_failures']} | faithfulness pass rate {f(m['faithfulness_pass_rate'])} (reported)")
    return out


def run_suite(a):
    """eval --suite ground-truth. Returns (passed, printed lines, report path or None)."""
    from ..contracts import GroundTruthReport
    from . import common
    got = evaluate_seed(a, 42)
    if isinstance(got, str):
        return False, [got], None
    store, report, m, d, g = got
    run_id = report.get("run_id") or latest_run_id(store) or "unknown"
    common.store_drift(store)
    passed = all(g.values())
    rep = GroundTruthReport(run_id=run_id, seed=42, passed=passed, metrics={k: v for k, v in m.items() if not isinstance(v, (list, dict))},
                            gates=g, cache_keys=report.get("manifest", {}).get("cache_keys", []), detail=d)
    path = common.write_report(a.report_dir, rep)
    out = lines(42, run_id, report, m, d, g) + metric_table(m, FLOORS_42)
    out.append(f"overall  {'PASS' if passed else 'FAIL'}   report: {path.as_posix()}" + ("" if passed else "   failing: " + ", ".join(k for k, v in g.items() if not v)))
    store.close()
    return passed, out, path


def metric_table(m, floors):
    rows = [f"{'metric':<22}{'target':>8}{'floor':>8}{'result':>9}"]
    for k, (target, floor, op) in floors.items():
        v = m.get(k)
        rows.append(f"{k:<22}{str(target):>8}{('all' if floor == 'all' else str(floor)):>8}{(f2(v) if isinstance(v, float) else str(v)):>9}")
    return rows
