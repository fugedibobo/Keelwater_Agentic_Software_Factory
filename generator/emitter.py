"""Safely publish a fully validated in-memory dataset inside its seed directory."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from .ground_truth import raw_hash
from .specs import ROOT


def destination(seed, root=ROOT):
    if seed not in (42, 43):
        raise ValueError('only seeds 42 and 43 are specified')
    return Path(root) / 'data' / ('holdout' if seed == 43 else '')


def assert_writable(seed, force=False, root=ROOT):
    base = destination(seed, root)
    if not force and ((base / 'raw').exists() or (base / 'ground_truth.yaml').exists()):
        raise FileExistsError(f'{base}: existing dataset; use --force to replace it')


def emit(seed, raw, truth, force=False, root=ROOT):
    """Stage all bytes before replacing owned outputs; restore on a failed swap."""
    assert_writable(seed, force, root)
    if truth['generated']['seed'] != seed or truth['generated']['raw_sha256'] != raw_hash(raw):
        raise ValueError('ground truth does not match the raw dataset')
    base = destination(seed, root)
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.generator-', dir=base) as temp:
        stage = Path(temp)
        staged_raw = stage / 'raw'
        for name, data in sorted(raw.items()):
            rel = PurePosixPath(name)
            if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name:
                raise ValueError('unsafe raw file path')
            out = staged_raw.joinpath(*rel.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        staged_truth = stage / 'ground_truth.yaml'
        staged_truth.write_bytes((json.dumps(truth, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))
        # JSON is a YAML subset. Put existing outputs in this private staging
        # directory first, so any failed swap can be rolled back.
        targets = [(base / 'raw', staged_raw), (base / 'ground_truth.yaml', staged_truth)]
        backups, installed = [], []
        try:
            for i, (target, source) in enumerate(targets):
                backup = stage / f'previous-{i}'
                if target.exists():
                    os.replace(target, backup)
                    backups.append((target, backup))
                os.replace(source, target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
            for target, backup in reversed(backups):
                os.replace(backup, target)
            raise
    return base
