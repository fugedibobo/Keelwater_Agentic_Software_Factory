"""Stage 3: one insight per kept snippet, with a verified quote (architecture section 4, evals 3.2)."""

from . import prompts
from .contracts import Insight
from .gateway import call_id_for
from .store import canonical, insight_id, sha256
from .verify import verify_quote

RETRY = "quote not found in snippet; copy it verbatim"
EXTRACT = ("keep", "low_confidence", "untriaged")


def _words(text, n):
    return " ".join(text.split()[:n])


def extract_one(gw, snippet, source, system, version):
    """Return (model output dict, quote_match, span_start, span_end, call_id) after at most one retry."""
    user = (f"SNIPPET (quote only from here):\n{snippet['text']}\n\n"
            f"CONTEXT (internal, do not quote):\n{snippet['context_text'] or '(none)'}")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in (0, 1):
        body = gw.chat_request("extract", messages)
        call_id = call_id_for("extract", sha256(canonical(body)), "snippet", snippet["snippet_id"])
        out = gw.chat("extract", messages, target_type="snippet", target_id=snippet["snippet_id"], prompt_version=version)
        match, start, end = verify_quote(str(out.get("quote", "")), snippet["text"], source)
        if match != "failed" or attempt:
            return out, match, start, end, call_id
        messages = messages + [{"role": "assistant", "content": canonical(out)}, {"role": "user", "content": RETRY}]


def run(ctx):
    store, gw = ctx.store, ctx.gateway
    system, version = prompts.load_prompt("extract", "extract")
    raws = {r["raw_id"]: r for r in store.select("raw_record")}
    done = {i["snippet_id"] for i in store.select("insight")}
    triage = {t["snippet_id"]: t for t in store.select("triage", {"run_id": ctx.run_id}) if t["decision"] in EXTRACT}
    todo = [s for s in store.select("snippet", order_by="snippet_id") if s["snippet_id"] in triage and s["snippet_id"] not in done]

    def work(snippet):
        raw = raws[snippet["raw_id"]]
        out, match, start, end, call_id = extract_one(gw, snippet, raw["source"], system, version)
        quote = str(out.get("quote", "")).strip()
        if not 5 <= len(quote.split()) <= 60:  # the Insight contract needs 5-60 words even for a failed quote
            # shortcut: a failed quote is stored as the snippet's first 60 words, upgrade if the board must show the model's text
            quote = _words(snippet["text"], 60)
        if len(quote.split()) < 5:
            return None  # shortcut: a snippet under 5 words cannot hold an insight, upgrade with a looser contract
        return Insight(insight_id=insight_id(snippet["snippet_id"], quote), snippet_id=snippet["snippet_id"], run_id=ctx.run_id,
                       call_id=call_id, problem=str(out.get("problem", "")), quote=quote, quote_match=match,
                       quote_span_start=start, quote_span_end=end, workflow=out.get("workflow"),
                       desired_outcome=out.get("desired_outcome"),
                       severity=triage[snippet["snippet_id"]]["severity"] or 2,  # shortcut: untriaged gets mid severity 2, upgrade when #4 sets one
                       account_id=raw["account_id"], account_status=raw["account_status"])

    for ins in gw.map(work, todo):
        if ins:
            store.insert("insight", ins, replace=True)
    snip_raw = {s["snippet_id"]: s["raw_id"] for s in store.select("snippet")}
    for ins in store.select("insight"):  # evals 3.3: no model chooses an account
        assert ins["account_id"] == raws[snip_raw[ins["snippet_id"]]]["account_id"]
