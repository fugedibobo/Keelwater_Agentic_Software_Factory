from collections import Counter
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from signal_engine import config
from generator.cli import main
from generator.assemble import assemble
from generator.brief import make_prompt
from generator.dataset import assemble_dataset
from generator.fullstory import build
from generator.ground_truth import raw_hash
from generator.hubspot import companies
from generator.planner import plan
from generator.references import assemble_reference_files, briefs
from generator.scoring import score
from generator.specs import load
from generator.verify import leaked_terms, unknown_names, verify_mention_text, verify_plan
from generator.writer import RecordValidationError, request_parameters, write_all, write_record


@pytest.mark.parametrize('seed,text_count', [(42, 129), (43, 42)])
def test_dry_run(seed, text_count, capsys):
    assert main(['--seed', str(seed), '--dry-run']) == 0
    out = capsys.readouterr().out
    assert f'Text records: {text_count}' in out
    assert 'Estimated cost: USD ' in out


@pytest.mark.parametrize('seed', [42, 43])
def test_plan_is_reproducible_and_matches_spec(seed):
    first = plan(seed)
    assert first == plan(seed)
    assert verify_plan(first) == []
    assert len({r['id'] for r in first['records']}) == len(first['records'])


def test_check_detects_missing_mention():
    p = plan(42)
    next(r for r in p['records'] if r['mentions'])['mentions'].pop()
    assert verify_plan(p)


def test_hubspot_has_the_mess_and_total():
    rows = companies()['results']
    assert len(rows) == 36
    names = Counter(r['properties']['name'] for r in rows)
    assert sorted(names.values()).count(2) == 2
    spec = load(42)['accounts']['accounts']
    assert sum(a['arr_gbp'] or 0 for a in spec) == 15440000
    assert next(a for a in spec if a['key'] == 'A22')['renewal'] is None
    assert any(r['properties']['keelwater_tier'] == 'enterprise' for r in rows)
    assert all(r['properties']['domain'].endswith('.example') for r in rows)


def test_fullstory_long_sessions_and_locators():
    built = build(plan(42)['records'])
    assert len(built['sessions']) == 40
    assert len(built['events']) == 1200
    assert len(built['false_positives']) == 11
    assert {event['event_type'] for event in built['events']} == {'click', 'page_view'}
    assert len({event['source_properties']['page_name'] for event in built['events']}) > 3
    events = {e['event_id']: e for e in built['events']}
    for m in built['mentions']:
        assert events[m['locator']['event_ids'][0]]['session_id'] == m['source_id']
    for session in built['sessions'][:10]:
        times = [datetime.fromisoformat(e['event_time'].replace('Z', '+00:00')) for e in built['events'] if e['session_id'] == session['sessionId']]
        duration = (times[-1] - times[0]).total_seconds()
        largest_gap = max((b-a).total_seconds() for a, b in zip(times, times[1:]))
        assert duration > 90 * 60 and largest_gap / duration >= .8


def test_unknown_name_is_flagged():
    assert 'Brackenford Mutual' in unknown_names('We heard from Brackenford Mutual today.')
    assert not unknown_names('We heard from Hollinbrook Home Insurance today.')
    assert 'Hollinbrook Mutual' in unknown_names('The Hollinbrook Mutual team is waiting.')


def test_record_brief_is_seeded_and_has_exact_mention_ids():
    r = next(r for r in plan(42)['records'] if r['mentions'] and r['source'] != 'fullstory')
    prompt = make_prompt(42, r)
    assert prompt == make_prompt(42, r)
    assert all(m['id'] in prompt for m in r['mentions'])
    request = request_parameters(r, 42, 0)
    assert request['stage'] == 'generate' and request['temperature'] == .8
    assert request['model'] == config.load('models')['profiles']['demo']['stages']['generate']['model']


def test_writer_retries_and_fails_closed():
    r = {'id': 'name-test', 'source': 'intercom', 'mentions': []}
    calls = []
    def request(record, attempt):
        calls.append(attempt)
        return {'turns': [{'speaker': 'customer', 'text': 'We heard from Brackenford Mutual about the issue today.', 'mention_ids': []}]}
    with pytest.raises(RecordValidationError, match='Brackenford'):
        write_record(r, 42, request)
    assert calls == [0, 1, 2]


def test_writer_batches_in_record_order():
    records = [{'id': 'b', 'source': 'intercom', 'mentions': []}, {'id': 'a', 'source': 'gong', 'mentions': []}]
    responses = write_all(records, 42, lambda record, attempt: {'turns': [{'speaker': 'customer', 'text': 'A routine message.', 'mention_ids': []}]})
    assert list(responses) == ['b', 'a']


@pytest.mark.parametrize('source', ['gong', 'intercom', 'fireflies'])
def test_assembly_keeps_real_locator_and_removes_private_tags(source):
    r = next(r for r in plan(42)['records'] if r['source'] == source and r['mentions'] and not any(m.get('agreement') for m in r['mentions']))
    response = {'turns': [{'speaker': 'customer', 'text': 'We have spent many hours trying to resolve this particular issue.', 'mention_ids': [m['id'] for m in r['mentions']]}]}
    for category in r.get('required_noise', []):
        text = f"A question about {r['distractor']} for the service desk." if category == 'how_to' and r.get('distractor') else 'A routine request for the service desk.'
        response['turns'].append({'speaker': 'customer', 'text': text, 'mention_ids': [], 'noise_category': category})
    if r.get('fin_mode') in ('resolved', 'escalated'):
        response['turns'].append({'speaker': 'bot', 'text': 'Here is the guidance for the team.', 'mention_ids': []})
    if r.get('admin_note') or r.get('fin_mode') == 'escalated':
        response['turns'].append({'speaker': 'internal', 'text': 'We can review this with the team.', 'mention_ids': [], 'noise_category': 'internal' if r.get('admin_note') else None})
    while r.get('turns_range') and len(response['turns']) < r['turns_range'][0]:
        response['turns'].append({'speaker': 'internal', 'text': 'We can review the matter later.', 'mention_ids': []})
    raw, truth = assemble(r, response, 42)
    assert len(truth) == len(r['mentions'])
    assert all(m['source_id'] == r['id'] and m['at_ms'] == 0 for m in truth)
    assert 'mention_ids' not in str(raw)


def test_raw_hash_uses_sorted_paths():
    assert raw_hash({'b': b'2', 'a': b'1'}) == raw_hash({'a': b'1', 'b': b'2'})
    assert raw_hash({'a': b'1', 'b': b'2'}) != raw_hash({'a': b'2', 'b': b'1'})


def test_synonym_is_required_in_raw_but_banned_in_config():
    p = plan(42)
    r = next(r for r in p['records'] if any(m['theme'] == 'rt-doc-type-misfile' for m in r['mentions']))
    m = next(m for m in r['mentions'] if m['theme'] == 'rt-doc-type-misfile')
    text = 'Our wrong document category creates delays for several teams today.'
    assert verify_mention_text(42, [(r, {'turns': [{'speaker': 'customer', 'text': text, 'mention_ids': [m['id']]}]})]) == []
    assert 'wrong document category' in leaked_terms(42, text)
    assert 'wrong document category' not in leaked_terms(42, text, include_synonyms=False)


def test_repeated_six_word_phrase_is_detected_across_mentions():
    p = plan(42)
    chosen = [(r, m) for r in p['records'] for m in r['mentions'] if m['theme'] == 'rt-doc-type-misfile'][:3]
    samples = [(r, {'turns': [{'speaker': 'customer', 'text': 'Our wrong document category creates delays for several teams today.', 'mention_ids': [m['id']]}]}) for r, m in chosen]
    assert any('six-word span' in error for error in verify_mention_text(42, samples))


def test_ship_dates_and_one_offs():
    p = plan(42)
    mentions = [m for r in p['records'] for m in r['mentions']]
    shipped = [m for m in mentions if m['theme'] == 'sh-bulk-upload']
    assert sum(m['post_ship'] for m in shipped) == 2
    assert all((m['occurred_at'] >= '2026-10-06T00:00:00Z') == m['post_ship'] for m in shipped)
    assert sum(m['theme'].startswith('one-off:') for m in mentions) == 10


def test_seed_42_source_mix_and_join_traps():
    records = plan(42)['records']
    sales = [r for r in records if r['route'] == 'sales']
    support = [r for r in records if r['route'] == 'support']
    assert sum(r['account'].startswith('P') for r in sales) == 7
    assert sum(r['turns_range'] == [40, 60] for r in sales) == 8
    assert Counter(r['fin_mode'] for r in support) == {'resolved': 22, 'escalated': 12, 'human': 26}
    assert sum(r['admin_note'] for r in support) == 25
    assert sum(r.get('join_trap') == 'personal_email' for r in support) == 2


def test_reference_plan_and_required_records():
    plans = briefs()
    assert len(plans) == 22
    files = assemble_reference_files({b['key']: 'A short synthetic description.' for b in plans})
    assert len(files['stories']) == 12 and len(files['pages']) == 10
    shipped = next(s for s in files['stories'] if s['id'] == 4127)
    assert shipped['completed_at'] == '2026-10-06T00:00:00Z'
    assert next(s for s in files['stories'] if s['id'] == 4133)['started'] is False
    assert files['pages'][0]['properties']['Target']['date']['start'] == '2027-03-31'


def test_loud_narrow_probe_below_six_real_themes():
    spec = load(42)
    themes = spec['themes']['themes']
    probe = next(t for t in themes if t['kind'] == 'probe')
    assert probe['accounts'] == ['A01'] and probe['severity'] == 4
    assert {r for r, n in probe['routes'].items() if n} == {'sales', 'support', 'account_management'}
    assert min(score(t, spec['accounts']['accounts']) for t in themes if t['kind'] == 'real') > score(probe, spec['accounts']['accounts'])


def test_dataset_rejects_missing_model_outputs_before_validation():
    def schema_check(*args):
        raise AssertionError('validation must not start on an incomplete dataset')
    with pytest.raises(ValueError, match='responses do not match'):
        assemble_dataset(42, {}, {}, schema_check)




def test_null_content_is_invalid_retried_and_never_cached(tmp_path):
    from signal_engine.gateway import InvalidResponse
    from tests.conftest import FakeGateway
    gw = FakeGateway(None, {'generate': {'content': None}}, tmp=tmp_path / 'c', sleep=lambda s: None)
    with pytest.raises(InvalidResponse):
        gw.chat('generate', [{'role': 'user', 'content': 'x'}], target_type='t', target_id='1')
    assert len(gw.calls) == gw.stage_cfg('generate')['retries'] + 1
    assert not list((tmp_path / 'c').rglob('*.json'))


def test_write_record_regenerates_on_invalid_response():
    from signal_engine.gateway import InvalidResponse
    seen = []
    def bad(record, attempt):
        seen.append(attempt)
        raise InvalidResponse('null content')
    record = {'id': 'r1'}
    with pytest.raises(RecordValidationError, match='failed after two regenerations'):
        write_record(record, 42, bad)
    assert seen == [0, 1, 2]


def test_cache_is_atomic_and_corrupt_file_is_a_miss(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from tests.conftest import FakeGateway
    gw = FakeGateway(None, {'generate': {'content': '{"a": "' + 'x' * 200000 + '"}'}}, tmp=tmp_path / 'c')
    ask = lambda _: gw.chat('generate', [{'role': 'user', 'content': 'same'}], target_type='t', target_id='1', schema={'type': 'object'})
    with ThreadPoolExecutor(16) as ex:
        assert all(len(r['a']) == 200000 for r in ex.map(ask, range(64)))
    files = list((tmp_path / 'c').rglob('*'))
    assert not [f for f in files if f.suffix == '.tmp']
    f = next(f for f in files if f.suffix == '.json')
    f.write_text('{"request": ', encoding='utf-8')
    assert len(ask(0)['a']) == 200000


def test_record_schema_carries_band_and_enums():
    from generator.planner import plan
    from generator.writer import record_schema
    r = next(r for r in plan(42)['records'] if r.get('turns_range') == [40, 60] and r['mentions'])
    t = record_schema(r, 42)['properties']['turns']
    assert (t['minItems'], t['maxItems']) == (40, 60)
    p = t['items']['properties']
    assert p['mention_ids']['items']['enum'] == [m['id'] for m in r['mentions']]
    assert None in p['noise_category']['enum'] and 'how_to' in p['noise_category']['enum']


def test_gateway_rejects_response_outside_the_schema(tmp_path):
    import json
    import pytest
    from generator.planner import plan
    from generator.writer import record_schema
    from signal_engine.gateway import Gateway, InvalidResponse
    r = next(r for r in plan(42)['records'] if r.get('turns_range') and r['source'] != 'fullstory')
    bad = json.dumps({'turns': [{'speaker': 'customer', 'text': 'x', 'mention_ids': [], 'noise_category': None}]})

    class C:
        class chat:
            @staticmethod
            def completions_create(**kw): ...
    class Resp:
        def model_dump(self):
            return {'choices': [{'message': {'content': bad}, 'finish_reason': 'stop'}], 'usage': {}}
    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    return Resp()
    gw = Gateway(store=None, profile='demo', cache_dir=tmp_path, keys={}, client=Client(), sleep=lambda s: None, max_usd=1)
    with pytest.raises(InvalidResponse):
        gw.chat('generate', [{'role': 'user', 'content': 'x'}], target_type='t', target_id='1', schema=record_schema(r, 42))


def test_synonym_is_one_deterministic_term_and_prompt_forbids_facts():
    from generator.brief import mention_briefs
    from generator.planner import plan
    from generator.writer import record_schema
    from generator.specs import load
    r = next(r for r in plan(42)['records'] if r['source'] != 'fullstory' and any(m['theme'] in {t['id'] for t in load(42)['themes']['themes']} for m in r['mentions']))
    briefs = mention_briefs(42, r)
    assert briefs == mention_briefs(42, r)
    chosen = [m['synonym'] for m in briefs if 'synonym' in m]
    assert chosen and record_schema(r, 42)['properties']['turns']['items']['properties']['synonym_used']['enum'] == [*chosen, None]
    prompt = make_prompt(42, r)
    theme = next(t for t in load(42)['themes']['themes'] if t['id'] == r['mentions'][0]['theme'])
    assert 'never_write_verbatim' in prompt and theme['facts'][0] in prompt and 'exactly as written' in prompt


def test_common_capitalised_word_passes_but_invented_name_fails():
    from generator.verify import unknown_names
    assert unknown_names('We only get the English letters here', 42) == []
    assert unknown_names('please ask Brenda Quillfeather about it', 42)
