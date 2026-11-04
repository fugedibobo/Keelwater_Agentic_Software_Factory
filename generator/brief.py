"""Create a deterministic private per-record model brief."""
from __future__ import annotations

import hashlib
import json
import random
from .specs import ROOT, load


def labels(record):
    """Opaque per-record labels (m1, m2, ...) sent to the model in place of mention ids, which embed theme ids."""
    return {m['id']: f'm{i + 1}' for i, m in enumerate(record['mentions'])}


def mention_briefs(seed, record):
    """One deterministic brief per planted mention; the single synonym chosen here is the one the writer must use."""
    spec = load(seed)
    rng = random.Random(int(hashlib.sha256(f"{seed}:{record['id']}".encode()).hexdigest(), 16))
    theme_map = {theme['id']: theme for theme in spec['themes']['themes']}
    mentions, tag = [], labels(record)
    for mention in record['mentions']:
        theme = theme_map.get(mention['theme'])
        if theme is None:
            mentions.append({'id': tag[mention['id']], 'request': mention['request'], 'severity': mention['severity']})
        else:
            mentions.append({'id': tag[mention['id']], 'problem': theme['description'], 'fact': rng.choice(theme['facts']), 'synonym': rng.choice(theme['synonyms']), 'severity': theme['severity'], 'stance': mention.get('stance'), 'post_ship': mention.get('post_ship', False), 'form': 'short agreement: the internal speaker states the problem with the synonym, then the customer agrees in under eight words' if mention.get('agreement') else rng.choice(['complaint', 'workaround', 'feature ask', 'question'])})
    return mentions


def make_prompt(seed, record):
    spec = load(seed)
    account = next(a for a in spec['accounts']['accounts'] if a['key'] == record['account'])
    contact = next(p for p in spec['people']['customer_contacts'] if p['account'] == record['account'])
    staff = next(p for p in spec['people']['staff'] if p['team'] == record['route'])
    mentions = mention_briefs(seed, record)
    themes = {t['id']: t for t in spec['themes']['themes']}
    never = sorted({term for m in record['mentions'] if m['theme'] in themes for term in (themes[m['theme']]['title'], *themes[m['theme']]['facts'])})
    record_brief = {'never_write_verbatim': never, 'only_people_who_may_be_named': [account['name'], contact['name'], staff['name']], 'source': record['source'], 'route': record['route'], 'date': record['occurred_at'], 'customer': {'company': account['name'], **contact}, 'staff': staff, 'turns_range': record.get('turns_range'), 'fin_mode': record.get('fin_mode'), 'glossary': spec['glossary']['features']}
    if record.get('other_account'):
        other = next(a for a in spec['accounts']['accounts'] if a['key'] == record['other_account'])
        other_contact = next(p for p in spec['people']['customer_contacts'] if p['account'] == record['other_account'])
        record_brief['second_customer'] = {'company': other['name'], **other_contact}
        record_brief['only_people_who_may_be_named'] += [other['name'], other_contact['name']]
    noise = {'allowed_categories': spec['noise']['categories'], 'required_categories': record.get('required_noise', []), 'distractor_how_to_phrase': record.get('distractor'), 'admin_note': record.get('admin_note', False), 'instructions': 'Tag every noise turn with its category. Put the distractor phrase, if given, in a how-to turn with no mention id. An admin note must be an internal turn tagged internal. A Fin-resolved or escalated conversation needs a bot turn; an escalated one also needs an internal reply. About 35 percent of customer turns are pleasantries. Every tagged customer mention, including a short agreement, must contain its supplied synonym.'}
    output_schema = {'turns': [{'speaker': 'customer|internal|bot', 'text': 'string', 'noise_category': 'string or null'}], 'mentions': {labels(record)[m['id']]: ({'internal_text': 'internal turn stating the problem, with the synonym', 'agreement_text': 'customer reply, under eight words', 'after_turn': 'index of the turns entry it follows'} if m.get('agreement') else {'text': 'the customer turn carrying this mention', 'after_turn': 'index of the turns entry it follows'}) for m in record['mentions']}}
    template = (ROOT / 'generator' / 'prompts' / 'record.md').read_text(encoding='utf-8-sig')
    return template.format(source=record['source'], record_brief=json.dumps(record_brief, ensure_ascii=False, sort_keys=True), mention_briefs=json.dumps(mentions, ensure_ascii=False, sort_keys=True), noise_brief=json.dumps(noise, sort_keys=True), output_schema=json.dumps(output_schema, sort_keys=True))
