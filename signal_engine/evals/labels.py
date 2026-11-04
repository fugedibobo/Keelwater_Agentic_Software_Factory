"""Labels: import human jsonl, re-apply human actions in a fresh store, seed and export (docs/evals.md 5.4, 5.5, 7; architecture 11).

`import_human` and `apply` are pipeline entry points (signal_engine/pipeline.py HOOKS and the review stage): fn(ctx).
# shortcut: in a fresh-store run, rank and brief still see an opportunity a PM rejected earlier; production keeps one store
"""

import argparse
import json
import re
from pathlib import Path

from .. import config
from ..contracts import Annotation, Label
from ..store import content_id, now_iso, reassign, transition

HUMAN_DIR = config.ROOT / "labels" / "human"
SEED_DIR = config.ROOT / "labels" / "seed"
EXPORT_DIR = config.ROOT / "reports" / "labels"
ANN_FIELDS = tuple(Annotation.model_fields)
LABEL_FIELDS = tuple(Label.model_fields)
# phase -> actions re-applied there (review = the pipeline's review stage)
PHASES = {"after_cluster": {"merge"}, "after_tag": {"confirm_tag", "remove_tag"},
          "review": {"accept", "reject", "park", "reassign", "edit"}}
TO_STATUS = {"accept": "accepted", "reject": "rejected", "park": "parked"}


def read_records(path):
    """(records, bad_line_count, file_count) from one jsonl file or every *.jsonl in a folder."""
    path = Path(path)
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path] if path.is_file() else []
    records, bad = [], 0
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    raise ValueError
            except ValueError:
                bad += 1
                continue
            records.append((f, rec))
    return records, bad, len(files)


def _target_exists(store, target_type, target_id):
    table, col = {"opportunity": ("opportunity", "opportunity_id"), "brief": ("brief", "brief_id"), "noise_audit": ("triage", "snippet_id"),
                  "outtake": ("outtake", "outtake_id")}.get(target_type, (None, None))
    return True if table is None else bool(store.select(table, {col: target_id}))


def import_path(store, path):
    """Load annotation and label rows from jsonl; rows already present are skipped; missing targets are kept and counted."""
    records, bad, n_files = read_records(path)
    undone_events = {r["undo_of"] for _, r in records if r.get("kind") == "undo"}
    dropped_labels = {i for _, r in records if r.get("kind") == "undo" for i in r.get("label_ids", [])}
    by_event = {r["audit_event_id"]: r for _, r in records if r.get("kind") == "annotation" and r.get("audit_event_id")}
    counts = dict(annotations=0, labels=0, undos=0, missing_targets=0, bad_lines=bad, files=n_files)
    for f, r in records:
        kind = r.get("kind") or ("label" if "judge" in r and "verdict" in r else None)
        try:
            if kind == "annotation":
                row = Annotation.model_validate({k: r[k] for k in ANN_FIELDS if k in r})
                existing = store.select("annotation", {"annotation_id": row.annotation_id})
                edit = {k: r[k] for k in ("title", "problem_statement") if k in r}
                source = r.get("audit_event_id")
            elif kind == "undo":
                orig = by_event.get(r["undo_of"], {})
                row = Annotation(annotation_id=content_id("undo", r["undo_of"]), target_type=orig.get("target_type", "opportunity"),
                                 target_id=orig.get("target_id", ""), actor=r.get("actor") or f.stem, action="undo", undo_of=r["undo_of"],
                                 created_at=r.get("created_at") or orig.get("created_at") or now_iso())
                existing, edit, source = store.select("annotation", {"annotation_id": row.annotation_id}), {}, r.get("audit_event_id")
            elif kind == "label":
                if r.get("label_id") in dropped_labels:
                    continue  # an undo removed it
                row = Label.model_validate({k: r[k] for k in LABEL_FIELDS if k in r})
                if not store.select("label", {"label_id": row.label_id}):
                    store.insert("label", row)
                    counts["labels"] += 1
                    counts["missing_targets"] += not _target_exists(store, row.target_type, row.target_id)
                continue
            else:
                counts["bad_lines"] += 1
                continue
        except (ValueError, KeyError):
            counts["bad_lines"] += 1
            continue
        if existing:
            continue
        store.insert("annotation", row)
        store.append_audit("system", "system", "annotation.import", "annotation", row.annotation_id,
                           {"annotation_id": row.annotation_id, "source_event": source, "file": f.name, **({"edit": edit} if edit else {})})
        counts["undos" if kind == "undo" else "annotations"] += 1
        counts["missing_targets"] += kind == "annotation" and not _target_exists(store, row.target_type, row.target_id)
    if any(counts[k] for k in ("annotations", "labels", "undos")):
        store.append_audit("system", "system", "labels.import", "labels", str(path), counts)
    return counts


def import_human(ctx):
    """Run-start hook: load labels/human/*.jsonl."""
    c = import_path(ctx.store, HUMAN_DIR)
    if any(c[k] for k in ("annotations", "labels", "undos", "bad_lines")):
        print(f"labels: imported {c['annotations']} annotations, {c['labels']} labels, {c['undos']} undos; "
              f"{c['missing_targets']} missing targets kept; {c['bad_lines']} bad lines")
    return c


def _audit_maps(store):
    """(annotation ids already applied, {source audit event id: annotation id}) from the audit log."""
    applied, source = set(), {}
    with store.lock:
        rows = store.db.execute("SELECT action, details_json FROM audit_event WHERE details_json LIKE '%annotation_id%' ORDER BY rowid").fetchall()
    for action, details in rows:
        d = json.loads(details)
        if action == "annotation.import":
            if d.get("source_event"):
                source[d["source_event"]] = d["annotation_id"]
        elif d.get("annotation_id"):
            applied.add(d["annotation_id"])
    return applied, source


def apply(ctx_or_store, phase=None):
    """Re-apply human actions of this phase with their original actor and time; an undo cancels its action first.

    Called as fn(ctx) by the pipeline (phase = ctx.stage) or as apply(store, phase). Returns counts.
    """
    store = getattr(ctx_or_store, "store", ctx_or_store)
    phase = phase or getattr(ctx_or_store, "stage", "")
    actions = PHASES.get(phase)
    if not actions:
        return None
    applied, source = _audit_maps(store)
    anns = store.select("annotation", order_by="created_at, rowid")
    cancelled = {source[a["undo_of"]] for a in anns if a["action"] == "undo" and a["undo_of"] in source}
    counts = {"applied": 0, "cancelled": 0, "missing": 0, "skipped": 0}
    imported = {r["details_json"]["annotation_id"]: r["details_json"] for r in store.select("audit_event") if r["action"] == "annotation.import"} if "edit" in actions else {}
    for a in anns:
        if a["action"] not in actions or a["target_type"] != "opportunity" or a["annotation_id"] in applied:
            continue
        if a["annotation_id"] in cancelled:
            counts["cancelled"] += 1
            continue
        opp = (store.select("opportunity", {"opportunity_id": a["target_id"]}) or [None])[0]
        if opp is None:
            counts["missing"] += 1
            continue
        counts["applied" if _apply_one(store, a, opp, imported) else "skipped"] += 1
    if counts["applied"] or counts["missing"]:
        print(f"labels: {phase} applied {counts['applied']}, cancelled {counts['cancelled']}, target missing {counts['missing']}, skipped {counts['skipped']}")
    return counts


def _apply_one(store, a, opp, imported):
    oid, at, actor, act = opp["opportunity_id"], a["created_at"], a["actor"], a["action"]
    details = {"annotation_id": a["annotation_id"], "action": act, "reason_code": a["reason_code"], "note": a["note"]}
    try:
        if act == "merge":
            m = re.search(r"merged into (\w+)", a["note"] or "")
            if not m or not store.select("opportunity", {"opportunity_id": m.group(1)}) or opp["status"] not in ("new", "proposed"):
                return False
            if opp["status"] == "new":  # the status machine has no new -> merged, so the system proposes it first
                transition(store, oid, "proposed", "labels", "system", {"annotation_id": a["annotation_id"], "reason": "merge replay"}, at=at)
            store.update("opportunity", {"opportunity_id": oid}, {"merged_into": m.group(1)})
            transition(store, oid, "merged", actor, "person", {**details, "merged_into": m.group(1)}, at=at)
        elif act in ("confirm_tag", "remove_tag"):
            if opp["tag"] == "none" or opp["tag_state"] != "proposed":
                return False
            state = "confirmed" if act == "confirm_tag" else "removed"
            store.update("opportunity", {"opportunity_id": oid}, {"tag_state": state})
            store.append_audit(actor, "person", f"opportunity.{act}", "opportunity", oid,
                               {**details, "restore": {"table": "opportunity", "key_col": "opportunity_id", "key": oid,
                                                       "before": {"tag_state": "proposed"}, "after": {"tag_state": state}}}, at=at)
        elif act in TO_STATUS:
            if opp["status"] != "proposed":
                return False
            transition(store, oid, TO_STATUS[act], actor, "person", details, at=at)
        elif act == "reassign":
            m = re.search(r"to (\w+)", a["note"] or "")
            if not m or m.group(1) not in config.squads():
                return False
            reassign(store, oid, m.group(1), actor, "person", details, at=at)
        elif act == "edit":
            edit = imported.get(a["annotation_id"], {}).get("edit")
            if not edit:  # shortcut: the board's jsonl carries no edited text, so only records with title and problem_statement re-apply
                return False
            store.update("opportunity", {"opportunity_id": oid}, edit)
            store.append_audit(actor, "person", "opportunity.edit", "opportunity", oid, {**details, "edit": edit}, at=at)
        else:
            return False
    except (ValueError, PermissionError):
        return False
    return True


# ---- seed, import, export commands --------------------------------------------------------------------------------

def load_seed_files(seed_dir=SEED_DIR):
    """{judge: [record]} from labels/seed/<judge>.jsonl (records carry their judge evidence)."""
    out = {}
    for f in sorted(Path(seed_dir).glob("*.jsonl")) if Path(seed_dir).is_dir() else []:
        out[f.stem] = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return out


def export(store, judge=None, out_dir=EXPORT_DIR, seed_dir=SEED_DIR):
    """One JSONL dataset per judge under out_dir: seed items (with evidence) and store labels (with the judge's verdict when judged)."""
    from .common import judged_verdicts
    judged = judged_verdicts(store) if store else {}
    seeds = load_seed_files(seed_dir)
    names = [judge] if judge else ["faithfulness", "signal", "duplicate"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for j in names:
        rows = [dict(r, dataset="seed") for r in seeds.get(j, [])]
        for l in (store.select("label", {"judge": j}) if store else []):
            rows.append(dict(l, dataset="store", judge_verdict=judged.get((l["target_id"], j))))
        path = out_dir / f"{j}.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows), encoding="utf-8", newline="\n")
        paths.append((path, len(rows)))
    return paths


def main(argv):
    ap = argparse.ArgumentParser(prog="keelwater labels", description="seed, import and export labels")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="build labels/seed/<judge>.jsonl from ground truth and a finished run")
    s.add_argument("--n", type=int, default=60, help="items per judge, half pass and half fail")
    s.add_argument("--profile", choices=["replay", "demo"], default="replay")
    s.add_argument("--db", default=".local/keelwater.sqlite", help="store of a finished run on data/raw")
    s.add_argument("--cache-dir", default="fixtures/llm_cache")
    s.add_argument("--max-usd", type=float, default=1.75)
    s.add_argument("--out", default=str(SEED_DIR))
    s.add_argument("--scratch", default=".scratch/labels")
    i = sub.add_parser("import", help="load label and annotation jsonl into the store")
    i.add_argument("path")
    i.add_argument("--db", default=".local/keelwater.sqlite")
    e = sub.add_parser("export", help="write one JSONL dataset per judge under reports/labels/")
    e.add_argument("--judge", choices=["faithfulness", "signal", "duplicate"])
    e.add_argument("--phoenix", action="store_true")
    e.add_argument("--db", default=".local/keelwater.sqlite")
    e.add_argument("--out", default=str(EXPORT_DIR))
    a = ap.parse_args(argv)
    from ..store import Store
    if a.cmd == "seed":
        from . import seeds
        return seeds.main(a)
    if a.cmd == "export" and a.phoenix:
        from .. import telemetry
        from . import ground_truth
        store = Store(a.db).init() if Path(a.db).is_file() else None
        telemetry.export_datasets(store, seed_dir=SEED_DIR, truth=ground_truth.load_gt(ground_truth.GT_PATH))
        return 0
    if a.cmd == "import":
        if not Path(a.path).exists():
            print(f"no such file or folder: {a.path}")
            return 2
        store = Store(a.db).init()
        c = import_path(store, a.path)
        print(f"imported {c['annotations']} annotations, {c['labels']} labels, {c['undos']} undos from {c['files']} files; "
              f"{c['missing_targets']} missing targets kept; {c['bad_lines']} bad lines")
        store.close()
        return 0
    store = Store(a.db).init() if Path(a.db).is_file() else None
    for path, n in export(store, a.judge, a.out):
        print(f"{path.as_posix()}: {n} rows")
    return 0
