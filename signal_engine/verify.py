"""Quote verification (docs/evals.md 3.2): the quote must sit in the snippet's own text, never context_text."""

import re
import unicodedata

FILLERS = {"um", "uh", "er", "erm", "ah"}
FILLER_SOURCES = {"gong", "fireflies"}
_MAP = {"‘": "'", "’": "'", "‛": "'", "“": '"', "”": '"', "–": "-", "—": "-",
        "‐": "-", "‑": "-", "−": "-", " ": " "}
_ELLIPSIS = re.compile(r"\.\.\.|…")


def normalise(text, drop_fillers=False):
    """Return (normalised text, index of each output char in the original text)."""
    chars = []
    for i, ch in enumerate(text):
        for o in unicodedata.normalize("NFKC", ch).casefold():
            chars.append((_MAP.get(o, o), i))
    kept = []
    for j, (ch, i) in enumerate(chars):
        prev = chars[j - 1][0] if j else ""
        nxt = chars[j + 1][0] if j + 1 < len(chars) else ""
        if ch.isspace():
            kept.append((" ", i))
        elif ch.isalnum() or ch in "£%":
            kept.append((ch, i))
        elif ch == "'" and prev.isalnum() and nxt.isalnum():
            kept.append((ch, i))
        elif ch in ".," and prev.isdigit() and nxt.isdigit():
            kept.append((ch, i))
    out, word = [], []  # word = run of non-space (char, index) pairs

    def flush():
        if word and not (drop_fillers and "".join(c for c, _ in word) in FILLERS):
            out.extend(word + [(" ", word[-1][1])])
        word.clear()

    for ch, i in kept:
        if ch == " ":
            flush()
        else:
            word.append((ch, i))
    flush()
    if out:
        out.pop()  # trailing space
    return "".join(c for c, _ in out), [i for _, i in out]


def _find_in_order(fragments, hay):
    """(start, end) from the first fragment's start to the last one's end; None unless all match in order."""
    pos, first, last = 0, None, 0
    for f in fragments:
        p = hay.find(f, pos)
        if p < 0:
            return None
        first = p if first is None else first
        pos = last = p + len(f)
    return first, last


def _fragments(quote, norm=None):
    parts = _ELLIPSIS.split(quote)
    if len(parts) > 1:
        parts = [p for p in parts if len(p.split()) >= 3]  # shorter fragments are connective tissue
    parts = [norm(p)[0] if norm else p.strip() for p in parts]
    return [p for p in parts if p]


def verify_quote(quote, text, source):
    """Return (quote_match, span_start, span_end); quote_match is exact, normalised or failed (span None)."""
    quote = quote.strip()
    if not 5 <= len(quote.split()) <= 60:
        return "failed", None, None
    frags = _fragments(quote)
    hit = frags and _find_in_order(frags, text)
    if hit:
        return "exact", hit[0], hit[1]
    if str(source) == "fullstory":  # a rendered UI line: exact only
        return "failed", None, None
    fill = str(source) in FILLER_SOURCES
    ns, idx = normalise(text, fill)
    frags = _fragments(quote, lambda p: normalise(p, fill))
    hit = frags and _find_in_order(frags, ns)
    if not hit:
        return "failed", None, None
    return "normalised", idx[hit[0]], idx[hit[1] - 1] + 1
