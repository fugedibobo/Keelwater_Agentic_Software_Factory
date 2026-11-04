"""Private writing briefs and native shapes for Shortcut and Notion."""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


STORIES = [
    (4127, 'Bulk upload documents to a claim', 'completed'),
    (4128, 'Claim search refinements', 'completed'),
    (4129, 'Supplier contact details', 'completed'),
    (4130, 'Payment history improvements', 'completed'),
    (4131, 'Workspace administration', 'completed'),
    (4132, 'Activity timeline display', 'completed'),
    (4133, 'Document classifier confidence threshold', 'not_started'),
    (4134, 'Task list improvements', 'in_progress'),
    (4135, 'Claim information display', 'in_progress'),
    (4136, 'Supplier address fields', 'in_progress'),
    (4137, 'Reporting navigation', 'not_started'),
    (4138, 'Organisation settings', 'not_started'),
]
PAGES = [
    ('Policyholder milestone notifications', 'In progress', '2027-03-31'),
    ('Reserve history audit export', 'Planned', None),
    ('Task overview', 'Planned', None),
    ('Claims timeline', 'Planned', None),
    ('Supplier directory', 'In progress', None),
    ('Account settings', 'Planned', None),
    ('Reporting navigation', 'Planned', None),
    ('September release notes', 'Done', None),
    ('October release notes', 'Done', None),
    ('Summer release notes', 'Done', None),
]


def briefs():
    stories = [{'key': f'story:{sid}', 'source': 'shortcut', 'name': name, 'status': status} for sid, name, status in STORIES]
    pages = [{'key': f'page:{i}', 'source': 'notion', 'name': name, 'status': status, 'target': target} for i, (name, status, target) in enumerate(PAGES)]
    return stories + pages


def assemble_reference_files(descriptions):
    expected = {b['key'] for b in briefs()}
    if set(descriptions) != expected or any(not isinstance(x, str) or not x.strip() for x in descriptions.values()):
        raise ValueError('one nonempty description is required for each reference brief')
    stories = []
    for sid, name, state in STORIES:
        stories.append({'id': sid, 'name': name, 'description': descriptions[f'story:{sid}'], 'story_type': 'feature', 'workflow_state_id': {'completed': 3, 'in_progress': 2, 'not_started': 1}[state], 'completed': state == 'completed', 'started': state != 'not_started', 'blocked': False, 'completed_at': ('2026-10-06T00:00:00Z' if sid == 4127 else '2026-09-15T00:00:00Z') if state == 'completed' else None})
    pages = []
    for i, (name, state, target) in enumerate(PAGES):
        page_id = str(uuid5(NAMESPACE_URL, 'https://keelwater.example/notion/' + str(i)))
        pages.append({'object': 'page', 'id': page_id, 'properties': {'Name': {'type': 'title', 'title': [{'type': 'text', 'text': {'content': name}, 'plain_text': name}]}, 'Status': {'type': 'status', 'status': {'name': state}}, 'Target': {'type': 'date', 'date': {'start': target} if target else None}, 'Problem': {'type': 'rich_text', 'rich_text': [{'type': 'text', 'text': {'content': descriptions[f'page:{i}']}, 'plain_text': descriptions[f'page:{i}']}]}}})
    return {'stories': stories, 'pages': pages}
