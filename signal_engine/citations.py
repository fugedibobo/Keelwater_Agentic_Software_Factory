"""Citation integrity for briefs: the six rules of docs/evals.md 3.4, pure functions over plain dicts.

check(body, members, facts, names) -> list of {"rule", "detail"}; empty means the brief passes.
members: {insight_id: {"quote", "account_id", "route", "verified"}} for this opportunity only.
facts: the fact sheet (see brief.fact_sheet). names: {account_id: customer name} for every account in the store.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

CITE = re.compile(r"\[i:([0-9a-zA-Z_-]+)\]")
QUOTE = re.compile(r'"([^"]+)"|\u201c([^\u201d]+)\u201d')
BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
MONEY = re.compile(r"\u00a3\s?([\d,]+(?:\.(\d+))?)\s?(bn|m|k)?\b", re.I)
COUNT = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:[\w-]+\s+)?(account|customer|mention|route|renewal)s?\b", re.I)
WINDOW = re.compile(r"\b90[- ]days?\b", re.I)  # the renewal horizon of the fact sheet (brief.RENEWAL_DAYS)
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(r"\d(?:,?\d)*(?:\.\d+)?|%|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|hundred|thousand|million)\b", re.I)
WORDS = dict(zip("one two three four five six seven eight nine ten".split(), range(1, 11)))
UNIT = {"": 1, "k": 10**3, "m": 10**6, "bn": 10**9}
RULES = ("cited_ids", "uncited_claims", "numbers", "quotes", "customer_names", "citation_spread")


def cited_ids(text):
    return list(dict.fromkeys(CITE.findall(text)))


def norm(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", s).strip().lower().strip(" .,;:!?\u2026")


def units(body):
    """(section, is_bullet, sentence) for each sentence; quoted text never splits a sentence; headings are skipped."""
    section, out = "", []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            section = line.lstrip("# ").strip().lower()
            continue
        if not line.strip():
            continue
        bullet = bool(BULLET.match(line))
        quotes = []
        masked = QUOTE.sub(lambda m: quotes.append(m.group(0)) or f"\x00{len(quotes) - 1}\x00", BULLET.sub("", line))
        for sent in re.split(r"(?<=[.!?])\s+(?!\[i:)", masked.strip()):
            out.append((section, bullet, re.sub(r"\x00(\d+)\x00", lambda m: quotes[int(m.group(1))], sent)))
    return out


def _round(v, places):
    return Decimal(v).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def money_ok(sentence, allowed):
    """Failures for each £ amount not equal to an allowed ARR value at the stated unit and decimals."""
    bad = []
    for m in MONEY.finditer(sentence):
        places, mult = len(m.group(2) or ""), UNIT[(m.group(3) or "").lower()]
        stated = _round(Decimal(m.group(1).replace(",", "")), places)
        if not any(_round(Decimal(str(a)) / mult, places) == stated for a in allowed):
            bad.append(m.group(0))
    return bad


def count_expected(facts):
    per_route = list(facts["mentions_by_route"].values())
    per_acct = [a["mentions"] for a in facts["accounts"]]
    return {"account": {facts["accounts_n"]}, "customer": {facts["accounts_n"]},
            "mention": {facts["mentions_n"], *per_route, *per_acct}, "route": {facts["routes_n"]},
            "renewal": {facts["renewals_90d_n"]}}


def check(body, members, facts, names):
    fails = []

    def fail(rule, detail):
        fails.append({"rule": rule, "detail": detail})

    cited = cited_ids(body)
    for i in cited:  # rule 1
        if i not in members:
            fail("cited_ids", f"{i} is not an insight of this opportunity")
        elif not members[i]["verified"]:
            fail("cited_ids", f"{i} has an unverified quote")
    allowed_money = [facts["arr_total_gbp"], *[a["arr_gbp"] for a in facts["accounts"] if a["arr_gbp"] is not None]]
    expected = count_expected(facts)
    facts_n = {Decimal(str(x)) for x in [*allowed_money, *[n for v in expected.values() for n in v]]}
    dates = {facts.get("as_of"), *[(a.get("renewal_date") or "")[:10] for a in facts["accounts"]]} - {None, ""}
    facts_n |= {Decimal(d[:4]) for d in dates}  # fact-sheet years
    for section, bullet, sent in units(body):
        ids = cited_ids(sent)
        plain = QUOTE.sub("", sent)
        if not ids and ((bullet and section in ("evidence", "who is affected")) or re.search(r"\d", plain)):  # rule 2
            fail("uncited_claims", f"no citation: {sent[:80]}")
        for m in MONEY.finditer(plain):  # rule 3, money
            for bad in money_ok(m.group(0), allowed_money):
                fail("numbers", f"{bad} does not match the fact sheet (total {facts['arr_total_gbp']:,.0f})")
        for m in COUNT.finditer(plain):  # rule 3, counts
            n = WORDS.get(m.group(1).lower()) or int(m.group(1))
            if n not in expected[m.group(2).lower()]:
                fail("numbers", f"'{m.group(0)}' does not match the fact sheet ({sorted(expected[m.group(2).lower()])})")
        mine = {str(members[i].get("date") or "")[:10] for i in ids if i in members}  # dates of the cited insights and in their text
        for i in ids:
            mine |= set(ISO.findall(members.get(i, {}).get("quote") or ""))
        ok_dates = (dates | mine) - {""}
        sent_n = facts_n | {Decimal(d[:4]) for d in ok_dates}
        near = ids or next((cited_ids(ln) for ln in body.splitlines() if sent in ln), [])  # the sentence's own citations, else its paragraph's
        accts = {members[i]["account_id"] for i in near if i in members}
        arr = [a["arr_gbp"] for a in facts["accounts"] if a["arr_gbp"] is not None and any(names.get(x) == a["name"] for x in accts)]
        sent_n |= {Decimal(str(sum(arr)))} if arr else set()  # ARR sum of the accounts behind the cited insights
        rest = COUNT.sub(" ", MONEY.sub(" ", ISO.sub(lambda m: " " if m.group(0) in ok_dates else m.group(0), CITE.sub(" ", plain))))
        for m in NUMBER.finditer(WINDOW.sub(" ", rest)):  # rule 3, every other number must equal a fact-sheet value
            tok = m.group(0)
            v = Decimal({**WORDS, "zero": 0}[tok.lower()]) if tok.lower() in {**WORDS, "zero": 0} else None if not tok[0].isdigit() else Decimal(tok.replace(",", ""))
            if v is None or v not in sent_n:
                fail("numbers", f"'{tok}' matches no fact-sheet value: {sent[:60]}")
        have = {norm(members[i]["quote"]) for i in ids if i in members}
        for m in QUOTE.finditer(sent):  # rule 4
            if norm(m.group(1) or m.group(2)) not in have:
                fail("quotes", f"quoted text is not the quote of a cited insight: {(m.group(1) or m.group(2))[:60]}")
        own = {members[i]["account_id"] for i in ids if i in members}
        for acct, name in names.items():  # rule 5
            if re.search(rf"\b{re.escape(name)}\b", sent, re.I) and acct not in own:
                fail("customer_names", f"{name} is not the account of a cited insight")
    valid = [i for i in cited if i in members]  # rule 6
    if len(members) >= 3 and len(valid) < 3:
        fail("citation_spread", f"{len(members)} insights but only {len(valid)} distinct citations")
    routes = {m["route"] for m in members.values() if m["route"]}
    if len(routes) >= 2 and len({members[i]["route"] for i in valid if members[i]["route"]}) < 2:
        fail("citation_spread", f"opportunity spans {len(routes)} routes but citations cover fewer than two")
    return fails
