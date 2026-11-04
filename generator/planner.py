"""Construct a deterministic, private plan before making any model calls."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import random

from .specs import ROOT, load

VOLUMES = {
    42: {'sales': 25, 'support': 60, 'onboarding': 10, 'account_management': 12, 'sessions': 40, 'hubspot': 36, 'shortcut': 12, 'notion': 10},
    43: {'sales': 10, 'support': 24, 'onboarding': 4, 'account_management': 4, 'sessions': 16, 'hubspot': 36, 'shortcut': 12, 'notion': 10},
}


def plan(seed: int) -> dict:
    if seed not in VOLUMES:
        raise ValueError('Only seeds 42 and 43 are specified')
    base = ROOT / 'generator' / 'spec'
    specific = base / 'holdout' if seed == 43 else base
    paths = [base / f'{x}.yaml' for x in ('accounts', 'people', 'glossary')] + [specific / f'{x}.yaml' for x in ('themes', 'noise')]
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    return deepcopy(_plan_cached(seed, signature))


@lru_cache(maxsize=8)
def _plan_cached(seed: int, signature: tuple) -> dict:
    spec = load(seed)
    rng = random.Random(seed)
    records = []
    for route in ('sales', 'support', 'onboarding', 'account_management', 'sessions'):
        for i in range(VOLUMES[seed][route]):
            source = {'sales': 'gong', 'support': 'intercom', 'onboarding': 'fireflies', 'account_management': 'fireflies', 'sessions': 'fullstory'}[route]
            identity = hashlib.sha256(f'{seed}:{route}:{i}'.encode()).hexdigest()[:12]
            records.append({'id': identity, 'source': source, 'route': route, 'account': None, 'mentions': []})
    # Allocate to slots by account, spreading a theme's accounts over routes.
    themes = spec['themes']['themes']
    pending = []
    for theme in themes:
        accounts = theme['accounts'][:]
        rng.shuffle(accounts)
        n = 0
        for route, count in theme['routes'].items():
            for _ in range(count):
                pending.append((theme, route, accounts[n % len(accounts)], n))
                n += 1
    growth = [a['key'] for a in spec['accounts']['accounts'] if a['tier'] == 'Growth']
    one_off_routes = (['support'] * 3 + ['sales'] * 2 + ['onboarding'] * 2 + ['account_management'] * 3) if seed == 42 else ['support', 'support', 'onboarding', 'account_management']
    for i, (request, route) in enumerate(zip(spec['noise']['one_offs'], one_off_routes)):
        theme = {'id': f'one-off:{i}', 'mentions': 1, 'request': request, 'severity': 1 + i % 2, 'recent_count': rng.randrange(2)}
        pending.append((theme, route, rng.choice(growth), 0))
    # Minimise the number of account-specific slots by swapping account
    # assignments within each theme; this preserves each theme's coverage.
    def required(items):
        groups = {}
        for theme, route, account, number in items:
            recent_count = theme.get('recent_count', 2 if theme.get('kind') == 'shipped' else theme['mentions'] // 2)
            k = (route, account, number < recent_count)
            groups.setdefault(k, Counter())[theme['id']] += 1
        result = Counter()
        for (route, _, _), counts in groups.items():
            result[route] += sum(counts.values()) if route == 'sessions' else max((sum(counts.values()) + 2) // 3, max((n + 1) // 2 for n in counts.values()))
        return sum(max(0, result[r] - VOLUMES[seed][r]) for r in result)

    by_theme = {}
    for i, item in enumerate(pending):
        by_theme.setdefault(item[0]['id'], []).append(i)
    score = required(pending)
    for iteration in range(100000):
        if score == 0:
            break
        indices = rng.choice(list(by_theme.values()))
        if len(indices) < 2:
            i = indices[0]
            a = pending[i]
            if not a[0]['id'].startswith('one-off:'):
                continue
            pending[i] = (a[0], a[1], rng.choice(growth), a[3])
            new = required(pending)
            if new <= score or rng.random() < .003:
                score = new
            else:
                pending[i] = a
            continue
        i, j = rng.sample(indices, 2)
        a, b = pending[i], pending[j]
        pending[i] = (a[0], a[1], b[2], a[3])
        pending[j] = (b[0], b[1], a[2], b[3])
        new = required(pending)
        if new <= score or rng.random() < .003:
            score = new
        else:
            pending[i], pending[j] = a, b
    if score:
        raise ValueError(f'Cannot place mentions within route/account capacity: {score}')
    pending.sort(key=lambda x: (x[1], x[2], x[3] < x[0].get('recent_count', 2 if x[0].get('kind') == 'shipped' else x[0]['mentions'] // 2), x[0]['id']))
    for theme, route, account, number in pending:
        recent = number < theme.get('recent_count', 2 if theme.get('kind') == 'shipped' else theme['mentions'] // 2)
        candidates = [r for r in records if r['route'] == route and r['account'] in (None, account) and (not r['mentions'] or r['recent'] == recent) and len(r['mentions']) < (1 if route == 'sessions' else 3) and sum(m['theme'] == theme['id'] for m in r['mentions']) < 2]
        candidates.sort(key=lambda r: (r['account'] is None, len(r['mentions'])))
        if not candidates:
            raise ValueError('Cannot pack allocated mentions')
        slot = candidates[0]
        slot['account'] = account
        slot['recent'] = recent
        day = datetime(2026, 10, 15, tzinfo=timezone.utc) if recent else datetime(2026, 9, 15, tzinfo=timezone.utc)
        mention = {'id': f"{theme['id']}:{number}", 'theme': theme['id'], 'account': account, 'occurred_at': day.isoformat().replace('+00:00', 'Z')}
        if theme['id'] == 'cx-auto-assignment':
            mention['stance'] = 'more_automation' if account in ('A02', 'A04', 'A11') else 'less_automation'
        else:
            mention['stance'] = None
        mention['post_ship'] = bool(theme.get('kind') == 'shipped' and recent)
        if 'request' in theme:
            mention.update(request=theme['request'], severity=theme['severity'])
        slot['mentions'].append(mention)
    sales = [r for r in records if r['route'] == 'sales']
    if seed == 42:
        prospect_count = sum(bool(r['account'] and r['account'].startswith('P')) for r in sales)
        empty_sales = [r for r in sales if r['account'] is None]
        if prospect_count > 7 or len(empty_sales) < 7 - prospect_count:
            raise ValueError('Cannot place seven prospect calls')
        for r in empty_sales[:7 - prospect_count]:
            r['account'] = rng.choice(['P1', 'P2', 'P3', 'P4'])
    customers = [a['key'] for a in spec['accounts']['accounts'] if a['arr_gbp'] is not None]
    for r in records:
        if r['account'] is None:
            r['account'] = rng.choice(customers)
        r['mentions'].sort(key=lambda m: m['id'])
        recent = r.get('recent', rng.choice([True, False]))
        month = 10 if recent else 9
        october_start = 7 if any(m['theme'] == 'sh-bulk-upload' and m['post_ship'] for m in r['mentions']) else 4
        date = datetime(2026, month, rng.randint(october_start if recent else 1, 31 if recent else 30), rng.randint(8, 16), rng.randrange(60), tzinfo=timezone.utc)
        r['occurred_at'] = date.isoformat().replace('+00:00', 'Z')
        for mention in r['mentions']:
            mention['occurred_at'] = r['occurred_at']
    for i, record in enumerate(sales):
        record['turns_range'] = [40, 60] if seed == 42 and i < 8 else [15, 30]
    support = [r for r in records if r['route'] == 'support']
    resolved = 22 if seed == 42 else 9
    escalated = 12 if seed == 42 else 5
    resolved_records = [r for r in support if not r['mentions']][:resolved]
    if len(resolved_records) != resolved:
        raise ValueError('not enough noise-only support records for Fin resolutions')
    remaining = [r for r in support if r not in resolved_records]
    escalated_ids = {r['id'] for r in remaining[:escalated]}
    resolved_ids = {r['id'] for r in resolved_records}
    for i, record in enumerate(support):
        record['fin_mode'] = 'resolved' if record['id'] in resolved_ids else 'escalated' if record['id'] in escalated_ids else 'human'
        record['admin_note'] = i < (25 if seed == 42 else 10)
        record['required_noise'] = []
    for i, record in enumerate(resolved_records):
        record['required_noise'].append('password_reset' if i < (12 if seed == 42 else 5) else 'how_to')
    text_records = [r for r in records if r['source'] != 'fullstory']
    for record in text_records:
        record.setdefault('required_noise', [])
    for record in rng.sample(text_records, 45 if seed == 42 else 18):
        record['required_noise'].append('scheduling')
    for record in [r for r in sales if not any(m['theme'] == 'nz-renewal-pricing' for m in r['mentions'])][:6 if seed == 42 else 2]:
        record['required_noise'].append('pricing')
    for record in (sales[:2] + support[:2] + [r for r in records if r['source'] == 'fireflies'][:2])[:6 if seed == 42 else 3]:
        record['required_noise'].append('praise')
    how_to = [r for r in resolved_records if 'how_to' in r['required_noise']]
    for record in how_to[:2 if seed == 42 else 1]:
        record['distractor'] = spec['themes']['themes'][0]['synonyms'][0]
    eligible = [(r, m) for r in text_records for m in r['mentions'] if not m['theme'].startswith('one-off:')]
    for record, mention in eligible[:3 if seed == 42 else 1]:
        mention['agreement'] = True
    if seed == 42:
        personal = [r for r in support if not r['mentions']][:2]
        if len(personal) != 2:
            raise ValueError('Cannot place personal-domain join traps')
        for record in personal:
            record['join_trap'] = 'personal_email'
        next(r for r in sales if not r['mentions'])['join_trap'] = 'broker_and_customer'
        coverage = Counter((m['theme'], m['account']) for r in records for m in r['mentions'])
        ambiguous = next(r for r in records if r['source'] == 'fireflies' and len(r['mentions']) == 1
                         and coverage[(r['mentions'][0]['theme'], r['account'])] > 1
                         and not r['mentions'][0]['theme'].startswith('one-off:'))
        ambiguous['join_trap'] = 'two_customer_domains'
        ambiguous['other_account'] = next(a for a in customers if a != ambiguous['account'])
    return {'seed': seed, 'records': records, 'counts': dict(Counter(r['source'] for r in records)), 'estimated_usd': .50 if seed == 42 else .20}
