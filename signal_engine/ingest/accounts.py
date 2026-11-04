"""HubSpot account table, domain and id resolution (evals 3.3), teams.yaml."""

from datetime import date, datetime
from pathlib import Path

import yaml

from .. import config
from ..contracts import Account

DEFAULT_TEAMS = {"internal_domains": ["keelwater.example"], "teams": {}}


def load_teams(data_dir):
    """<data root>/teams.yaml when it exists (fixtures), else config/teams.yaml, else the built-in default.

    Format: internal_domains: [..]; teams: {onboarding: [emails], account_management: [emails], ...}.
    """
    for p in (Path(data_dir) / "teams.yaml", config.CONFIG_DIR / "teams.yaml"):
        if p.is_file():
            return {**DEFAULT_TEAMS, **(yaml.safe_load(p.read_text(encoding="utf-8")) or {})}
    return DEFAULT_TEAMS


def is_internal(email, teams):
    e = (email or "").strip().lower()
    return bool(e) and (e.rsplit("@", 1)[-1] in teams["internal_domains"]
                        or any(e == m.lower() for ms in teams["teams"].values() for m in ms))


def team_of(email, teams):
    e = (email or "").strip().lower()
    return next((t for t, ms in teams["teams"].items() if e in [m.lower() for m in ms]), None)


def norm_domain(value):
    d = (value or "").strip().lower().rsplit("@", 1)[-1]
    return d[4:] if d.startswith("www.") else d


def parse_arr(v):
    """'2400000', '1,250,000', '£610k', '540000.00' -> float; anything else -> None (missing, never guessed)."""
    s = (v or "").strip().lower().replace("£", "").replace(",", "")
    mult = 1000 if s.endswith("k") else 1
    try:
        return float(s.rstrip("k")) * mult if s else None
    except ValueError:
        return None


def parse_date(v):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((v or "").strip()[:10], fmt).date()
        except ValueError:
            pass
    return None


def renewal_within_days(renewal, as_of, days=90):
    """True when the renewal date falls in [as_of, as_of + days]; a missing date is False (never guessed)."""
    return renewal is not None and 0 <= (renewal - as_of).days <= days


def canonical_accounts(records):
    """HubSpot company records -> (Account list, id->canonical id, domain->canonical id).

    Of records sharing a domain the customer with the latest hs_lastmodifieddate wins.
    """
    by_domain = {}
    for r in records:
        p = r["properties"]
        by_domain.setdefault(norm_domain(p.get("domain")), []).append(r)
    id_map, dom_map, accounts = {}, {}, []
    for dom, group in by_domain.items():
        win = max(group, key=lambda r: (r["properties"].get("lifecyclestage") == "customer",
                                        r["properties"].get("hs_lastmodifieddate") or ""))
        p = win["properties"]
        dom_map[dom] = win["id"]
        id_map.update({r["id"]: win["id"] for r in group})
        accounts.append(Account(account_id=win["id"], name=p["name"], arr_gbp=parse_arr(p.get("keelwater_arr_gbp")),
                                tier=(p.get("keelwater_tier") or "").strip().title() or None,
                                renewal_date=parse_date(p.get("renewal_date"))))
    return accounts, id_map, dom_map


def settle(ids):
    """Set of canonical account ids -> (account_id, status)."""
    ids = set(ids)
    if len(ids) == 1:
        return next(iter(ids)), "resolved"
    return None, ("ambiguous" if ids else "unresolved")


def by_emails(emails, dom_map):
    """Domains unknown to HubSpot (personal mail, brokers, adjusters) are ignored."""
    return settle(dom_map[d] for d in {norm_domain(e) for e in emails if e} if d in dom_map)
