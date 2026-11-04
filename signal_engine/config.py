"""Repo paths, YAML config loading, config hashes and the .env locator."""

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_FILES = ("ranking", "pipeline", "taxonomy", "models")
FACTORY_JOB_SCHEMA = ROOT / "docs" / "contracts" / "factory_job.schema.json"


def load(name, config_dir=None):
    path = Path(config_dir or CONFIG_DIR) / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def bucket_ids():
    return tuple(b["id"] for b in load("taxonomy")["buckets"])


def people():
    """Board allow-list: actor id -> synthetic email (config/people.yaml)."""
    return load("people")["people"]


def squads():
    return tuple(load("taxonomy")["squads"])


def config_file_hashes(config_dir=None):
    d = Path(config_dir or CONFIG_DIR)
    return {n: hashlib.sha256((d / f"{n}.yaml").read_bytes().replace(b"\r\n", b"\n")).hexdigest() for n in CONFIG_FILES}


def config_hash(config_dir=None):
    h = config_file_hashes(config_dir)
    return hashlib.sha256("".join(f"{k}={h[k]}\n" for k in sorted(h)).encode()).hexdigest()


def find_env_file(cwd=None):
    """KEELWATER_ENV_FILE, else .env in the main checkout (parent of git's common dir). Never searches parents."""
    explicit = os.environ.get("KEELWATER_ENV_FILE")
    if explicit:
        return Path(explicit)
    cwd = Path(cwd or ROOT)
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=cwd, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return (cwd / out).resolve().parent / ".env"


def load_keys(cwd=None):
    """Return {name: value} from the env file (utf-8-sig) over process env. Values are never printed."""
    from dotenv import dotenv_values
    path = find_env_file(cwd)
    values = dotenv_values(path, encoding="utf-8-sig") if path and path.is_file() else {}
    names = ("OPENROUTER_API_KEY", "KEELWATER_AWS_KEY", "KEELWATER_SELFHOSTED_KEY")
    return {k: v for k, v in {**{k: os.environ.get(k) for k in names}, **values}.items() if v}
