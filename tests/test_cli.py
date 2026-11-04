import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from signal_engine import cli, contracts as c
from signal_engine.store import Store

ROOT = Path(__file__).resolve().parent.parent
SUBCOMMANDS = ["generate", "probe", "run", "eval", "labels", "handoff", "board", "render", "cache"]


def keelwater(*args, env=None, cwd=ROOT):
    e = {**os.environ, "KEELWATER_ENV_FILE": str(cwd / ".scratch" / "absent.env"), **(env or {})}
    return subprocess.run([sys.executable, "-m", "signal_engine.cli", *args], cwd=cwd, env=e, capture_output=True,
                          text=True, encoding="utf-8")


def test_help_lists_exactly_the_section_11_subcommands():
    out = keelwater("--help").stdout
    listed = re.findall(r"^    (\w+)\s{2,}", out, re.M)
    assert listed == SUBCOMMANDS == list(cli.COMMANDS)


def test_unbuilt_subcommand_prints_issue_and_exits_2():
    r = keelwater("eval", "--suite", "all")
    assert r.returncode == 2 and r.stdout.strip() == "not built yet: see issue #7"
    assert keelwater("generate", "--seed", "42").stdout.strip() == "not built yet: see issue #2"


def test_unknown_subcommand_is_an_error():
    assert keelwater("frobnicate").returncode == 2


def test_argv_reaches_the_module_main_untouched(tmp_path, monkeypatch, capsys):
    (tmp_path / "dummy_cmd.py").write_text("seen = []\ndef main(argv):\n    seen.append(argv)\n    return 7\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(cli.COMMANDS, "generate", ("dummy_cmd:main", 2, "x"))
    assert cli.main(["generate", "--seed", "43", "--dry-run", "--max-usd", "1"]) == 7
    import dummy_cmd
    assert dummy_cmd.seen == [["--seed", "43", "--dry-run", "--max-usd", "1"]]


def test_module_without_the_function_counts_as_not_built(tmp_path, monkeypatch, capsys):
    (tmp_path / "dummy_empty.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(cli.COMMANDS, "labels", ("dummy_empty:main", 7, "x"))
    assert cli.main(["labels", "seed"]) == 2 and "see issue #7" in capsys.readouterr().out


def test_stdout_is_utf8_even_when_the_pipe_is_not(tmp_path):
    (tmp_path / "dummy_utf.py").write_text("def main(argv):\n    print('\\u2265 \\u03c4 \\u00a3')\n    return 0\n", encoding="utf-8")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from signal_engine import cli; "
            "cli.COMMANDS['generate'] = ('dummy_utf:main', 2, 'x'); raise SystemExit(cli.main(['generate']))")
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "cp1252", "KEELWATER_ENV_FILE": str(tmp_path / "x")})
    assert r.returncode == 0 and r.stdout.strip() == "\u2265 \u03c4 \u00a3"


def test_run_with_no_env_and_no_network_writes_store_report_and_hash(tmp_path):
    db, rep = tmp_path / "k.sqlite", tmp_path / "reports"
    r = keelwater("run", "--data", "tests/fixtures/raw", "--db", str(db), "--report-dir", str(rep))
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert sum(l.endswith(": skipped (not built)") for l in lines) == 10  # 12 stages minus brief and judge (#6); each later stage lowers this
    assert any(re.fullmatch(r"output hash: [0-9a-f]{64}", l) for l in lines)
    store = Store(db)
    assert {t[0] for t in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == set(c.TABLES)
    (run,) = store.select("run")
    assert run["status"] == "done" and run["as_of"] == "2026-11-03" and run["profile"] == "replay" and run["seed"] == 42
    for k in ("data_hash", "config_hash", "prompt_versions", "model_ids", "batch"):
        assert run[k] not in (None, "")
    assert run["model_ids"]["extract"] == "openai/gpt-oss-120b"
    report = rep / "runs" / "latest-replay.json"
    assert report.is_file() and report.read_bytes().count(b"\r") == 0


def test_default_run_works_in_the_repo_checkout_state():
    """`keelwater run` with the defaults must exit 0 even before any data exists; it recreates .local/."""
    r = keelwater("run", "--db", str(ROOT / ".scratch" / "default.sqlite"), "--report-dir", str(ROOT / ".scratch" / "rep"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_run_flags_are_the_architecture_section_11_set():
    a = cli.run_parser().parse_args([])
    assert (a.profile, a.seed, a.batch, a.as_of, a.max_usd) == ("replay", 42, "all", "03/11/2026", 1.0)
    for flag in ("--data", "--stages", "--db", "--cache-dir", "--report-dir", "--max-usd", "--phoenix", "--as-of", "--batch", "--seed", "--profile"):
        assert flag in cli.run_parser().format_help()
