"""Code-only HubSpot company export; values and domains are synthetic."""
from __future__ import annotations

from datetime import datetime
from .specs import load


def companies():
    spec = load(42)['accounts']
    accounts = spec['accounts']
    duplicates = {item['account']: item for item in spec['hubspot_duplicates']}
    mess = spec['hubspot_mess']
    rows = []
    for i, a in enumerate(accounts, start=1):
        arr = a['arr_gbp']
        if arr is None:
            formatted = None
        elif i % 4 == 0:
            formatted = f'{arr:,}'
        elif i % 4 == 1:
            formatted = str(arr)
        elif i % 4 == 2:
            formatted = f'{arr:.2f}'
        else:
            formatted = f'£{arr / 1000:g}k'
        renewal = a['renewal']
        if renewal is not None:
            renewal = datetime.strptime(renewal, '%d/%m/%Y').date().isoformat()
        properties = {'name': a['name'], 'domain': a['key'].lower() + '.example',
                      'lifecyclestage': 'opportunity' if arr is None else 'customer',
                      'keelwater_arr_gbp': formatted,
                      'annualrevenue': str(arr * mess['default_revenue_multiplier']) if arr is not None else None,
                      'keelwater_tier': ('enterprise' if a['key'] == mess['lowercase_tier_account'] else a['tier']),
                      'renewal_date': renewal, 'hs_lastmodifieddate': '2026-10-31T12:00:00Z'}
        rows.append({'id': str(18452001000 + i), 'properties': properties})
        if a['key'] in duplicates:
            duplicate = duplicates[a['key']]
            stale = {**properties, 'keelwater_arr_gbp': str(arr - duplicate['arr_decrement_gbp']), 'hs_lastmodifieddate': duplicate['last_modified']}
            rows.append({'id': str(18452002000 + i), 'properties': stale})
    return {'results': sorted(rows, key=lambda r: r['id'])}
