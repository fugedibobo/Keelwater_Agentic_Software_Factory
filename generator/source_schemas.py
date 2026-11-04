"""Validate exports against issue #1's per-source schemas."""
from __future__ import annotations

import json
from pathlib import Path
from .specs import ROOT


def _validate_subset(value, schema, path='$'):
    # Supports every keyword in #1's current source schemas. Fail closed if a
    # future schema adds a constraint, rather than silently ignoring it.
    supported = {'$schema', 'title', 'description', 'type', 'properties', 'required', 'items', 'enum', 'const', 'additionalProperties'}
    unknown = set(schema) - supported
    if unknown:
        raise ValueError(f'{path}: unsupported schema keywords: {sorted(unknown)}')
    types = schema.get('type')
    if isinstance(types, str):
        types = [types]
    kinds = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
             'string': lambda v: isinstance(v, str), 'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
             'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
             'boolean': lambda v: isinstance(v, bool), 'null': lambda v: v is None}
    if types and (any(t not in kinds for t in types) or not any(kinds[t](value) for t in types)):
        raise ValueError(f'{path}: expected {types}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: not an allowed value')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{path}: not the required constant')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                raise ValueError(f'{path}: missing {key}')
        properties = schema.get('properties', {})
        for key, child in value.items():
            if key in properties:
                _validate_subset(child, properties[key], path + '.' + key)
            elif schema.get('additionalProperties') is False:
                raise ValueError(f'{path}: unexpected property {key}')
            elif isinstance(schema.get('additionalProperties'), dict):
                _validate_subset(child, schema['additionalProperties'], path + '.' + key)
    if isinstance(value, list) and 'items' in schema:
        for i, item in enumerate(value):
            _validate_subset(item, schema['items'], f'{path}[{i}]')


def schema_for(name):
    fixed = {'gong/calls.json': ('gong_calls', False), 'gong/transcripts.json': ('gong_transcripts', False),
             'fullstory/events.ndjson': ('fullstory_event', True), 'fullstory/sessions.json': ('fullstory_session', True),
             'hubspot/companies.json': ('hubspot_companies', False), 'shortcut/stories.json': ('shortcut_stories', False),
             'notion/pages.json': ('notion_pages', False)}
    if name in fixed:
        return fixed[name]
    if name.startswith('intercom/') and name.endswith('.json'):
        return 'intercom_conversation', False
    if name.startswith('fireflies/') and name.endswith('.json'):
        return 'fireflies_transcript', False
    raise ValueError(f'unknown raw file {name}')


def validate(name, data, schema_dir=None):
    schema_name, per_row = schema_for(name)
    directory = Path(schema_dir) if schema_dir else ROOT / 'contracts' / 'sources'
    schema = json.loads((directory / (schema_name + '.schema.json')).read_text(encoding='utf-8'))
    value = [json.loads(line) for line in data.decode('utf-8').splitlines() if line] if name.endswith('.ndjson') else json.loads(data.decode('utf-8'))
    if per_row:
        if not isinstance(value, list):
            raise ValueError(f'{name}: expected a list of records')
        for row in value:
            _validate_subset(row, schema)
    else:
        _validate_subset(value, schema)
