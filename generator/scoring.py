"""Apply architecture section 4 to the intended planted accounts."""
from __future__ import annotations
from datetime import date, datetime
from math import log10, log2
from .specs import load


def score(theme, accounts):
    lookup = {a['key']: a for a in accounts}
    selected = [lookup[key] for key in theme['accounts']]
    nominal = 135000
    arr = sum(a['arr_gbp'] if a['arr_gbp'] is not None else nominal for a in selected)
    renewing = sum(a['arr_gbp'] or nominal for a in selected if a['renewal'] and date(2026, 11, 3) <= datetime.strptime(a['renewal'], '%d/%m/%Y').date() <= date(2027, 2, 1))
    routes = sum(v > 0 for v in theme['routes'].values())
    corroboration = 1.5 if routes >= 3 else 1.3 if routes == 2 else 1
    recent_count = 2 if theme['kind'] == 'shipped' else theme['mentions'] // 2
    recency = max(.2, recent_count / theme['mentions'])
    return log2(1 + len(selected)) * theme['severity'] * max(.5, 1 + log10(arr / 270000)) * corroboration * recency * (1 + .25 * renewing / arr) * (.5 if theme['kind'] == 'roadmap' else 1)
