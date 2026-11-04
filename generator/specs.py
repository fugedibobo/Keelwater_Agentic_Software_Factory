"""Read the generator specifications without depending on pipeline packages."""
from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=32)
def _read_cached(path: Path, modified_ns: int, size: int) -> dict:
    # The specifications use the JSON subset of YAML, with an initial comment.
    return json.loads('\n'.join(line for line in path.read_text(encoding='utf-8').splitlines() if not line.lstrip().startswith('#')))


def read_spec(path: Path) -> dict:
    stat = path.stat()
    return deepcopy(_read_cached(path, stat.st_mtime_ns, stat.st_size))


def load(seed: int, root: Path = ROOT) -> dict:
    if seed not in (42, 43):
        raise ValueError('Only seeds 42 and 43 are specified')
    directory = root / 'generator' / 'spec'
    specific = directory / 'holdout' if seed == 43 else directory
    return {name: read_spec((specific if name in ('themes', 'noise') else directory) / (name + '.yaml')) for name in ('accounts', 'people', 'glossary', 'themes', 'noise')}
