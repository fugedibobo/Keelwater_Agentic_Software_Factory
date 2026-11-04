"""Build deterministic FullStory events and truth locators without a model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import random


PATTERNS = {
    'rt-doc-type-misfile': ('Document type', 'rage'),
    'rt-fnol-duplicate-claims': ('Link to existing claim', 'dead'),
    'rt-mi-export-mismatch': ('Export CSV', 'error'),
    'ho-role-setup': ('Permission', 'rage'),
}
GRAPH = {'Claims': ('Claim details', 'Tasks', 'Reports', 'Administration'), 'Claim details': ('Claims', 'Documents', 'Payments', 'Suppliers'),
         'Documents': ('Claim details', 'Claims'), 'Payments': ('Claim details', 'Claims'),
         'Suppliers': ('Claim details', 'Claims'), 'Tasks': ('Claims', 'Claim details'),
         'Reports': ('Claims',), 'Administration': ('Claims',)}
THEME_PAGE = {'rt-doc-type-misfile': 'Documents', 'rt-fnol-duplicate-claims': 'Claims',
              'rt-mi-export-mismatch': 'Reports', 'ho-role-setup': 'Administration'}


def build(records):
    sessions, events, truth, false_positives = [], [], [], []
    for index, record in enumerate(r for r in records if r['source'] == 'fullstory'):
        session = record['id']
        rng = random.Random(int(hashlib.sha256((session + ':walk').encode()).hexdigest(), 16))
        page = 'Claims'
        day = record['occurred_at']
        start = datetime.fromisoformat(day.replace('Z', '+00:00'))
        sessions.append({'sessionId': session, 'userId': 'contact@' + record['account'].lower() + '.example', 'createdTime': start.isoformat().replace('+00:00', 'Z'), 'fsUrl': f'https://app.fullstory.example/s/{session}'})
        for j in range(30):
            timestamp = start + timedelta(minutes=j + (130 if index < 10 and j >= 15 else 0))
            event_id = hashlib.sha256(f'{session}:{j}'.encode()).hexdigest()[:16]
            if j and rng.random() < .3:
                page = rng.choice(GRAPH[page])
            event_type = 'page_view' if rng.random() < .25 else 'click'
            props = {'fs_rage_count': 0, 'fs_dead_count': 0, 'fs_error_kind': None, 'target_text': rng.choice(['Open', 'Save', 'Next', 'Details'])}
            if j < len(record['mentions']):
                mention = record['mentions'][j]
                target, kind = PATTERNS[mention['theme']]
                page = THEME_PAGE[mention['theme']]
                event_type = 'click'
                props['target_text'] = target
                if kind == 'rage': props['fs_rage_count'] = 5
                if kind == 'dead': props['fs_dead_count'] = 1
                if kind == 'error': props['fs_error_kind'] = 'exception'
                truth.append({**mention, 'occurred_at': timestamp.isoformat().replace('+00:00', 'Z'), 'source': 'fullstory', 'route': 'sessions', 'source_id': session, 'locator': {'event_ids': [event_id]}, 'at_ms': int((timestamp-start).total_seconds()*1000)})
            elif j == 29 and 10 <= index < 21:
                event_type = 'click'
                kind = 'habitual_double_click' if index < 16 else 'static_dead_click'
                props['target_text'] = 'Save' if index < 16 else 'Overview'
                props['fs_rage_count' if index < 16 else 'fs_dead_count'] = 3 if index < 16 else 1
                false_positives.append({'session_id': session, 'event_ids': [event_id], 'kind': kind})
            if event_type == 'page_view':
                props = {'page_name': page, 'duration_millis': 60000}
            events.append({'event_id': event_id, 'event_time': timestamp.isoformat().replace('+00:00', 'Z'), 'session_id': session, 'event_type': event_type, 'event_properties': props, 'source_properties': {'page_name': page}})
    return {'sessions': sessions, 'events': events, 'mentions': truth, 'false_positives': false_positives}
