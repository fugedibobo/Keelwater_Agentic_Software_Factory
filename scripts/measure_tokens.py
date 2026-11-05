"""Measure tokens per model for this build, price them, and render the tables in the docs (#64).

  python scripts/measure_tokens.py measure      read the local session logs, write reports/factory/tokens-by-model.csv
  python scripts/measure_tokens.py render       print the per-model table (from the CSVs, no logs needed)
  python scripts/measure_tokens.py render --write-doc    rewrite the marked blocks in docs/ai-usage.md, docs/delegation.md and README.md

Privacy: only token counts, model names, timestamps and working-folder names are read. No prompt or response text
is stored, printed or sent anywhere, and no home-folder path is written to any file (the logs are found at run time).
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / "reports" / "factory"
TOKENS_CSV, PRICES_CSV = F / "tokens-by-model.csv", F / "model-prices.csv"
OPENROUTER_CSV, TELEMETRY_CSV = F / "openrouter-usage.csv", F / "build-telemetry.csv"
CACHE_DIR = ROOT / "fixtures" / "llm_cache"
USAGE_DOC, DELEG_DOC, README_DOC = ROOT / "docs" / "ai-usage.md", ROOT / "docs" / "delegation.md", ROOT / "README.md"
SINCE = "2026-11-03"  # first build day; earlier sessions are the planning chat's other projects
REPO_WORDS = ("keelwater-agentic-software-factory", "keelwater_agentic_software_factory")
ORDER = ["Opus", "Sonnet", "Haiku", "Codex Terra", "Codex Sol", "Gemini Argon (agy)", "OpenRouter pipeline"]
COLS = ["model", "input", "cache_write", "cache_read", "output", "total", "source", "cache_write_1h"]  # the last is part of cache_write
START, END = "<!-- tokens:start -->", "<!-- tokens:end -->"


def family(model_id):
    m = (model_id or "").lower()
    for key, label in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")):
        if key in m:
            return label
    return None  # "<synthetic>" and anything unknown are not counted


def claude_rows(base):
    """Sum usage per model family from Claude Code transcripts; each API message counted once."""
    seen = {}
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        if not any(w in folder.name.lower() for w in REPO_WORDS):
            continue
        for path in folder.rglob("*.jsonl"):  # sessions and their subagents/ transcripts
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    m = o.get("message")
                    if not (isinstance(m, dict) and isinstance(m.get("usage"), dict)) or (o.get("timestamp") or "") < SINCE:
                        continue
                    label = family(m.get("model"))
                    if label is None:
                        continue
                    u = m["usage"]
                    use = (u.get("input_tokens") or 0, u.get("cache_creation_input_tokens") or 0,
                           u.get("cache_read_input_tokens") or 0, u.get("output_tokens") or 0,
                           (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0)
                    key = m.get("id") or o.get("requestId") or o.get("uuid")
                    if key not in seen or sum(use[:4]) > sum(seen[key][1][:4]):  # same message is logged once per content block
                        seen[key] = (label, use)
    return _sum(seen.values())


def codex_rows(base):
    """Last cumulative token_count per Codex session whose folder is this repo or one of its worktrees."""
    out = []
    for path in sorted(base.glob("**/rollout-*.jsonl")) if base.is_dir() else []:
        cwd, ts, model, last = "", "", None, None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                if o.get("type") == "session_meta":
                    cwd, ts = p.get("cwd") or "", p.get("timestamp") or ""
                elif o.get("type") == "turn_context" and model is None:
                    model = p.get("model")
                elif p.get("type") == "token_count" and isinstance(p.get("info"), dict):
                    last = p["info"].get("total_token_usage") or last
        if not (last and ts >= SINCE and any(w in cwd.lower().replace("\\", "/") for w in REPO_WORDS)):
            continue
        label = "Codex Sol" if "sol" in (model or "").lower() else "Codex Terra"
        cached = last.get("cached_input_tokens") or 0  # a subset of input_tokens in Codex logs
        out.append((label, ((last.get("input_tokens") or 0) - cached, last.get("cache_write_input_tokens") or 0,
                            cached, last.get("output_tokens") or 0, 0)))
    return _sum(out)


def _sum(pairs):
    t = defaultdict(lambda: [0, 0, 0, 0, 0])
    for label, use in pairs:
        for i, v in enumerate(use):
            t[label][i] += v
    return dict(t)


def openrouter_rows(cache_dir):
    """Per-model tokens and USD from the recorded response cache (one entry per distinct request)."""
    t = defaultdict(lambda: [0, 0, 0, 0.0])
    for path in sorted(cache_dir.rglob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        u = (d.get("response") or {}).get("usage") or {}
        if not u.get("tokens_in") and not u.get("tokens_out"):
            continue
        r = t[(d.get("request") or {}).get("model") or "unknown"]
        r[0] += 1
        r[1] += u.get("tokens_in") or 0
        r[2] += u.get("tokens_out") or 0
        r[3] += float(u.get("cost_usd") or 0)
    return dict(t)


def agy_row(telemetry):
    """agy tokens as its report gave them: only a total exists, so it is all booked as input."""
    rows = [r for r in csv.DictReader(open(telemetry, newline="", encoding="utf-8")) if r["engine"] == "agy"]
    good = [r for r in rows if r["tokens_basis"] in ("measured", "estimated")]
    return (sum(float(r["tokens_total"]) for r in good), "measured" if all(r["tokens_basis"] == "measured" for r in good) else "estimated") if good else (0, "estimated")


def measure(claude_base, codex_base, out=TOKENS_CSV):
    rows = {k: (v, "measured") for k, v in {**claude_rows(claude_base), **codex_rows(codex_base)}.items()}
    orr = openrouter_rows(CACHE_DIR)
    rows["OpenRouter pipeline"] = ([sum(r[1] for r in orr.values()), 0, 0, sum(r[2] for r in orr.values()), 0], "measured")
    n, basis = agy_row(TELEMETRY_CSV)
    rows["Gemini Argon (agy)"] = ([int(n), 0, 0, 0, 0], basis)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLS)
        for name in ORDER:
            use, src = rows.get(name, ([0, 0, 0, 0, 0], "measured"))
            w.writerow([name, *use[:4], sum(use[:4]), src, use[4]])
    with open(OPENROUTER_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["model", "calls", "tokens_in", "tokens_out", "cost_usd"])
        for m, r in sorted(orr.items()):
            w.writerow([m, r[0], r[1], r[2], f"{r[3]:.4f}"])


def load(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def costs(tokens, prices, openrouter):
    """API cost per model: tokens x list price per million. The OpenRouter row uses the cost its responses report."""
    p = {r["model"]: r for r in prices}
    out = []
    for r in tokens:
        use = [int(r[k]) for k in ("input", "cache_write", "cache_read", "output")]
        w1h = int(r["cache_write_1h"])
        total = int(r["total"])
        if r["model"] == "OpenRouter pipeline":
            usd = sum(float(x["cost_usd"]) for x in openrouter)
        else:
            q = p[r["model"]]
            usd = (use[0] * float(q["input"]) + (use[1] - w1h) * float(q["cache_write_5m"]) + w1h * float(q["cache_write_1h"])
                   + use[2] * float(q["cache_read"]) + use[3] * float(q["output"])) / 1e6
        out.append({"model": r["model"], "total": total, "source": r["source"], "usd": usd,
                    "blended": usd / total * 1e6 if total else 0.0, "basis": p.get(r["model"], {}).get("basis", "billed")})
    return out


WHAT = {"Opus": "Orchestrated, dispatched work orders, merged", "Sonnet": "Built work orders, checked every pull request, ran live steps",
        "Haiku": "Read, searched, summarised logs", "Codex Terra": "Offline builds, mostly stalled or hit its limit",
        "Codex Sol": "Adversarial review of the finished build", "Gemini Argon (agy)": "One blocked turn, wrote nothing",
        "OpenRouter pipeline": "Ran the product's pipeline stages on open-weight models"}


def render_table(tokens, prices, openrouter):
    c = costs(tokens, prices, openrouter)
    L = ["| Model | What it did | Total tokens | Blended rate (USD per million tokens) | API cost equivalent (USD) |", "|---|---|---|---|---|"]
    for r in c:
        mark = "estimated" if r["source"] == "estimated" else "measured"
        rate = f"{r['blended']:.2f}" + (" (nearest published tier, estimated)" if r["basis"] == "nearest-tier" else "")
        L.append(f"| {r['model']} | {WHAT[r['model']]} | {r['total']:,} ({mark}) | {rate} | {r['usd']:,.2f} |")
    t = sum(r["total"] for r in c)
    usd = sum(r["usd"] for r in c)
    L.append(f"| **Total** | | **{t:,}** | **{usd / t * 1e6:.2f}** | **{usd:,.2f}** |")
    return "\n".join(L), usd


def live_usd(telemetry):
    """Live OpenRouter spend as the work-order reports gave it; measured and estimated stay apart."""
    t = {"measured": 0.0, "estimated": 0.0}
    for r in load(telemetry):
        if r["live_usd_basis"] in t and r["live_usd"] not in ("", "not reported"):
            t[r["live_usd_basis"]] += float(r["live_usd"])
    return t


METHODS = [
    "Blended rate = the cost of every token type at its list price, divided by total tokens. Cache reads cost a tenth or less of normal input, and agent sessions are mostly cache reads, so the blended rate is far below the headline price.",
    "Claude: summed from the usage fields of the laptop's Claude Code session logs from 03/11/2026, subagents included, each API message counted once. Only token counts and model names are read.",
    "Codex: the last token count of each Codex session run in this repo or its worktrees from 03/11/2026. Terra and Sol are priced at the 272K-or-less rates.",
    "Gemini Argon (agy): the one total its report gave, all counted as input because no split exists. Its published rate is the one in force until 30/11/2026 and doubles on 01/12/2026.",
    "OpenRouter pipeline: summed from the recorded model responses in the repo's replay cache, one entry per distinct request. Repeated and failed calls are not in it, so it is a lower bound; the rate is the cost each response reported.",
    "Haiku is priced at the over-100K-prompt rates, which some of its calls reached. Prices were read from the providers' pages on 05/11/2026; sources are in reports/factory/README.md.",
]


def comparison(usd, spend):
    return (f"At API prices this build would cost a company about USD {usd:,.0f}. What it cost me: the Claude and Codex "
            f"subscriptions I already pay for, which charge no per-token fee, plus OpenRouter spend of USD {spend['measured']:.2f} "
            f"measured and USD {spend['estimated']:.2f} estimated, as the work-order reports gave it.")


def usage_block(tokens, prices, openrouter, telemetry):
    table, usd = render_table(tokens, prices, openrouter)
    notes = "\n".join(f"- {m}" for m in METHODS)
    return f"{table}\n\n{notes}\n\n{comparison(usd, live_usd(telemetry))}"


def summary_line(tokens, prices, openrouter):
    c = costs(tokens, prices, openrouter)
    return (f"Measured from the session logs, the build used {sum(r['total'] for r in c):,} tokens across all models, "
            f"an API cost equivalent of about USD {sum(r['usd'] for r in c):,.0f}; the table is in [ai-usage.md](docs/ai-usage.md).")


def write_block(path, block):
    text = path.read_text(encoding="utf-8")
    a, b = text.find(START), text.find(END)
    if a < 0 or b < a:
        raise SystemExit(f"markers {START} / {END} not found in {path.name}")
    path.write_bytes((text[:a + len(START)] + "\n\n" + block + "\n\n" + text[b:]).encode("utf-8"))  # LF kept on Windows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--claude-dir", type=Path, default=Path.home() / ".claude" / "projects")
    m.add_argument("--codex-dir", type=Path, default=Path.home() / ".codex" / "sessions")
    r = sub.add_parser("render")
    r.add_argument("--write-doc", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "measure":
        measure(a.claude_dir, a.codex_dir)
        print(TOKENS_CSV.read_text(encoding="utf-8"))
        return
    t, p, o = load(TOKENS_CSV), load(PRICES_CSV), load(OPENROUTER_CSV)
    block = usage_block(t, p, o, TELEMETRY_CSV)
    print(block)
    if a.write_doc:
        write_block(USAGE_DOC, block)
        write_block(DELEG_DOC, render_table(t, p, o)[0])
        write_block(README_DOC, summary_line(t, p, o))


if __name__ == "__main__":
    main()
