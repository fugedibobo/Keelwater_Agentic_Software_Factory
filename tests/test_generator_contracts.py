"""Offline source-contract and in-memory assembly checks with fake text."""
from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generator.brief import labels, mention_briefs
from generator.dataset import assemble_dataset, json_bytes
from generator.planner import plan
from generator.references import assemble_reference_files, briefs
from generator.source_schemas import schema_for, validate
from generator.specs import load

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / 'contracts' / 'sources'
if not SCHEMAS.is_dir():
    SCHEMAS = ROOT / '.scratch' / 'issue1' / 'contracts' / 'sources'


def fake_inputs(seed):
    spec = load(seed)
    themes = {t['id']: t for t in spec['themes']['themes']}
    responses = {}
    number = 0
    for record in plan(seed)['records']:
        if record['source'] == 'fullstory':
            continue
        turns = []
        for mention in record['mentions']:
            number += 1
            theme = themes.get(mention['theme'])
            term = next((b['synonym'] for b in mention_briefs(seed, record) if b['id'] == labels(record)[mention['id']] and 'synonym' in b), 'a small request')
            if mention.get('agreement'):
                turns.append({'speaker': 'internal', 'text': f'Could you confirm that the issue is {term} for the team today?', 'mention_ids': [], 'noise_category': None})
                text = 'Yes, that is right.'
            else:
                text = f'Here {term} aa{number} bb{number} cc{number} dd{number} ee{number} ff{number}.'
            turns.append({'speaker': 'customer', 'text': text, 'mention_ids': [mention['id']], 'noise_category': None})
        if not turns:
            turns.append({'speaker': 'customer', 'text': 'Here is a routine message about the service today.', 'mention_ids': [], 'noise_category': None})
        for category in record.get('required_noise', []):
            text = f"Here is a question about {record['distractor']} for the team today." if category == 'how_to' and record.get('distractor') else 'Here is a routine service request for the team today.'
            turns.append({'speaker': 'customer', 'text': text, 'mention_ids': [], 'noise_category': category})
        if record.get('fin_mode') in ('resolved', 'escalated'):
            turns.append({'speaker': 'bot', 'text': 'Here is some guidance for the requested task today.', 'mention_ids': [], 'noise_category': None})
        if record.get('admin_note') or record.get('fin_mode') == 'escalated':
            turns.append({'speaker': 'internal', 'text': 'We can review this request with the team today.', 'mention_ids': [], 'noise_category': 'internal' if record.get('admin_note') else None})
        while record.get('turns_range') and len(turns) < record['turns_range'][0]:
            turns.append({'speaker': 'internal', 'text': 'We can discuss the details during our meeting today.', 'mention_ids': [], 'noise_category': None})
        responses[record['id']] = {'turns': turns}
    references = assemble_reference_files({b['key']: 'A routine description of the work.' for b in briefs()})
    files = {'shortcut/stories.json': json_bytes({'stories': references['stories']}),
             'notion/pages.json': json_bytes({'results': references['pages']})}
    return responses, files


@pytest.mark.parametrize('seed', [42, 43])
def test_every_assembled_source_matches_issue_one_schemas(seed):
    if not SCHEMAS.is_dir():
        pytest.skip('issue #1 source contracts are unavailable')
    responses, references = fake_inputs(seed)
    raw, truth = assemble_dataset(seed, responses, references, lambda name, data: validate(name, data, SCHEMAS))
    from jsonschema import Draft202012Validator
    validators = {}
    for name, data in raw.items():
        schema_name, per_row = schema_for(name)
        if schema_name not in validators:
            schema = json.loads((SCHEMAS / f'{schema_name}.schema.json').read_text(encoding='utf-8'))
            Draft202012Validator.check_schema(schema)
            validators[schema_name] = Draft202012Validator(schema)
        value = [json.loads(line) for line in data.decode('utf-8').splitlines() if line] if name.endswith('.ndjson') else json.loads(data)
        for item in value if per_row else [value]:
            validators[schema_name].validate(item)
    assert len([p for p in raw if p.startswith('intercom/')]) == (60 if seed == 42 else 24)
    assert len([p for p in raw if p.startswith('fireflies/')]) == (22 if seed == 42 else 8)
    assert truth['generated']['seed'] == seed


def test_schema_validator_rejects_missing_fields_and_unknown_keywords():
    from generator.source_schemas import _validate_subset
    with pytest.raises(ValueError, match='missing id'):
        _validate_subset({}, {'type': 'object', 'required': ['id']})
    with pytest.raises(ValueError, match='unsupported'):
        _validate_subset('abc', {'type': 'string', 'minLength': 9})


def test_intercom_tags_are_informative_but_not_perfect():
    from generator.assemble import assemble
    responses, _ = fake_inputs(42)
    buckets = {t['id']: t['bucket'] for t in load(42)['themes']['themes']}
    matches = []
    for record in plan(42)['records']:
        if record['source'] != 'intercom':
            continue
        expected = next((buckets.get(m['theme']) for m in record['mentions'] if buckets.get(m['theme'])), None)
        if expected:
            raw, _ = assemble(record, responses[record['id']], 42)
            matches.append(raw['tags']['tags'][0]['name'] == expected)
    assert len(matches) >= 10
    assert .4 <= sum(matches) / len(matches) <= .9
