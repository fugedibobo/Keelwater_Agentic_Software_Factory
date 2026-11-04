"""Convert private tagged responses into source records and truth locators."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import random
from .specs import load
from .writer import validate_response


def assemble(record, response, seed, include_noise=False):
    """Return (source record, ground-truth mentions); strips every private tag."""
    validate_response(record, response, seed)
    spec = load(seed)
    people = spec['people']
    staff = next(p for p in people['staff'] if p['team'] == record['route'])
    contact = next(p for p in people['customer_contacts'] if p['account'] == record['account'])
    hubspot_id = str(18452001001 + next(i for i, a in enumerate(spec['accounts']['accounts']) if a['key'] == record['account']))
    rng = random.Random(int(hashlib.sha256(f"{seed}:{record['id']}:metadata".encode()).hexdigest(), 16))
    bucket_by_theme = {t['id']: t['bucket'] for t in spec['themes']['themes']}
    bucket = next((bucket_by_theme.get(m['theme']) for m in record['mentions'] if bucket_by_theme.get(m['theme'])), None)
    buckets = sorted({t['bucket'] for t in spec['themes']['themes'] if t['bucket']} | {'general'})
    occurred = record['occurred_at']
    epoch = int(datetime.fromisoformat(occurred.replace('Z', '+00:00')).timestamp())
    lookup = {m['id']: m for m in record['mentions']}
    truth, turns, noise, cursor = [], [], [], 0
    for index, turn in enumerate(response['turns']):
        duration = max(1000, round(len(turn['text'].split()) / 150 * 60000))
        speaker = turn['speaker']
        if record['source'] == 'gong':
            locator = {'sentence_start_ms': cursor}
            turns.append({'speakerId': 'customer' if speaker == 'customer' else 'staff', 'topic': '', 'sentences': [{'start': cursor, 'end': cursor + duration, 'text': turn['text']}]})
        elif record['source'] == 'fireflies':
            locator = {'sentence_index': index}
            name = contact['name'] if speaker == 'customer' else staff['name']
            lower = turn['text'].casefold()
            turns.append({'index': index, 'speaker_id': 'customer' if speaker == 'customer' else 'staff', 'speaker_name': name, 'text': turn['text'], 'raw_text': turn['text'], 'start_time': cursor / 1000, 'end_time': (cursor + duration) / 1000, 'ai_filters': {'question': '?' in turn['text'], 'pricing': 'price' in lower, 'task': 'follow up' in lower}})
        elif record['source'] == 'intercom':
            part_id = f"{record['id']}-{index}"
            locator = {'part_id': part_id}
            name = contact['name'] if speaker == 'customer' else staff['name']
            is_note = speaker == 'internal' and turn.get('noise_category') == 'internal'
            turns.append({'type': 'conversation_part', 'id': part_id, 'part_type': 'note' if is_note else 'comment', 'body': turn['text'], 'created_at': epoch + cursor // 1000, 'author': {'type': {'customer': 'user', 'internal': 'admin', 'bot': 'bot'}[speaker], 'id': speaker, 'name': name}})
        else:
            raise ValueError('unsupported text source')
        for mention_id in turn.get('mention_ids', []):
            mention_time = (datetime.fromisoformat(occurred.replace('Z', '+00:00')) + timedelta(milliseconds=cursor)).isoformat().replace('+00:00', 'Z')
            truth.append({**lookup[mention_id], 'occurred_at': mention_time, 'account': None if record.get('join_trap') == 'two_customer_domains' else record['account'], 'source': record['source'], 'route': record['route'], 'source_id': record['id'], 'locator': locator, 'at_ms': cursor})
        if turn.get('noise_category') and not turn.get('mention_ids'):
            noise.append({'source': record['source'], 'source_id': record['id'], 'locator': locator, 'at_ms': cursor, 'category': turn['noise_category']})
        cursor += duration
    def result(raw):
        return (raw, truth, noise) if include_noise else (raw, truth)
    if record['source'] == 'gong':
        transcript_text = ' '.join(t['text'] for t in response['turns']).casefold()
        trackers = [{'name': name, 'count': transcript_text.count(word)} for name, word in (('documents', 'document'), ('claims', 'claim'), ('pricing', 'price')) if word in transcript_text]
        call = {'metaData': {'id': record['id'], 'started': occurred, 'duration': cursor // 1000}, 'content': {'trackers': trackers}, 'context': [{'system': 'HubSpot', 'objects': [{'objectType': 'company', 'objectId': hubspot_id, 'fields': [], 'timing': 'TimeOfCall'}]}], 'parties': [{'speakerId': 'staff', 'name': staff['name'], 'emailAddress': staff['email'], 'affiliation': 'Internal'}, {'speakerId': 'customer', 'name': contact['name'], 'emailAddress': contact['email'], 'affiliation': 'External'}]}
        if record.get('join_trap') == 'broker_and_customer':
            broker = people['brokers'][0]
            call['parties'].append({'speakerId': 'broker', 'name': broker['name'], 'emailAddress': broker['email'], 'affiliation': 'External'})
        return result({'call': call, 'transcript': {'callId': record['id'], 'transcript': turns}})
    if record['source'] == 'fireflies':
        attendees = [{'name': p['name'], 'displayName': p['name'], 'email': p['email']} for p in (staff, contact)]
        if record.get('other_account'):
            other = next(p for p in people['customer_contacts'] if p['account'] == record['other_account'])
            attendees.append({'name': other['name'], 'displayName': other['name'], 'email': other['email']})
        return result({'id': record['id'], 'date': epoch * 1000, 'duration': cursor / 60000, 'host_email': staff['email'], 'meeting_attendees': attendees, 'sentences': turns})
    email = 'contact@mailbox.example' if record.get('join_trap') == 'personal_email' else contact['email']
    mode = record.get('fin_mode', 'human')
    ai_agent = None if mode == 'human' else {'last_answer_type': 'ai_answer', 'resolution_state': 'assumed_resolution' if mode == 'resolved' else 'routed_to_team'}
    tag = bucket if bucket and rng.random() < .7 else rng.choice([b for b in buckets if b != bucket])
    return result({'type': 'conversation', 'id': record['id'], 'created_at': epoch, 'source': {'author': {'type': 'user', 'name': contact['name'], 'email': email}}, 'tags': {'type': 'tag.list', 'tags': [{'name': tag}]}, 'ai_agent': ai_agent, 'ai_agent_participated': mode != 'human', 'conversation_parts': {'type': 'conversation_part.list', 'conversation_parts': turns, 'total_count': len(turns)}})
