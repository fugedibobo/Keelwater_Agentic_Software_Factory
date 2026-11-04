"""Stage 11: shipped story -> release note, help article and change notice; latest customer call -> follow-up brief. Drafts only."""

from datetime import date

from .brief import chat_with_id, render
from .contracts import Outtake
from .gateway import ReplayMiss
from .prompts import load_prompt
from .store import content_id

KINDS = ("release_note", "help_article", "change_notice")
STAFF_DOMAIN = "@keelwater.example"


def shipped_stories(ctx):
    """Completed feature stories in the data window (completed on or before as_of), in id order."""
    out = []
    for r in ctx.store.select("raw_record", {"source": "shortcut"}, order_by="source_id"):
        s = r["payload_json"]
        if isinstance(s, dict) and s.get("story_type") == "feature" and s.get("completed") and s.get("completed_at") \
                and date.fromisoformat(s["completed_at"][:10]) <= ctx.as_of:
            out.append(s)
    return sorted(out, key=lambda s: s["id"])


def draft_one(ctx, kind, story_ref, target_type, **parts):
    body, pv = load_prompt("outtake", kind)
    try:
        out, call_id = chat_with_id(ctx.gateway, "outtake", render(body, **parts), target_type, story_ref, pv)
    except ReplayMiss:  # replay with no recorded answer: no draft, a later run retries
        print(f"outtake: replay miss for {story_ref} {kind}, skipped")
        return
    ctx.store.insert("outtake", Outtake(outtake_id=content_id("outtake", story_ref, kind), story_ref=story_ref, call_id=call_id,
                                        kind=kind, body_md=out["body_md"], status="draft"))


def problem_for(store, story):
    """The de-identified problem statement of the opportunity tagged with this story, if its job exists."""
    for o in store.select("opportunity", {"tag": "shipped"}):
        if str(story["id"]) in (o["tag_ref"] or "").split(":")[-1:]:
            for h in store.select("handoff", {"opportunity_id": o["opportunity_id"]}):
                if h["factory_job_json"]:
                    return h["factory_job_json"]["problem_statement"]
    return "Not stated."


def followup(ctx, stories):
    """One draft for the most recent Gong call with an existing customer, from the customer's own snippets and the shipped stories."""
    store = ctx.store
    known = {a["account_id"] for a in store.select("account") if a["arr_gbp"] is not None}
    calls = [r for r in store.select("raw_record", {"source": "gong"}) if r["account_id"] in known and r["occurred_at"]]
    if not calls:
        return
    call = max(calls, key=lambda r: (r["occurred_at"], r["raw_id"]))
    ref = f"call:{call['source_id']}"
    if store.select("outtake", {"story_ref": ref, "kind": "followup_brief"}):
        return
    said = [s["text"] for s in store.select("snippet", {"raw_id": call["raw_id"]}, order_by="start_ms")
            if not (s["speaker_email"] or "").endswith(STAFF_DOMAIN)]
    draft_one(ctx, "followup_brief", ref, "raw_record", customer_snippets=said,
              stories=[{"id": s["id"], "name": s["name"], "description": s.get("description")} for s in stories])


def run(ctx):
    store = ctx.store
    stories = shipped_stories(ctx)
    todo = [s for s in stories if not any(store.select("outtake", {"story_ref": str(s["id"]), "kind": k}) for k in KINDS)]
    ctx.gateway.map(lambda s: [draft_one(ctx, k, str(s["id"]), "story", story={"id": s["id"], "name": s["name"],
                                                                              "description": s.get("description")},
                                         problem=problem_for(store, s)) for k in KINDS], todo)
    followup(ctx, stories)
