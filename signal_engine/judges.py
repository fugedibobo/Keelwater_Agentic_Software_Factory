"""Stage 8: signal, faithfulness and duplicate judges (a different model family from the writer). Verdicts are advisory rows."""

import json
import re

from .brief import chat_with_id, fact_sheet, members, render
from .citations import cited_ids
from .contracts import JudgeVersion, Judgement
from .prompts import load_prompt
from .store import content_id

# critique first so the model reasons before it commits to a verdict
SCHEMA = {"type": "object", "properties": {"critique": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "fail"]}},
          "required": ["critique", "verdict"], "additionalProperties": False}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def similar_items(store, statement, tag_ref=None, n=5):
    """Top n stories and roadmap pages by word overlap with the statement; the tagged item always first."""
    # shortcut: word overlap instead of embedding similarity, upgrade when story embeddings are stored.
    want = _words(statement)
    scored = []
    for r in store.select("raw_record"):
        if r["source"] not in ("shortcut", "notion"):
            continue
        text = json.dumps(r["payload_json"], ensure_ascii=False) if not isinstance(r["payload_json"], str) else r["payload_json"]
        have = _words(text)
        sim = len(want & have) / len(want | have) if want | have else 0
        tagged = tag_ref in (r["raw_id"], r["source_id"])
        scored.append((not tagged, -sim, r["raw_id"], {"source": r["source"], "id": r["source_id"], "similarity": round(sim, 3), "record": text[:700]}))
    return [x[3] for x in sorted(scored, key=lambda x: x[:3])[:n]]


def judge(ctx, name, target_type, target_id, evidence):
    store, gw = ctx.store, ctx.gateway
    body, pv = load_prompt("judge", name)
    model = gw.model_ids()["judge"]
    jv = f"{pv}+{model}"
    with store.lock:
        if not store.select("judge_version", {"judge_version_id": jv}):
            store.insert("judge_version", JudgeVersion(judge_version_id=jv, judge=name, prompt_version=pv, model=model))
    out, call_id = chat_with_id(gw, "judge", render(body, evidence=evidence), target_type, target_id, pv, SCHEMA)
    store.insert("judgement", Judgement(judgement_id=content_id("judgement", ctx.run_id, jv, target_type, target_id), run_id=ctx.run_id,
                                        call_id=call_id, judge_version_id=jv, judge=name, target_type=target_type, target_id=target_id,
                                        verdict=out["verdict"], critique=out["critique"]), replace=True)


def jobs(ctx):
    store = ctx.store
    for b in store.select("brief", {"run_id": ctx.run_id}):
        opp = store.select("opportunity", {"opportunity_id": b["opportunity_id"]})[0]
        ms = members(store, opp["opportunity_id"])
        quotes = [{"quote": m["quote"], "route": m["route"], "date": m["date"]} for m in ms[:12]]
        cited = [{"id": m["insight_id"], "quote": m["quote"], "account": m["account"], "route": m["route"], "date": m["date"]}
                 for m in ms if m["insight_id"] in cited_ids(b["body_md"])]
        yield "signal", "opportunity", opp["opportunity_id"], {"title": opp["title"], "problem_statement": opp["problem_statement"], "quotes": quotes}
        yield "faithfulness", "brief", b["brief_id"], {"brief": b["body_md"], "cited_insights": cited,
                                                       "fact_sheet": fact_sheet(store, opp["opportunity_id"], ctx.as_of)}
        yield "duplicate", "brief", b["brief_id"], {"problem_statement": opp["problem_statement"],
                                                    "similar": similar_items(store, opp["problem_statement"], opp["tag_ref"])}
    for opp in store.select("opportunity"):  # a wrongly tagged opportunity gets no brief, so judge it directly
        if opp["tag"] != "none" and not opp["merged_into"]:
            yield "duplicate", "opportunity", opp["opportunity_id"], {
                "problem_statement": opp["problem_statement"], "similar": similar_items(store, opp["problem_statement"], opp["tag_ref"])}


def run(ctx):
    ctx.gateway.map(lambda j: judge(ctx, *j), list(jobs(ctx)))


def tag_disagreements(store, run_id):
    """Tagged opportunities the duplicate judge failed: for the PM queue. Never changes the tag."""
    with store.lock:
        rows = store.db.execute(
            "SELECT o.opportunity_id, o.tag, o.tag_ref, j.critique FROM judgement j JOIN opportunity o ON o.opportunity_id=j.target_id "
            "WHERE j.run_id=? AND j.judge='duplicate' AND j.target_type='opportunity' AND j.verdict='fail' AND o.tag!='none' "
            "ORDER BY o.opportunity_id", (run_id,)).fetchall()
    return [dict(r) for r in rows]
