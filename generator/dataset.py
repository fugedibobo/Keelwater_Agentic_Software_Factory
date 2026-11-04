"""Assemble an in-memory dataset; validation must pass before any emit step."""
from __future__ import annotations

import json
from .assemble import assemble
from .fullstory import build as build_fullstory
from .ground_truth import build as build_truth
from .hubspot import companies
from .planner import plan
from .verify import leaked_terms, verify_mention_text, verify_plan


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def assemble_dataset(seed, responses, references, validate_source):
    """Build a dataset in memory and fail closed on any verification error.

    `responses` maps planned text record IDs to tagged responses. `references`
    contains raw Shortcut and Notion JSON bytes (reused unchanged for seed 43).
    `validate_source` must validate a source filename and its bytes against the
    corresponding issue #1 schema, raising on error.
    """
    p = plan(seed)
    errors = verify_plan(p)
    if errors:
        raise ValueError('; '.join(errors))
    records = [r for r in p['records'] if r['source'] != 'fullstory']
    if set(responses) != {r['id'] for r in records}:
        raise ValueError('responses do not match the planned text records')
    expected_refs = {'shortcut/stories.json', 'notion/pages.json'}
    if set(references) != expected_refs or any(not isinstance(v, bytes) for v in references.values()):
        raise ValueError('Shortcut and Notion reference files are required')
    errors = verify_mention_text(seed, [(r, responses[r['id']]) for r in records])
    if errors:
        raise ValueError('; '.join(errors))
    raw, truth, noise = dict(references), [], []
    calls, transcripts = [], []
    for r in records:
        raw_record, labelled, noise_units = assemble(r, responses[r['id']], seed, include_noise=True)
        truth.extend(labelled)
        noise.extend(noise_units)
        if r['source'] == 'gong':
            calls.append(raw_record['call'])
            transcripts.append(raw_record['transcript'])
        else:
            raw[f"{r['source']}/{r['id']}.json"] = json_bytes(raw_record)
    calls.sort(key=lambda c: c['metaData']['id'])
    transcripts.sort(key=lambda c: c['callId'])
    raw['gong/calls.json'] = json_bytes({'calls': calls})
    raw['gong/transcripts.json'] = json_bytes({'callTranscripts': transcripts})
    fs = build_fullstory(p['records'])
    raw['fullstory/sessions.json'] = json_bytes(fs['sessions'])
    raw['fullstory/events.ndjson'] = b''.join((json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8') for event in fs['events'])
    raw['hubspot/companies.json'] = json_bytes(companies())
    truth.extend(fs['mentions'])
    planned_ids = {m['id'] for r in p['records'] for m in r['mentions']}
    if {m['id'] for m in truth} != planned_ids or len(truth) != len(planned_ids):
        raise ValueError('ground truth does not cover every planned mention exactly once')
    for name, data in raw.items():
        validate_source(name, data)
        for scan_seed in (42, 43):
            if leaked_terms(scan_seed, data.decode('utf-8'), include_synonyms=False):
                raise ValueError(f'{name}: planted term present in raw output')
    traps = [{'source': r['source'], 'source_id': r['id'], 'expected_account': None if r['join_trap'] in ('personal_email', 'two_customer_domains') else r['account'], 'reason': r['join_trap']} for r in records if 'join_trap' in r]
    if seed == 42:
        traps.extend([{'source': 'hubspot', 'source_id': str(18452002000 + int(key[1:])), 'expected_account': key, 'reason': 'stale duplicate'} for key in ('A06', 'A15')])
    return raw, build_truth(seed, raw, truth, fs['false_positives'], noise=noise, join_traps=traps)
