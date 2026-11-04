"""No-network integration using the real gateway and a fake model client."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from generator.brief import make_prompt
from generator.emitter import emit
from generator.ground_truth import raw_hash
from generator.planner import plan
from generator.runner import run
from signal_engine.gateway import Gateway

from test_generator_contracts import fake_inputs


def tree_bytes(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}


class Response:
    def __init__(self, content):
        self.content = content

    def model_dump(self):
        return {'choices': [{'message': {'content': json.dumps(self.content)}}], 'usage': {'cost': 0.0}}


class FakeClient:
    def __init__(self, records):
        self.records = records
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        prompt = kwargs['messages'][0]['content']
        if prompt.startswith('Write one short realistic description'):
            return Response({'description': 'A routine description of the work.'})
        assert prompt in self.records
        return Response(self.records[prompt])


def test_generation_and_forced_replay_are_byte_identical(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('network attempted'))
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network attempted'))
    root = Path(tmp_path)
    schemas = Path(__file__).resolve().parent.parent / 'contracts' / 'sources'
    shutil.copytree(schemas, root / 'contracts' / 'sources')
    records = {}
    for seed in (42, 43):
        inputs, _ = fake_inputs(seed)
        for record in plan(seed)['records']:
            if record['source'] != 'fullstory':
                prompt = make_prompt(seed, record)
                if prompt in records:
                    assert records[prompt] == inputs[record['id']]
                records[prompt] = inputs[record['id']]
    cache = root / 'generator' / 'cache'
    fake = Gateway(store=None, profile='demo', cache_dir=cache, keys={}, client=FakeClient(records), max_usd=.9)
    result42 = run(42, root=root, gateway=fake, out=lambda _: None)
    assert result42['calls'] == 129 and result42['regenerations'] == 0
    before42 = tree_bytes(root / 'data' / 'raw')
    truth42 = (root / 'data' / 'ground_truth.yaml').read_bytes()
    truth_data = json.loads(truth42)
    from collections import Counter
    noise = Counter(n['category'] for n in truth_data['noise'])
    assert noise['scheduling'] == 45 and noise['pricing'] == 6 and noise['praise'] == 6
    assert noise['password_reset'] == 12 and noise['how_to'] == 10
    assert len(truth_data['join_traps']) == 6
    assert len(truth_data['fullstory_false_positives']) == 11
    conversations = [json.loads(data) for name, data in before42.items() if name.startswith('intercom/')]
    assert sum(any(p['part_type'] == 'note' for p in c['conversation_parts']['conversation_parts']) for c in conversations) == 25
    with pytest.raises(FileExistsError):
        run(42, root=root, gateway=fake, out=lambda _: None)
    fake43 = Gateway(store=None, profile='demo', cache_dir=cache, keys={}, client=FakeClient(records), max_usd=.3)
    result43 = run(43, root=root, gateway=fake43, out=lambda _: None)
    assert result43['calls'] == 42 and result43['regenerations'] == 0
    before43 = tree_bytes(root / 'data' / 'holdout' / 'raw')
    truth43 = (root / 'data' / 'holdout' / 'ground_truth.yaml').read_bytes()
    for seed in (42, 43):
        replay = Gateway(store=None, profile='replay', cache_dir=cache, keys={}, max_usd=.9 if seed == 42 else .3)
        run(seed, force=True, root=root, gateway=replay, out=lambda _: None)
    assert before42 == tree_bytes(root / 'data' / 'raw')
    assert truth42 == (root / 'data' / 'ground_truth.yaml').read_bytes()
    assert before43 == tree_bytes(root / 'data' / 'holdout' / 'raw')
    assert truth43 == (root / 'data' / 'holdout' / 'ground_truth.yaml').read_bytes()


def test_emit_rolls_back_if_replacement_fails(tmp_path, monkeypatch):
    raw1, raw2 = {'gong/calls.json': b'old\n'}, {'gong/calls.json': b'new\n'}
    def truth(raw):
        return {'generated': {'seed': 42, 'raw_sha256': raw_hash(raw)}}
    emit(42, raw1, truth(raw1), root=tmp_path)
    before = tree_bytes(tmp_path / 'data')
    import generator.emitter as emitter
    actual = emitter.os.replace
    def fail_last(src, dst):
        if Path(src).name == 'ground_truth.yaml' and Path(dst).name == 'ground_truth.yaml':
            raise OSError('simulated replacement failure')
        return actual(src, dst)
    monkeypatch.setattr(emitter.os, 'replace', fail_last)
    with pytest.raises(OSError, match='simulated'):
        emit(42, raw2, truth(raw2), force=True, root=tmp_path)
    assert tree_bytes(tmp_path / 'data') == before
