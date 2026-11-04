"""Stage 5, tagging: shipped and roadmap matches by embedding similarity, code only (ADR-004)."""

from datetime import datetime, timezone

from .cluster import unit

ROADMAP = {"planned", "in progress"}


def parse_dt(s):
    """ISO date or datetime (a trailing Z allowed) as an aware UTC datetime; None when absent."""
    if not s:
        return None
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def reference_items(store):
    """Shipped Shortcut stories and Planned or In progress Notion pages as {ref, tag, text, completed_at}.

    shortcut: one raw_record per story or per export file, upgrade if #3 stores another shape.
    """
    out = []
    for raw in store.select("raw_record"):
        p = raw["payload_json"]
        if raw["source"] == "shortcut":
            for s in p.get("stories", [p]):
                if s.get("completed"):
                    out.append({"ref": f"shortcut:{s['id']}", "tag": "shipped", "completed_at": s.get("completed_at"),
                                "text": f"{s['name']}\n{s.get('description') or ''}".strip()})
        elif raw["source"] == "notion":
            for pg in p.get("results", [p]):
                props = pg["properties"]
                if props["Status"]["status"]["name"].casefold() in ROADMAP:
                    title = "".join(t["plain_text"] for t in props["Name"]["title"])
                    problem = "".join(t["plain_text"] for t in props.get("Problem", {}).get("rich_text", []))
                    out.append({"ref": f"notion:{pg['id']}", "tag": "on_roadmap", "completed_at": None, "text": f"{title}\n{problem}".strip()})
    return sorted(out, key=lambda i: i["ref"])


def run(ctx):
    store = ctx.store
    items = reference_items(store)
    opps = [o for o in store.select("opportunity", order_by="opportunity_id") if o["merged_into"] is None and o["centroid"]]
    if not items or not opps:
        return
    threshold = ctx.config["pipeline"]["tagging"]["similarity"]
    vecs = [unit(v) for v in ctx.gateway.embed("embed", [i["text"] for i in items], target_type="reference", target_id="roadmap")]
    snippet_of = {i["insight_id"]: i["snippet_id"] for i in store.select("insight")}
    raw_of = {s["snippet_id"]: s["raw_id"] for s in store.select("snippet")}
    when = {r["raw_id"]: r["occurred_at"] for r in store.select("raw_record")}
    for o in opps:
        if o["tag_state"] in ("confirmed", "removed"):  # a PM decision stands
            continue
        c = unit(o["centroid"])
        sim, item = max(((float(c @ v), it) for v, it in zip(vecs, items)), key=lambda x: (x[0], x[1]["ref"]))
        hit = item if sim > threshold else None
        store.update("opportunity", {"opportunity_id": o["opportunity_id"]},
                     {"tag": hit["tag"] if hit else "none", "tag_ref": hit["ref"] if hit else None,
                      "tag_state": "proposed" if hit else None})
        done = parse_dt(hit["completed_at"]) if hit and hit["tag"] == "shipped" else None
        for link in store.select("opportunity_insight", {"opportunity_id": o["opportunity_id"]}):
            seen = parse_dt(when.get(raw_of.get(snippet_of.get(link["insight_id"]))))
            store.update("opportunity_insight", {"insight_id": link["insight_id"]}, {"post_ship": bool(done and seen and seen > done)})
