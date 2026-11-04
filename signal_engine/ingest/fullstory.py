"""FullStory idle-strip and interaction windows: deterministic, no model."""

import re
from datetime import datetime

IDLE_S, PAD_S = 120, 60


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def is_trigger(e):
    p = e["event_properties"]
    return (e["event_type"] == "click" and bool(p.get("fs_rage_count") or p.get("fs_dead_count") or p.get("fs_error_kind"))) \
        or e["event_type"] == "exception"  # stretch item, kept: one condition


def render(e):
    """One line per event, e.g. `Claim > Documents: click "Document type" select, rage x5`."""
    p, page = e["event_properties"], (e.get("source_properties") or {}).get("page_name", "")
    parts = [f'{page}: {e["event_type"]}' if page else e["event_type"]]
    if p.get("target_text"):
        parts[0] += f' "{p["target_text"]}"'
    el = p.get("target_element") or (re.match(r"[a-z]+", p.get("target_selector") or "") or [None])[0]
    if el:
        parts[0] += f" {el}"
    if p.get("fs_rage_count"):
        parts.append(f'rage x{p["fs_rage_count"]}')
    if p.get("fs_dead_count"):
        parts.append(f'dead x{p["fs_dead_count"]}')
    if p.get("fs_error_kind"):
        parts.append(f'error {p["fs_error_kind"]}')
    if e["event_type"] == "exception" and p.get("message"):
        parts.append(str(p["message"]))
    return ", ".join(parts)


def windows(events, start):
    """-> (windows, before_s, after_s). Gaps over 120 s between events are cut to zero on a stripped clock;
    +-60 s around each trigger on that clock, overlaps merged. A window: lines, event_ids, start_ms, end_ms (real offsets)."""
    evs = sorted(events, key=lambda e: (ts(e["event_time"]), e["event_id"]))
    if not evs:
        return [], 0.0, 0.0
    real = [ts(e["event_time"]) for e in evs]
    clock, t = [], 0.0
    for i, r in enumerate(real):
        gap = r - real[i - 1] if i else 0
        t += gap if gap <= IDLE_S else 0
        clock.append(t)
    spans = []
    for e, c in zip(evs, clock):
        if is_trigger(e):
            lo, hi = max(0.0, c - PAD_S), min(clock[-1], c + PAD_S)
            if spans and lo <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], hi)
            else:
                spans.append([lo, hi])
    out = []
    for lo, hi in spans:
        inside = [i for i, c in enumerate(clock) if lo <= c <= hi]
        out.append({"lines": [render(evs[i]) for i in inside], "event_ids": [evs[i]["event_id"] for i in inside],
                    "start_ms": max(0, round((real[inside[0]] - start) * 1000)),
                    "end_ms": max(0, round((real[inside[-1]] - start) * 1000))})
    return out, real[-1] - real[0], sum(hi - lo for lo, hi in spans)
