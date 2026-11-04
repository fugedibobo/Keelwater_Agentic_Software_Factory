"""Validate private tagged model responses before building public records.

The caller supplies a gateway adapter. This module does not access a network
or read credentials, and it does not record pipeline model_call rows.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from signal_engine import config
from signal_engine.gateway import InvalidResponse
from .brief import make_prompt, mention_briefs
from .specs import ROOT, load
from .verify import leaked_terms, repeated_record_ids, unknown_names, verify_mention_text

MODEL = config.load('models')['profiles']['demo']['stages']['generate']['model']
TURN_ITEM = {
    'type': 'object', 'additionalProperties': False, 'required': ['speaker', 'text', 'noise_category'],
    'properties': {'speaker': {'type': 'string', 'enum': ['customer', 'internal', 'bot']}, 'text': {'type': 'string'},
                   'noise_category': {'type': ['string', 'null']}}
}


def bounded(slot, mention, synonym=None):
    """A plain mention is a customer text of at least 45 characters. A short agreement is an internal turn of at least
    45 characters that states the problem (carries the pinned phrase) plus a customer agreement of at most 44."""
    slot = copy.deepcopy(slot)
    props = slot['properties']
    if mention.get('agreement'):
        del props['text']
        props['internal_text'] = {'type': 'string', 'minLength': 45}
        props['agreement_text'] = {'type': 'string', 'maxLength': 44}
        slot['required'] = ['internal_text', 'agreement_text', 'after_turn']
    else:
        props['text']['minLength'] = 45
    return slot


def record_schema(record, seed):
    """Per-record response schema. `turns` holds the conversation without the planted mentions (band minus the
    mention count, noise enum); `mentions` has exactly this record's mention ids, each one customer text plus a
    placement hint. Code inserts and tags them (merge_mentions), so one tag per mention holds by construction."""
    n = sum(2 if m.get('agreement') else 1 for m in record['mentions'])  # an agreement adds an internal turn too
    syn = {b['id']: b['synonym'] for b in mention_briefs(seed, record) if 'synonym' in b}
    item = copy.deepcopy(TURN_ITEM)
    item['properties']['noise_category'] = {'enum': [*load(seed)['noise']['categories'], None]}
    turns = {'type': 'array', 'items': item}
    if record.get('turns_range'):
        turns['minItems'], turns['maxItems'] = (max(0, x - n) for x in record['turns_range'])
    slot = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'after_turn'],
            'properties': {'text': {'type': 'string'}, 'after_turn': {'type': 'integer'}}}
    ids = [m['id'] for m in record['mentions']]
    return {'type': 'object', 'additionalProperties': False, 'required': ['turns', 'mentions'],
            'properties': {'turns': turns, 'mentions': {'type': 'object', 'additionalProperties': False, 'required': ids,
                                                         'properties': {m['id']: bounded(slot, m, syn.get(m['id'])) for m in record['mentions']}}}}


def merge_mentions(record, raw, seed=None):
    """Insert each mention slot after its hinted turn (clamped), deterministic by position then mention order. A plain
    mention becomes one tagged customer turn. A short-agreement mention becomes an internal turn stating the problem
    (it must carry the pinned phrase) followed by the tagged customer agreement."""
    base = [{**t, 'mention_ids': []} for t in raw.get('turns', [])]
    pinned = {b['id']: b['synonym'] for b in mention_briefs(seed, record) if 'synonym' in b} if seed is not None else {}
    inserts = []
    for order, m in enumerate(record['mentions']):
        slot = raw['mentions'][m['id']]
        carrier = slot['internal_text'] if m.get('agreement') else slot['text']
        term = pinned.get(m['id'])
        if term and term.casefold() not in carrier.casefold():  # code-side guard: the pinned synonym only, no splicing
            raise RecordValidationError(f"{record['id']}: mention {m['id']} lacks the required phrase '{term}'")
        pos = min(max(slot['after_turn'], 0), max(len(base) - 1, 0))
        if m.get('agreement'):
            group = [{'speaker': 'internal', 'text': slot['internal_text'], 'mention_ids': [], 'noise_category': None},
                     {'speaker': 'customer', 'text': slot['agreement_text'], 'mention_ids': [m['id']], 'noise_category': None}]
        else:
            group = [{'speaker': 'customer', 'text': slot['text'], 'mention_ids': [m['id']], 'noise_category': None}]
        inserts.append((pos, order, group))
    turns = []
    queue = sorted(inserts, key=lambda x: x[:2])
    for i, t in enumerate(base):
        turns.append(t)
        for x in queue:
            if x[0] == i:
                turns.extend(x[2])
    if not base:
        for x in queue:
            turns.extend(x[2])
    return {'turns': turns}


DESCRIPTION_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['description'],
                      'properties': {'description': {'type': 'string'}}}


def request_parameters(record, seed, attempt):
    """Describe a generator call for the issue #1 gateway adapter."""
    return {'stage': 'generate', 'model': MODEL, 'temperature': .8,
            'cache_dir': ROOT / 'generator' / 'cache',
            'prompt': make_prompt(seed, record), 'attempt': attempt}


class RecordValidationError(ValueError):
    pass


def validate_response(record, response, seed):
    if not isinstance(response, dict) or not isinstance(response.get('turns'), list):
        raise RecordValidationError('expected an object with a turns list')
    required = {m['id'] for m in record['mentions']}
    seen = []
    categories = set(load(seed)['noise']['categories'])
    if record.get('turns_range') and not record['turns_range'][0] <= len(response['turns']) <= record['turns_range'][1]:
        raise RecordValidationError(f"{record['id']}: turn count outside the requested range")
    for index, turn in enumerate(response['turns']):
        if not isinstance(turn, dict) or turn.get('speaker') not in ('customer', 'internal', 'bot') or not isinstance(turn.get('text'), str):
            raise RecordValidationError('invalid turn')
        names = unknown_names(turn['text'], seed)
        if names:
            raise RecordValidationError(f"{record['id']}: unknown name {names[0]}")
        tags = turn.get('mention_ids', [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise RecordValidationError('invalid mention tags')
        category = turn.get('noise_category')
        if category is not None and category not in categories:
            raise RecordValidationError('unknown noise category')
        if tags and category:
            raise RecordValidationError('a mention turn cannot also be labelled noise')
        has_context = index > 0 and response['turns'][index - 1].get('speaker') == 'internal'
        if tags and (turn['speaker'] != 'customer' or (len(turn['text'].split()) < 8 and not has_context)):
            raise RecordValidationError('a mention must be in a customer turn of at least eight words or a short agreement after an internal turn')
        seen.extend(tags)
    if Counter(seen) != Counter(required):
        raise RecordValidationError('mention tags are missing, duplicated or unknown')
    if record.get('fin_mode') in ('resolved', 'escalated') and not any(t['speaker'] == 'bot' for t in response['turns']):
        raise RecordValidationError('Fin conversation has no bot turn')
    if record.get('fin_mode') == 'escalated' and not any(t['speaker'] == 'internal' for t in response['turns']):
        raise RecordValidationError('escalated conversation has no internal reply')
    if record.get('fin_mode') == 'human' and any(t['speaker'] == 'bot' for t in response['turns']):
        raise RecordValidationError('human-only conversation has a bot turn')
    if record.get('admin_note') and not any(t['speaker'] == 'internal' and t.get('noise_category') == 'internal' for t in response['turns']):
        raise RecordValidationError('missing admin note')
    if record.get('source') == 'intercom' and not record.get('admin_note') and any(t['speaker'] == 'internal' and t.get('noise_category') == 'internal' for t in response['turns']):
        raise RecordValidationError('unexpected admin note')
    if any(not any(t.get('noise_category') == category for t in response['turns']) for category in record.get('required_noise', [])):
        raise RecordValidationError('missing required noise category')
    if record.get('distractor') and not any(record['distractor'].casefold() in t['text'].casefold() and t.get('noise_category') == 'how_to' and not t.get('mention_ids') for t in response['turns']):
        raise RecordValidationError('missing non-themed how-to distractor')
    for mention in record['mentions']:
        if mention.get('agreement'):
            positions = [i for i, t in enumerate(response['turns']) if mention['id'] in t.get('mention_ids', [])]
            if not positions or positions[0] == 0 or response['turns'][positions[0] - 1]['speaker'] != 'internal' or len(response['turns'][positions[0]]['text'].split()) >= 8:
                raise RecordValidationError('missing short customer agreement after internal summary')
    return response


def write_record(record, seed, make_request, start_attempt=0, on_rejection=None):
    """Try at most three responses; the adapter enforces its own USD cap.

    make_request(record, attempt) must use gateway.chat with the generate
    stage and generator/cache. No calls are made until a caller supplies it.
    """
    last = None
    for attempt in range(start_attempt, 3):
        try:
            response = validate_response(record, make_request(record, attempt), seed)
            errors = verify_mention_text(seed, [(record, response)])
            for turn in response['turns']:
                for scan_seed in (42, 43):
                    terms = leaked_terms(scan_seed, turn['text'], include_synonyms=False)
                    if terms:
                        errors.append(f"{record['id']}: forbidden raw phrase {terms[0]}")
            if errors:
                raise RecordValidationError('; '.join(errors))
            return response
        except (RecordValidationError, InvalidResponse) as exc:
            last = exc
            FEEDBACK[record['id']] = str(exc)
            if on_rejection:
                on_rejection(record['id'], attempt, str(exc))
    raise RecordValidationError(f"{record['id']}: failed after two regenerations: {last}")


FEEDBACK = {}  # record id -> last rejection text, set by write_record and read by gateway_request


def feedback_text(record, seed, error):
    """State the failed rule, the offending text and the allowed values so a regeneration can fix it."""
    if not error:
        return ''
    lines = [f'Your previous attempt was rejected: {error}']
    for b in mention_briefs(seed, record):
        if 'synonym' in b:
            lines.append(f"Mention {b['id']} must contain the exact phrase '{b['synonym']}'.")
    never = re.search(r'forbidden raw phrase (.+)', error)
    if never:
        lines.append(f"Do not write the phrase '{never.group(1)}'; paraphrase it.")
    name = re.search(r'unknown name (.+?)(?:;|$)', error)
    if name:
        people = re.search(r'only_people_who_may_be_named": \[(.*?)\]', make_prompt(seed, record))
        lines.append(f"'{name.group(1)}' is not an allowed name; use only: {people.group(1) if people else 'the names in the record brief'}.")
    return '\n'.join(lines) + '\n'


def gateway_request(gateway, record, seed, attempt):
    """Adapter for issue #1's Gateway.chat; no store is attached by the caller."""
    request = request_parameters(record, seed, attempt)
    prompt = request['prompt']
    if attempt:
        prompt += f'\nRegeneration {attempt}: rewrite the record, satisfy every rule, and return the full JSON again.\n' + feedback_text(record, seed, FEEDBACK.get(record['id']))
    raw = gateway.chat('generate', [{'role': 'user', 'content': prompt}], target_type='generator_record',
                        target_id=record['id'], prompt_version='record@0.2.0', schema=record_schema(record, seed))
    return merge_mentions(record, raw, seed)


def write_reference(gateway, brief, seed, on_rejection=None):
    """Generate a short reference description using the same gateway and cache."""
    import json
    last = None
    for attempt in range(3):
        prompt = ('Write one short realistic description for this fictional claims software item. '
                  'Use no company, person or product name except Keelwater. Return JSON.\n' +
                  json.dumps(brief, ensure_ascii=False, sort_keys=True) + f'\nVersion {attempt}\n')
        try:
            response = gateway.chat('generate', [{'role': 'user', 'content': prompt}],
                                    target_type='generator_reference', target_id=brief['key'],
                                    prompt_version='reference@0.1.0', schema=DESCRIPTION_SCHEMA)
        except InvalidResponse as exc:
            last = str(exc)
            if on_rejection: on_rejection(brief['key'], attempt, last)
            continue
        text = response.get('description') if isinstance(response, dict) else None
        if not isinstance(text, str) or not text.strip():
            last = 'missing description'
            if on_rejection: on_rejection(brief['key'], attempt, last)
            continue
        names = unknown_names(text, seed)
        leaks = [term for scan_seed in (42, 43) for term in leaked_terms(scan_seed, text, include_synonyms=False)]
        if names or leaks:
            last = f'unknown name {names[0]}' if names else f'forbidden raw phrase {leaks[0]}'
            if on_rejection: on_rejection(brief['key'], attempt, last)
            continue
        return text
    raise RecordValidationError(f"{brief['key']}: failed after two regenerations: {last}")


def write_all(records, seed, make_request, on_rejection=None):
    """Write text records with at most eight concurrent adapter calls.

    The adapter must enforce the shared budget across threads and perform
    cache lookup before any network access. Responses retain private tags
    until source assembly and verification are complete.
    """
    text_records = [r for r in records if r['source'] != 'fullstory']
    if len({r['id'] for r in text_records}) != len(text_records):
        raise ValueError('duplicate record ID')
    attempts = {r['id']: 0 for r in text_records}
    def counted(record, attempt):
        attempts[record['id']] = attempt + 1
        return make_request(record, attempt)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {r['id']: executor.submit(write_record, r, seed, counted, 0, on_rejection) for r in text_records}
        try:
            results = {record_id: future.result() for record_id, future in futures.items()}
        except Exception:
            for future in futures.values():
                future.cancel()
            raise
    by_id = {record['id']: record for record in text_records}
    while True:
        repeated = repeated_record_ids(text_records, results)
        if not repeated:
            return results
        for record_id in repeated:
            if attempts[record_id] >= 3:
                raise RecordValidationError(f'{record_id}: repeated six-word phrase after two regenerations')
            if on_rejection:
                on_rejection(record_id, attempts[record_id] - 1, 'repeated six-word phrase')
            results[record_id] = write_record(by_id[record_id], seed, counted, attempts[record_id], on_rejection)
