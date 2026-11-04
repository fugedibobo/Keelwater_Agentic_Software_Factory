"""Versioned prompts: prompts/<stage>/<name>.md with a `version` front-matter field."""

import hashlib
import re
from pathlib import Path

import yaml

from .config import ROOT

PROMPT_DIR = ROOT / "prompts"
_FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)


def load_prompt(stage, name, prompt_dir=None):
    """Return (body, prompt_version) where prompt_version = name@version+<first 8 hex of sha256 of the file>."""
    path = Path(prompt_dir or PROMPT_DIR) / stage / f"{name}.md"
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    m = _FRONT.match(raw.decode("utf-8"))
    if not m or "version" not in (yaml.safe_load(m.group(1)) or {}):
        raise ValueError(f"{path}: missing front-matter version")
    version = yaml.safe_load(m.group(1))["version"]
    return m.group(2), f"{name}@{version}+{hashlib.sha256(raw).hexdigest()[:8]}"


def all_versions(prompt_dir=None):
    """{'<stage>/<name>': prompt_version} for every prompt file; empty when there is no prompts folder."""
    d = Path(prompt_dir or PROMPT_DIR)
    return {f"{p.parent.name}/{p.stem}": load_prompt(p.parent.name, p.stem, d)[1] for p in sorted(d.glob("*/*.md"))}
