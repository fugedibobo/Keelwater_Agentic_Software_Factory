"""Checks that fail closed before synthetic data can be emitted."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from .specs import load


def verify_plan(plan: dict) -> list[str]:
    seed = plan['seed']
    spec = load(seed)
    errors = []
    records = plan['records']
    for record in records:
        if len(record['mentions']) > 3:
            errors.append(f"{record['id']}: more than three mentions")
        if any(n > 2 for n in Counter(m['theme'] for m in record['mentions']).values()):
            errors.append(f"{record['id']}: more than two mentions of a theme")
        if len({m['occurred_at'] for m in record['mentions']}) > 1:
            errors.append(f"{record['id']}: inconsistent dates")
        if any(m['account'] != record['account'] for m in record['mentions']):
            errors.append(f"{record['id']}: inconsistent account")
    for theme in spec['themes']['themes']:
        matched = [(r, m) for r in records for m in r['mentions'] if m['theme'] == theme['id']]
        actual = Counter(r['route'] for r, _ in matched)
        if any(actual[route] != count for route, count in theme['routes'].items()):
            errors.append(f"{theme['id']}: route counts differ")
        if {m['account'] for _, m in matched} != set(theme['accounts']):
            errors.append(f"{theme['id']}: account coverage differs")
        if seed == 42 and theme['kind'] == 'real':
            months = Counter(m['occurred_at'][:7] for _, m in matched)
            if min(months['2026-09'], months['2026-10']) < 3:
                errors.append(f"{theme['id']}: insufficient monthly coverage")
    return errors


def unknown_names(text: str, seed: int = 42) -> list[str]:
    """# shortcut: capitalisation heuristic, upgrade to an NER pass if a real export is ever generated from.

    Return unknown capitalised tokens away from sentence starts. This is a
    conservative check and will also flag unlisted common words.
    """
    spec = load(seed)
    allowed_text = ' '.join(str(spec[k]) for k in ('accounts', 'people', 'glossary'))
    allowed = set(re.findall(r"[A-Z][a-z]+", allowed_text))
    allowed.update('January February March April May June July August September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday London Welsh UK Yes No The Keelwater'.split())
    allowed_names = {a['name'] for a in spec['accounts']['accounts']}
    allowed_names.update(p['name'] for p in spec['people']['staff'] + spec['people']['customer_contacts'])
    allowed_names.update(p['name'] for p in spec['people'].get('brokers', []))
    unknown = []
    for match in re.finditer(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text):
        prefix = text[:match.start()].rstrip()
        words = match.group().split()
        if not prefix or prefix[-1] in '.!?':
            words = words[1:]
        phrase = ' '.join(words)
        if words and (any(word not in allowed for word in words) or (len(words) > 1 and phrase not in allowed_names)):
            unknown.append(phrase)
    return unknown


def validate_source_file(path: Path, schema: dict) -> None:
    """Validate JSON with issue #1's schemas after that dependency exists."""
    import json
    import jsonschema
    value = json.loads(path.read_text(encoding='utf-8'))
    jsonschema.validate(value, schema)


def verify_mention_text(seed: int, records_and_responses) -> list[str]:
    """Check mention words, synonym evidence, and repeated six-word spans."""
    themes = {t['id']: t for t in load(seed)['themes']['themes']}
    spans = {}
    errors = []
    for record, response in records_and_responses:
        lookup = {m['id']: m for m in record['mentions']}
        turns = response.get('turns', [])
        for i, turn in enumerate(turns):
            for mention_id in turn.get('mention_ids', []):
                mention = lookup.get(mention_id)
                if mention is None:
                    errors.append(f"{record['id']}: unknown mention {mention_id}")
                    continue
                text = turn['text']
                if turn.get('speaker') != 'customer':
                    errors.append(f"{record['id']}: mention is not a customer turn")
                context = ''
                if len(text.split()) < 8:
                    if i and turns[i - 1].get('speaker') == 'internal':
                        context = turns[i - 1]['text']
                    else:
                        errors.append(f"{record['id']}: short mention without internal context")
                theme = themes.get(mention['theme'])
                if theme and not any(term.casefold() in text.casefold() for term in theme['synonyms']):
                    errors.append(f"{record['id']}: mention {mention_id} lacks a synonym")
                words = re.findall(r"[\w']+", text.casefold())
                for span in {tuple(words[n:n + 6]) for n in range(len(words) - 5)}:
                    spans.setdefault((mention['theme'], span), set()).add(mention_id)
    for (theme, _), ids in spans.items():
        if len(ids) > 2:
            errors.append(f'{theme}: six-word span occurs in {len(ids)} mentions')
    return errors


def repeated_record_ids(records, responses):
    """Identify the third and later mentions sharing a theme's six-word span."""
    spans = {}
    for record in records:
        lookup = {m['id']: m for m in record['mentions']}
        for turn in responses[record['id']]['turns']:
            words = re.findall(r"[\w']+", turn['text'].casefold())
            for mention_id in turn.get('mention_ids', []):
                mention = lookup[mention_id]
                for span in {tuple(words[n:n + 6]) for n in range(len(words) - 5)}:
                    spans.setdefault((mention['theme'], span), set()).add((mention_id, record['id']))
    return sorted({record_id for mentions in spans.values() if len(mentions) > 2
                   for _, record_id in sorted(mentions)[2:]})


def leaked_terms(seed: int, text: str, include_synonyms: bool = True) -> list[str]:
    """Return all planted title, fact and synonym strings in exposed text."""
    terms = []
    for theme in load(seed)['themes']['themes']:
        for term in [theme['id'], theme['title'], *theme['facts'], *(theme['synonyms'] if include_synonyms else [])]:
            if term and term.casefold() in text.casefold():
                terms.append(term)
    return terms
