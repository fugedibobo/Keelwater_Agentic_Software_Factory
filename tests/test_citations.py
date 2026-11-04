"""One passing brief and one failing example per rule of docs/evals.md 3.4."""

import pytest

from signal_engine.citations import check, money_ok

FACTS = {"accounts_n": 3, "mentions_n": 3, "routes_n": 2, "mentions_by_route": {"sales": 1, "support": 2}, "renewals_90d_n": 1,
         "arr_total_gbp": 2450000.0,
         "accounts": [{"name": "Northgate Mutual", "arr_gbp": 1200000.0, "mentions": 1},
                      {"name": "Harbour Assurance", "arr_gbp": 750000.0, "mentions": 1},
                      {"name": "Pennine Cover", "arr_gbp": 500000.0, "mentions": 1}]}
MEMBERS = {"a": {"quote": "the bulk upload keeps timing out", "account_id": "A1", "route": "sales", "verified": True},
           "b": {"quote": "we re-key every claim by hand", "account_id": "A2", "route": "support", "verified": True},
           "c": {"quote": "adjusters lose an hour a day", "account_id": "A3", "route": "support", "verified": True}}
NAMES = {"A1": "Northgate Mutual", "A2": "Harbour Assurance", "A3": "Pennine Cover"}
GOOD = """# Bulk upload timeouts
## Problem
Claims handlers lose time when uploads fail [i:a] [i:b] [i:c].
## Who is affected
- 3 accounts report it, worth £2.5m of ARR [i:a] [i:b] [i:c]
- 3 mentions across 2 routes [i:a]
## Evidence
- Northgate Mutual: "the bulk upload keeps timing out" [i:a]
- Harbour Assurance said "We re-key every claim by hand." [i:b]
## Why now
- 1 renewal falls in the next 90 days [i:a]
"""


def rules(body, members=MEMBERS):
    return {f["rule"] for f in check(body, members, FACTS, NAMES)}


def test_good_brief_passes():
    assert check(GOOD, MEMBERS, FACTS, NAMES) == []


@pytest.mark.parametrize("rule,old,new", [
    ("cited_ids", "[i:c].", "[i:c] [i:zzzz]."),                                   # 1 id not of this opportunity
    ("uncited_claims", "- 3 mentions across 2 routes [i:a]", "- 3 mentions across 2 routes"),  # 2 number without citation
    ("uncited_claims", "## Why now", "- An evidence bullet with no citation\n## Why now"),     # 2 bullet without citation
    ("numbers", "£2.5m", "£2.9m"),                                                # 3 ARR off the total
    ("numbers", "3 accounts", "4 accounts"),                                      # 3 count off
    ("quotes", '"the bulk upload keeps timing out"', '"the bulk upload always times out"'),    # 4 paraphrase in quotes
    ("customer_names", "- 3 mentions across 2 routes [i:a]", "- Pennine Cover also reported it [i:a]"),  # 5 name not in cited insight
])
def test_one_failing_example_per_rule(rule, old, new):
    assert old in GOOD
    assert rule in rules(GOOD.replace(old, new, 1))


@pytest.mark.parametrize("old,new", [
    ("Claims handlers lose time when uploads fail [i:a]", "Failure rate is 99% [i:a]"),    # cited, but no fact supports a percentage
    ("Claims handlers lose time when uploads fail [i:a]", "Seven handlers lose time every day [i:a]"),  # number word outside a count phrase
    ("Claims handlers lose time when uploads fail [i:a]", "Uploads fail 12 times a day [i:a]"),  # digits outside a count phrase
])
def test_numbers_outside_supported_facts_fail(old, new):
    assert old in GOOD
    assert "numbers" in rules(GOOD.replace(old, new, 1))


@pytest.mark.parametrize("new", [
    "Renewals fall due by 2026-12-05 [i:a]",                    # fact-sheet date
    "The newest report is dated 2026-10-28 [i:a]",              # date of a cited insight
    "Reports run from September to October 2026 [i:a]",         # year of a cited insight
    "Combined ARR is GBP 2450000.0 [i:a]",                      # sum of the account ARR values, GBP form
    "Combined ARR is 2,450,000 GBP [i:a]",                      # same, with separators
])
def test_verifiable_derived_numbers_pass(new):
    facts = {**FACTS, "as_of": "2026-11-03", "accounts": [{**FACTS["accounts"][0], "renewal_date": "2026-12-05"}, *FACTS["accounts"][1:]]}
    members = {**MEMBERS, "a": {**MEMBERS["a"], "date": "2026-10-28"}}
    body = GOOD.replace("Claims handlers lose time when uploads fail [i:a]", new, 1)
    assert check(body, members, facts, NAMES) == []


def test_arr_sum_of_cited_accounts_only():
    body = GOOD.replace("Claims handlers lose time when uploads fail [i:a] [i:b] [i:c].", "A combined ARR of 1,950,000 GBP [i:a][i:b].", 1)
    assert check(body, MEMBERS, FACTS, NAMES) == []  # 1,200,000 + 750,000 = the accounts behind a and b
    other = GOOD.replace("Claims handlers lose time when uploads fail [i:a] [i:b] [i:c].", "A combined ARR of 1,950,000 GBP [i:b][i:c].", 1)
    assert "numbers" in rules(other)  # b and c are 750,000 + 500,000


def test_unverified_quote_fails_rule_1():
    m = {**MEMBERS, "a": {**MEMBERS["a"], "verified": False}}
    assert "cited_ids" in rules(GOOD, m)


def test_rule_6_two_routes_must_both_be_cited():
    ms = {k: {**v, "route": "support"} for k, v in MEMBERS.items()} | {"d": {**MEMBERS["a"], "route": "sales"}}
    assert "citation_spread" in rules("## Problem\nIt hurts [i:a] [i:b] [i:c].\n", ms)


def test_arr_precision_is_the_stated_precision():
    allowed = [2450000.0]
    assert money_ok("£2.5m", allowed) == [] and money_ok("£2,450,000", allowed) == [] and money_ok("£2450k", allowed) == []
    assert money_ok("£2.4m", allowed) == ["£2.4m"]


def test_rule_6_three_insights_need_three_citations():
    assert "citation_spread" in rules("## Problem\nIt hurts [i:b].\n")
