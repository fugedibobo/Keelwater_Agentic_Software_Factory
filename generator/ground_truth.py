"""Ground truth assembled only from the locators produced by each exporter."""
from __future__ import annotations

import hashlib
from .specs import load
from .writer import MODEL


def raw_hash(files):
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(files[path])
    return h.hexdigest()


def build(seed, files, mentions, false_positives=(), noise=(), join_traps=()):
    spec = load(seed)
    expected_ids = {m['id'] for m in mentions}
    if len(expected_ids) != len(mentions):
        raise ValueError('duplicate mention id')
    themes = []
    for theme in spec['themes']['themes']:
        public = {key: theme[key] for key in ('id', 'kind', 'title', 'bucket', 'severity', 'stances', 'product_ref', 'hard_negatives', 'expected')}
        public['mentions'] = sorted((m for m in mentions if m['theme'] == theme['id']), key=lambda m: m['id'])
        themes.append(public)
    for m in mentions:
        if m['theme'].startswith('one-off:'):
            themes.append({'id': m['theme'], 'kind': 'one_off', 'title': m['request'], 'severity': m['severity'], 'mentions': [m]})
    accounts = {a['key']: {'hubspot_id': str(18452001001 + i), 'name': a['name']} for i, a in enumerate(spec['accounts']['accounts'])}
    return {'schema_version': 1, 'generated': {'seed': seed, 'generator_version': '0.1.0', 'model': MODEL, 'raw_sha256': raw_hash(files)}, 'as_of': '2026-11-03', 'window': {'from': '2026-09-01', 'to': '2026-10-31'}, 'accounts': accounts, 'themes': themes, 'noise': list(noise), 'fullstory_false_positives': list(false_positives), 'join_traps': list(join_traps)}
