"""Suite 4: judge TPR and TNR per origin and split, and judge-version qualification (docs/evals.md 5.5 to 5.7, 8.1)."""

from pathlib import Path

from .. import judges
from ..brief import render
from ..contracts import JudgesReport
from ..gateway import Gateway, GatewayError
from ..prompts import load_prompt
from ..store import Store, now_iso
from . import common, labels
from .common import JUDGES, agreement, f2

MIN_LABELS, MIN_LOWER, MIN_UPPER = 50, 0.75, 0.75
ORIGINS = ("synthetic_seed", "live_reviewer", "real_pm")


def qualify_state(items, current="uncalibrated"):
    """Decide a judge version's state from its blind held_out real_pm labels.

    items: (human verdict, judge verdict, weight, created_at). Trusted needs MIN_LABELS per class and both Wilson lower
    bounds >= MIN_LOWER. A trusted version is revoked when, on the latest MIN_LABELS per class, either upper bound is < MIN_UPPER.
    Returns (state, stats dict).
    """
    items = sorted(items, key=lambda x: x[3])
    r = agreement([x[:3] for x in items])
    enough = r["n_pass"] >= MIN_LABELS and r["n_fail"] >= MIN_LABELS
    if enough and r["tpr_lo"] >= MIN_LOWER and r["tnr_lo"] >= MIN_LOWER:
        return "trusted", r
    if current == "trusted" and enough:
        latest = [x for v in ("pass", "fail") for x in [y for y in items if y[0] == v][-MIN_LABELS:]]
        last = agreement([x[:3] for x in latest])
        if last["tpr_hi"] < MIN_UPPER or last["tnr_hi"] < MIN_UPPER:
            return "revoked", r
        return "trusted", r
    if current == "trusted":  # fewer than MIN_LABELS per class cannot test the bound; trust stays until evidence says otherwise
        return "trusted", r
    return ("revoked" if current == "revoked" else "calibrating"), r


def version_id(gw, judge):
    pv = load_prompt("judge", judge)[1]
    return f"{pv}+{gw.model_ids()['judge']}"


def judged_by_version(store, jv_ids):
    return {(j["target_id"], j["judge"]): j["verdict"] for j in store.select("judgement") if j["judge_version_id"] in jv_ids}


def candidates(store, label):
    """Judgement targets a label can match: itself, a brief's opportunity, an opportunity's brief."""
    ids = [label["target_id"]]
    if label["target_type"] == "brief":
        ids += [b["opportunity_id"] for b in store.select("brief", {"brief_id": label["target_id"]})]
    elif label["target_type"] == "opportunity":
        ids += [b["brief_id"] for b in store.select("brief", {"opportunity_id": label["target_id"]})]
    return ids


def seed_verdicts(gw, seeds):
    """{(judge, target_id): verdict or None} by running each judge over its stored evidence (cached in replay).

    Items with identical evidence share one call, so concurrent threads never race on one cache file.
    """
    jobs = {}
    for j, rows in seeds.items():
        for r in rows:
            if j in JUDGES:
                body, pv = load_prompt("judge", j)
                jobs.setdefault((j, render(body, evidence=r["evidence"])), (pv, r["target_id"]))

    def one(item):
        (judge, prompt), (pv, target) = item
        try:
            return gw.chat("judge", [{"role": "user", "content": prompt}], target_type="seed", target_id=target, prompt_version=pv,
                           schema=judges.SCHEMA)["verdict"]
        except GatewayError:
            return None
    got = dict(zip(jobs, gw.map(one, list(jobs.items()))))
    return {(j, r["target_id"]): got[(j, render(load_prompt("judge", j)[0], evidence=r["evidence"]))]
            for j, rows in seeds.items() if j in JUDGES for r in rows}


def collect(store, gw, seeds):
    """Every judged label as a dict, plus the number of labels and seed items with no verdict."""
    jv = {j: version_id(gw, j) for j in JUDGES}
    judged = judged_by_version(store, set(jv.values()))
    verdicts = seed_verdicts(gw, seeds)
    items, unjudged = [], 0
    for j, rows in seeds.items():
        for r in rows:
            v = verdicts.get((j, r["target_id"]))
            if v is None:
                unjudged += 1
                continue
            items.append(dict(judge=j, origin=r["origin"], split=r["split"], blind=bool(r["blind"]), weight=r["weight"], human=r["verdict"],
                              judge_verdict=v, created_at=r["created_at"]))
    for l in store.select("label"):
        if l["target_type"] == "noise_audit":
            continue
        v = next((judged[(t, l["judge"])] for t in candidates(store, l) if (t, l["judge"]) in judged), None)
        if v is None:
            unjudged += 1
            continue
        items.append(dict(judge=l["judge"], origin=l["origin"], split=l["split"], blind=bool(l["blind"]), weight=l["weight"], human=l["verdict"],
                          judge_verdict=v, created_at=l["created_at"]))
    return items, unjudged, jv


def rows_for(items, jv, states):
    out = []
    for j in JUDGES:
        for origin in ORIGINS:
            mine = [i for i in items if i["judge"] == j and i["origin"] == origin]
            if not mine and origin != "real_pm":
                continue
            row = {"judge": j, "origin": origin, "version": jv[j], "state": states.get(jv[j], "uncalibrated")}
            for split in ("dev", "held_out"):
                part = [(i["human"], i["judge_verdict"], i["weight"]) for i in mine if i["split"] == split]
                row[split] = dict(agreement(part), labels=len(part))
            blind = [i for i in mine if i["blind"] and i["split"] == "held_out"]
            row["blind_pass"] = sum(i["human"] == "pass" for i in blind)
            row["blind_fail"] = sum(i["human"] == "fail" for i in blind)
            out.append(row)
    return out


def _ci(r, k):
    return "-" if r[k] is None else f"{r[k]:.2f} ({f2(r[k + '_lo'])}-{f2(r[k + '_hi'])})"


def table(rows):
    out = [f"{'judge':<13}{'origin':<16}{'labels dev/held':>16}{'dev TPR':>9}{'dev TNR':>9}  {'held-out TPR (95% CI)':<22}{'held-out TNR (95% CI)':<22}state"]
    for r in rows:
        d, h = r["dev"], r["held_out"]
        if r["origin"] == "real_pm":
            state = f"{r['state']}: {min(r['blind_pass'], r['blind_fail'])} of {MIN_LABELS} per class" if r["state"] in ("uncalibrated", "calibrating") else r["state"]
        else:
            state = "(never certifies)"
        out.append(f"{r['judge']:<13}{r['origin']:<16}{str(d['labels']) + '/' + str(h['labels']):>16}{f2(d['tpr']):>9}{f2(d['tnr']):>9}  "
                   f"{_ci(h, 'tpr'):<22}{_ci(h, 'tnr'):<22}{state}")
    return out


def apply_qualify(store, items, jv):
    """Store each current judge version's state from blind held_out real_pm labels; every change is an audit event."""
    changes = []
    for j in JUDGES:
        mine = [(i["human"], i["judge_verdict"], i["weight"], i["created_at"]) for i in items
                if i["judge"] == j and i["origin"] == "real_pm" and i["blind"] and i["split"] == "held_out"]
        rows = store.select("judge_version", {"judge_version_id": jv[j]})
        if not rows:
            pv, model = jv[j].split("+", 1)
            store.insert("judge_version", {"judge_version_id": jv[j], "judge": j, "prompt_version": pv, "model": model, "state": "uncalibrated"})
            rows = store.select("judge_version", {"judge_version_id": jv[j]})
        old = rows[0]["state"]
        state, r = qualify_state(mine, old)
        values = {"state": state, "n_pass": r["n_pass"], "n_fail": r["n_fail"], "tpr": r["tpr"], "tnr": r["tnr"],
                  "tpr_lower": r["tpr_lo"], "tnr_lower": r["tnr_lo"]}
        if state != old:
            values["state_changed_at"] = now_iso()
            store.append_audit("system", "system", "judge.state", "judge_version", jv[j],
                               {"from": old, "to": state, **{k: values[k] for k in ("n_pass", "n_fail", "tpr", "tnr", "tpr_lower", "tnr_lower")}})
            changes.append((j, old, state))
        store.update("judge_version", {"judge_version_id": jv[j]}, values)
    return changes


def run_suite(a):
    scratch = Path(a.scratch)
    report = {}
    if a.qualify or a.db:
        db = a.db or ".local/keelwater.sqlite"
        if not Path(db).is_file():
            return False, [f"no store at {db}: run keelwater run first, or drop --qualify for a scratch replay"], None
        store = Store(db).init()
    else:
        rc, out, report = common.replay(a)
        if rc != 0:
            return False, [f"replay failed (exit {rc}):\n{out}"], None
        store = Store(scratch / "seed42-all.sqlite")
    labels.import_path(store, labels.HUMAN_DIR)
    run_id = report.get("run_id") or (store.db.execute("SELECT run_id FROM run ORDER BY rowid DESC LIMIT 1").fetchone() or ["unknown"])[0]
    gw = Gateway(store, a.profile, a.cache_dir, run_id, a.max_usd)
    items, unjudged, jv = collect(store, gw, labels.load_seed_files(Path(a.seeds)))
    changes = apply_qualify(store, items, jv) if a.qualify else []
    states = {v["judge_version_id"]: v["state"] for v in store.select("judge_version")}
    rows = rows_for(items, jv, states)
    drift = common.store_drift(store)
    gates = {"all_items_judged": unjudged == 0, "no_unearned_trust": not any(
        states.get(jv[j]) == "trusted" and not any(i["judge"] == j and i["origin"] == "real_pm" and i["blind"] for i in items) for j in JUDGES)}
    metrics = {f"{r['judge']}.{r['origin']}.{s}_{k}": r[s][k] for r in rows for s in ("dev", "held_out") for k in ("tpr", "tnr", "labels")}
    rep = JudgesReport(run_id=run_id, passed=all(gates.values()), metrics=metrics, gates=gates, cache_keys=sorted(set(report.get("manifest", {}).get("cache_keys", [])) | gw.used_keys),
                       detail={"rows": rows, "drift": drift, "unjudged": unjudged, "qualified": a.qualify, "state_changes": changes})
    path = common.write_report(a.report_dir, rep)
    out = [f"run {run_id}  judges {', '.join(jv.values())}", *table(rows)]
    out += [f"state change: {j} {o} -> {n}" for j, o, n in changes]
    out.append(f"{unjudged} labels or seed items had no judge verdict" if unjudged else "every label and seed item has a judge verdict")
    d = drift["label_panel_agreement"]
    out.append("drift    agreement " + " | ".join(f"{j} TPR {f2(d[j]['tpr'])} TNR {f2(d[j]['tnr'])}" for j in JUDGES)
               + f" | noise-audit miss {f2(drift['noise_audit_miss_rate'])} | PM acceptance {f2(drift['pm_acceptance_rate'])}")
    out.append(f"overall  {'PASS' if rep.passed else 'FAIL'}   report: {path.as_posix()}")
    store.close()
    return rep.passed, out, path
