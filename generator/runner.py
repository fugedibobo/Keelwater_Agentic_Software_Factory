"""Orchestrate generator calls, verification and emission through issue #1."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

from .dataset import assemble_dataset, json_bytes
from .emitter import assert_writable, emit
from .planner import plan
from .references import assemble_reference_files, briefs
from .source_schemas import validate
from .specs import ROOT
from .writer import MODEL, gateway_request, write_all, write_reference

SCHEMAS = ('gong_calls', 'gong_transcripts', 'intercom_conversation', 'fireflies_transcript', 'fullstory_event', 'fullstory_session', 'hubspot_companies', 'shortcut_stories', 'notion_pages')


def make_gateway(force, max_usd, root=ROOT):
    from signal_engine.gateway import Gateway
    # Store is deliberately absent: the generator is not a pipeline run.
    return Gateway(store=None, profile='replay' if force else 'demo', cache_dir=Path(root) / 'generator' / 'cache', max_usd=max_usd)


def run(seed, force=False, max_usd=None, root=ROOT, gateway=None, out=print):
    root = Path(root)
    cap = .90 if seed == 42 else .30 if seed == 43 else None
    if cap is None:
        raise ValueError('only seeds 42 and 43 are specified')
    if max_usd is None:
        max_usd = cap
    if not (0 < max_usd <= cap):
        raise ValueError(f'--max-usd must be positive and at most {cap:.2f} for seed {seed}')
    assert_writable(seed, force, root)
    schema_dir = root / 'contracts' / 'sources'
    missing = [name for name in SCHEMAS if not (schema_dir / f'{name}.schema.json').is_file()]
    if missing:
        raise FileNotFoundError('issue #1 source schemas missing: ' + ', '.join(missing))
    reference_files = {}
    if seed == 43:
        for name in ('shortcut/stories.json', 'notion/pages.json'):
            reference_files[name] = (root / 'data' / 'raw' / name).read_bytes()
    p = plan(seed)
    gateway = gateway or make_gateway(force, max_usd, root)
    cfg = gateway.stage_cfg('generate')
    if cfg['model'] != MODEL or cfg['temperature'] != .8:
        raise ValueError('generate gateway model or temperature differs from the specification')
    stats = {'calls': 0, 'rejections': 0, 'names_flagged': 0}
    lock = threading.Lock()

    class CountedGateway:
        def chat(self, *args, **kwargs):
            with lock:
                stats['calls'] += 1
            return gateway.chat(*args, **kwargs)

    counted = CountedGateway()
    def rejected(record_id, attempt, reason):
        with lock:
            stats['rejections'] += 1
            stats['names_flagged'] += int('unknown name' in reason)

    responses = write_all(p['records'], seed, lambda record, attempt: gateway_request(counted, record, seed, attempt), rejected)
    if seed == 42:
        reference_briefs = briefs()
        with ThreadPoolExecutor(max_workers=8) as executor:
            descriptions = list(executor.map(lambda item: write_reference(counted, item, seed, rejected), reference_briefs))
        reference = assemble_reference_files(dict(zip((b['key'] for b in reference_briefs), descriptions)))
        reference_files = {'shortcut/stories.json': json_bytes({'stories': reference['stories']}),
                           'notion/pages.json': json_bytes({'results': reference['pages']})}
    raw, truth = assemble_dataset(seed, responses, reference_files, lambda name, data: validate(name, data, schema_dir))
    base = emit(seed, raw, truth, force, root)
    text_records = 129 if seed == 42 else 42
    stats['regenerations'] = stats['calls'] - text_records
    stats['spend_usd'] = gateway.spent
    out(f"seed {seed}: gong={p['counts']['gong']} intercom={p['counts']['intercom']} fireflies={p['counts']['fireflies']} fullstory={p['counts']['fullstory']} hubspot=36 shortcut=12 notion=10")
    out(f"calls={stats['calls']} regenerations={stats['regenerations']} names_flagged={stats['names_flagged']} spend_usd={stats['spend_usd']:.6f}")
    out(f'output: {base}')
    return stats
