"""Entry point registered by the main CLI once issue #1 is integrated."""
from __future__ import annotations

import argparse
from collections import Counter
import json

from .planner import VOLUMES, plan
from .specs import load


def main(argv=None):
    parser = argparse.ArgumentParser(prog='keelwater generate')
    parser.add_argument('--seed', type=int, choices=(42, 43), default=42)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--max-usd', type=float)
    args = parser.parse_args(argv)
    p = plan(args.seed)
    if not args.dry_run:
        from .runner import run
        run(args.seed, force=args.force, max_usd=args.max_usd)
        return 0
    records = p['records']
    routes = Counter(r['route'] for r in records)
    print(f'Seed {args.seed} plan')
    print('Records: ' + ', '.join(f'{k}={v}' for k, v in VOLUMES[args.seed].items()))
    text_count = sum(routes[k] for k in ('sales', 'support', 'onboarding', 'account_management'))
    if args.seed == 42:
        text_count += 22  # Shortcut and Notion are reused by the held-out set.
    print(f'Text records: {text_count}')
    print(f"Fireflies: onboarding={routes['onboarding']}, account_management={routes['account_management']}")
    for theme in load(args.seed)['themes']['themes']:
        mentions = [m for r in records for m in r['mentions'] if m['theme'] == theme['id']]
        per_route = Counter(r['route'] for r in records for m in r['mentions'] if m['theme'] == theme['id'])
        months = Counter(m['occurred_at'][:7] for m in mentions)
        print(f"{theme['id']}: {len(mentions)} routes={json.dumps(dict(sorted(per_route.items())), sort_keys=True)} months={json.dumps(dict(sorted(months.items())), sort_keys=True)}")
    one_offs = [(r, m) for r in records for m in r['mentions'] if m['theme'].startswith('one-off:')]
    one_off_routes = Counter(r['route'] for r, _ in one_offs)
    one_off_months = Counter(m['occurred_at'][:7] for _, m in one_offs)
    print(f"One-offs: {len(one_offs)} routes={json.dumps(dict(sorted(one_off_routes.items())), sort_keys=True)} months={json.dumps(dict(sorted(one_off_months.items())), sort_keys=True)}")
    print(f"Estimated cost: USD {p['estimated_usd']:.2f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
