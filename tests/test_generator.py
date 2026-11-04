from collections import Counter
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from signal_engine import config
from generator.cli import main
from generator.assemble import assemble
from generator.brief import labels, make_prompt
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
    assert all(label in prompt for label in labels(r).values())
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
    ask = lambda n: gw.chat('generate', [{'role': 'user', 'content': f'same{n}'}], target_type='t', target_id='1', schema={'type': 'object'})
    with ThreadPoolExecutor(16) as ex:  # distinct keys: Windows os.replace on a file another thread is reading raises PermissionError
        assert all(len(r['a']) == 200000 for r in ex.map(ask, range(64)))
        assert all(len(r['a']) == 200000 for r in ex.map(ask, range(64)))  # now warm: concurrent reads only
    files = list((tmp_path / 'c').rglob('*'))
    assert not [f for f in files if f.suffix == '.tmp']
    for f in files:
        if f.suffix == '.json':
            f.write_text('{"request": ', encoding='utf-8')
    assert len(ask(0)['a']) == 200000


def test_record_schema_carries_band_slots_and_enums():
    from generator.planner import plan
    from generator.writer import record_schema
    r = next(r for r in plan(42)['records'] if r.get('turns_range') == [40, 60] and r['mentions'])
    sc = record_schema(r, 42)
    from generator.writer import extra_slots
    n = sum(2 if m.get('agreement') else 1 for m in r['mentions']) + len(extra_slots(r))
    t = sc['properties']['turns']
    assert (t['minItems'], t['maxItems']) == (40 - n, 60 - n)
    assert 'mention_ids' not in t['items']['properties']
    assert None in t['items']['properties']['noise_category']['enum'] and 'how_to' in t['items']['properties']['noise_category']['enum']
    m = sc['properties']['mentions']
    assert m['required'] == list(labels(r).values()) and set(m['properties']) == set(m['required']) and m['additionalProperties'] is False


def test_merge_mentions_tags_each_mention_once_deterministically():
    from generator.planner import plan
    from generator.writer import merge_mentions
    r = next(r for r in plan(42)['records'] if len(r['mentions']) >= 2 and not any(m.get('agreement') for m in r['mentions']))
    base = [{'speaker': 'customer' if i % 2 else 'internal', 'text': f't{i}', 'noise_category': None} for i in range(10)]
    raw = {'turns': base, 'mentions': {labels(r)[m['id']]: {'text': f"mention {m['id']}", 'after_turn': i * 3 - 5} for i, m in enumerate(r['mentions'])}}
    out = merge_mentions(r, raw)
    assert out == merge_mentions(r, raw)
    tagged = [t['mention_ids'] for t in out['turns'] if t['mention_ids']]
    assert sorted(x for ids in tagged for x in ids) == sorted(m['id'] for m in r['mentions']) and all(len(i) == 1 for i in tagged)
    assert len(out['turns']) == 10 + len(r['mentions']) and all(t['speaker'] == 'customer' for t in out['turns'] if t['mention_ids'])


def test_agreement_mention_becomes_an_internal_turn_then_a_tagged_agreement():
    from generator.planner import plan
    from generator.writer import merge_mentions
    r = next(r for r in plan(42)['records'] if any(m.get('agreement') for m in r['mentions']))
    base = [{'speaker': 'customer', 'text': 'a', 'noise_category': None}, {'speaker': 'bot', 'text': 'b', 'noise_category': None}]
    raw = {'turns': base, 'mentions': {labels(r)[m['id']]: {'internal_text': f"INT {m['id']}", 'agreement_text': 'yes', 'after_turn': 0} for m in r['mentions']}}
    out = merge_mentions(r, raw)['turns']
    idx = [i for i, t in enumerate(out) if t['mention_ids']]
    assert len(idx) == len(r['mentions']) and all(out[i - 1]['speaker'] == 'internal' and out[i]['speaker'] == 'customer' for i in idx)
    assert len(out) == 2 + 2 * len(r['mentions'])

def test_gateway_rejects_response_outside_the_schema(tmp_path):
    import json
    import pytest
    from generator.planner import plan
    from generator.writer import record_schema
    from signal_engine.gateway import Gateway, InvalidResponse
    r = next(r for r in plan(42)['records'] if r.get('turns_range') and r['source'] != 'fullstory')
    bad = json.dumps({'turns': [{'speaker': 'customer', 'text': 'x', 'noise_category': None}], 'mentions': {}})

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
    assert chosen
    prompt = make_prompt(42, r)
    theme = next(t for t in load(42)['themes']['themes'] if t['id'] == r['mentions'][0]['theme'])
    assert 'never_write_verbatim' in prompt and theme['facts'][0] in prompt and 'exactly as written' in prompt


def test_common_capitalised_word_passes_but_invented_name_fails():
    from generator.verify import unknown_names
    assert unknown_names('We only get the English letters in Wales and Northern Ireland here', 42) == []
    assert unknown_names('please ask Brenda Quillfeather about it', 42)


def test_mention_slot_shape_follows_the_agreement_flag():
    from generator.planner import plan
    from generator.writer import record_schema
    seen = set()
    for r in plan(42)['records']:
        if r['source'] == 'fullstory':
            continue
        props = record_schema(r, 42)['properties']['mentions']['properties']
        for m in r['mentions']:
            sl = props[labels(r)[m['id']]]
            if m.get('agreement'):
                assert 'text' not in sl['properties'] and sl['properties']['internal_text']['minLength'] == 45 and sl['properties']['agreement_text']['maxLength'] == 44
                assert set(sl['required']) == {'internal_text', 'agreement_text', 'after_turn'}
            else:
                assert sl['properties']['text']['minLength'] == 45
            seen.add(bool(m.get('agreement')))
    assert seen == {True, False}


def test_several_agreements_each_get_their_own_internal_turn_and_pinned_phrase_is_checked_there():
    import pytest
    from generator.brief import mention_briefs
    from generator.planner import plan
    from generator.writer import RecordValidationError, merge_mentions
    r = next(r for r in plan(42)['records'] if sum(1 for m in r['mentions'] if m.get('agreement')) >= 2)
    pin = {b['id']: b.get('synonym', '') for b in mention_briefs(42, r)}
    base = [{'speaker': 'customer', 'text': f't{i}', 'noise_category': None} for i in range(6)]
    good = {'turns': base, 'mentions': {labels(r)[m['id']]: {'internal_text': f"we hear {pin[labels(r)[m['id']]]} a lot", 'agreement_text': 'yes', 'after_turn': 3} for m in r['mentions']}}
    out = merge_mentions(r, good, 42)['turns']
    idx = [i for i, t in enumerate(out) if t['mention_ids']]
    assert len(idx) == len(r['mentions']) and all(out[i - 1]['speaker'] == 'internal' for i in idx)
    bad = {'turns': base, 'mentions': {labels(r)[m['id']]: {'internal_text': 'nothing relevant at all', 'agreement_text': 'the phrase ' + pin[labels(r)[m['id']]], 'after_turn': 3} for m in r['mentions']}}
    with pytest.raises(RecordValidationError, match='lacks the required phrase'):
        merge_mentions(r, bad, 42)

def test_regeneration_prompt_carries_the_failed_rule_and_pinned_phrase():
    from generator.brief import mention_briefs
    from generator.planner import plan
    from generator.writer import FEEDBACK, feedback_text
    r = next(r for r in plan(42)['records'] if r['source'] != 'fullstory' and any('synonym' in b for b in mention_briefs(42, r)))
    b = next(b for b in mention_briefs(42, r) if 'synonym' in b)
    text = feedback_text(r, 42, f"{r['id']}: unknown name Acme; forbidden raw phrase Some Theme Title")
    assert 'Acme' in text and "not an allowed name" in text and f"'{b['synonym']}'" in text and "Some Theme Title" in text
    assert feedback_text(r, 42, None) == ''


def test_missing_pinned_synonym_is_a_failure_in_code():
    import pytest
    from generator.brief import mention_briefs
    from generator.planner import plan
    from generator.writer import RecordValidationError, merge_mentions
    r = next(r for r in plan(42)['records'] if r['source'] != 'fullstory' and any('synonym' in b for b in mention_briefs(42, r)) and not any(m.get('agreement') for m in r['mentions']))
    raw = {'turns': [], 'mentions': {labels(r)[m['id']]: {'text': 'nothing relevant here', 'after_turn': 0} for m in r['mentions']}}
    with pytest.raises(RecordValidationError, match='lacks the required phrase'):
        merge_mentions(r, raw, 42)


def test_prompt_and_schema_never_carry_a_mention_id_or_theme_id():
    import json
    from generator.planner import plan
    from generator.writer import record_schema
    checked = 0
    for r in plan(42)['records']:
        if r['source'] == 'fullstory' or not r['mentions']:
            continue
        blob = make_prompt(42, r) + json.dumps(record_schema(r, 42))
        for m in r['mentions']:
            assert m['id'] not in blob and m['theme'] not in blob
        checked += 1
    assert checked > 50


def test_feedback_carries_a_plain_instruction_for_a_structural_rule():
    from generator.planner import plan
    from generator.writer import feedback_text
    r = next(r for r in plan(42)['records'] if r['source'] != 'fullstory')
    assert "speaker is 'bot'" in feedback_text(r, 42, 'x: Fin conversation has no bot turn')


def test_unbanded_record_still_needs_a_real_conversation():
    from generator.planner import plan
    from generator.writer import record_schema
    r = next(r for r in plan(42)['records'] if r['source'] != 'fullstory' and not r.get('turns_range'))
    assert record_schema(r, 42)['properties']['turns']['minItems'] == 6


def test_department_words_pass_the_name_check():
    from generator.verify import unknown_names
    assert unknown_names('we raised it with the Finance team and it was Escalated', 42) == []


def test_part_of_another_account_name_passes_but_an_invented_company_fails():
    from generator.verify import unknown_names
    assert unknown_names('we spoke to Tidewell Marine about it', 42) == []
    assert unknown_names('we spoke to Brackenford Mutual about it', 42)


def test_compass_place_names_pass():
    from generator.verify import unknown_names
    assert unknown_names('our offices in North Wales and the West Midlands', 42) == []


def test_each_required_element_rule_has_a_slot():
    from generator.writer import extra_slots
    cases = {'bot': {'fin_mode': 'resolved'}, 'esc': {'fin_mode': 'escalated'}, 'admin': {'admin_note': True},
             'noise': {'required_noise': ['praise', 'scheduling']}, 'how': {'required_noise': ['how_to'], 'distractor': 'a phrase'}}
    keys = {n: [k for k, *_ in extra_slots(c)] for n, c in cases.items()}
    assert keys['bot'] == ['bot_turn'] and keys['esc'] == ['bot_turn', 'internal_reply'] and keys['admin'] == ['admin_note']
    assert keys['noise'] == ['noise_praise', 'noise_scheduling'] and keys['how'] == ['noise_how_to']
    assert extra_slots({'admin_note': True, 'required_noise': ['internal']}) == [('admin_note', 'internal', 'internal', None)]
    assert extra_slots({'distractor': 'a phrase'})[0] == ('noise_how_to', 'customer', 'how_to', 'a phrase')


def test_extra_slots_are_inserted_with_speaker_and_noise_and_phrase_is_guarded():
    import pytest
    from generator.writer import RecordValidationError, merge_mentions
    r = {'id': 'x', 'mentions': [], 'fin_mode': 'escalated', 'admin_note': True, 'required_noise': ['how_to'], 'distractor': 'the export button'}
    base = [{'speaker': 'customer', 'text': 'hello there', 'noise_category': None}]
    ok = {k: {'text': 'twenty characters or more here', 'after_turn': 0} for k in ('bot_turn', 'internal_reply', 'admin_note', 'noise_how_to')}
    ok['noise_how_to']['text'] = 'where is the export button please'
    out = merge_mentions(r, {'turns': base, 'mentions': {}, 'extras': ok})['turns']
    assert [(t['speaker'], t['noise_category']) for t in out[1:]] == [('bot', None), ('internal', None), ('internal', 'internal'), ('customer', 'how_to')]
    ok['noise_how_to']['text'] = 'a question with no phrase at all here'
    with pytest.raises(RecordValidationError, match='lacks the required phrase'):
        merge_mentions(r, {'turns': base, 'mentions': {}, 'extras': ok})


def test_dry_pass_every_planned_record_satisfies_the_missing_element_rules_by_construction():
    from generator.brief import labels, mention_briefs
    from generator.planner import plan
    from generator.specs import load
    from generator.writer import RecordValidationError, merge_mentions, record_schema, validate_response
    checked = 0
    for seed in (42, 43):
        for r in plan(seed)['records']:
            if r['source'] == 'fullstory':
                continue
            sc = record_schema(r, seed)
            pin = {b['id']: b.get('synonym', 'a small request') for b in mention_briefs(seed, r)}
            lo = sc['properties']['turns']['minItems']
            base = [{'speaker': 'customer' if i % 2 else 'internal', 'text': f'we discuss item number {i} with the team today', 'noise_category': None} for i in range(max(lo, 6))]
            mentions = {}
            for m in r['mentions']:
                k = labels(r)[m['id']]
                mentions[k] = ({'internal_text': f'we keep hearing that {pin[k]} is a problem for the team', 'agreement_text': 'yes, that is right', 'after_turn': 2}
                               if m.get('agreement') else {'text': f'we really need help because {pin[k]} is hurting the whole team every day', 'after_turn': 3})
            extras = {k: {'text': ('where is ' + ph + ' please') if ph else 'a routine message for the team today', 'after_turn': 1} for k, _, _, ph in __import__('generator.writer', fromlist=['x']).extra_slots(r)}
            assert set(extras) == set(sc['properties']['extras']['required'])
            merged = merge_mentions(r, {'turns': base, 'mentions': mentions, 'extras': extras}, seed)
            validate_response(r, merged, seed)  # no rule at all fires, so no missing-element rule is masked
            checked += 1
    assert checked > 140


def test_role_word_passes_when_written_lowercase_elsewhere_and_invented_name_fails():
    from generator.verify import unknown_names
    assert unknown_names('We spoke. Customer is high-priority and the customer agrees', 42) == []
    assert unknown_names('The Zorbulon team said the customer agrees', 42) == ['Zorbulon']
    assert unknown_names('We heard from Brackenford Mutual today.', 42)


def test_season_names_pass_the_name_check():
    from generator.verify import unknown_names
    assert unknown_names('the review is due before Summer and again in Winter', 42) == []


def test_internal_noise_label_is_absent_where_an_admin_note_is_forbidden():
    from generator.planner import plan
    from generator.writer import record_schema
    r = next(r for r in plan(43)['records'] if r['source'] == 'intercom' and not r.get('admin_note'))
    enum = record_schema(r, 43)['properties']['turns']['items']['properties']['noise_category']['enum']
    assert 'internal' not in enum and None in enum
    w = next(r for r in plan(43)['records'] if r['source'] == 'intercom' and r.get('admin_note'))
    assert 'internal' in record_schema(w, 43)['properties']['turns']['items']['properties']['noise_category']['enum']
