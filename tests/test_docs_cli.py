"""Every `keelwater <subcommand> <flags>` written in code in README.md and docs/*.md exists in the CLI.

The CLI's parsers live inside each subcommand's main(), so parse_args is intercepted: it parses the
documented flags (argparse exits on an unknown one) and then stops before anything runs.
"""

import argparse
import re
from pathlib import Path

import pytest

from signal_engine import cli

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
CODE = re.compile(r"```[a-z]*\n(.*?)```|`([^`\n]+)`", re.S)
CMD = re.compile(r"\bkeelwater ([a-z][a-z-]*)((?: [^\n#;&>`]*)?)")


class Parsed(Exception):
    pass


def documented():
    found = []
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        for m in CODE.finditer(text):
            for c in CMD.finditer(m.group(1) or m.group(2)):
                sub, rest = c.group(1), c.group(2)
                if sub not in cli.COMMANDS and sub in {"subcommand", "run-id"}:
                    continue
                rest = re.sub(r"<[^>]*>", "1", rest).replace("[", "").replace("]", "")
                args = [t.split("|")[0] for t in rest.split() if t not in {"|", "..."}]
                found.append(pytest.param(sub, args, id=f"{f.name}: keelwater {sub} {' '.join(args)}".strip()))
    return found


CASES = documented()


def test_docs_mention_commands():
    assert len(CASES) >= 15


@pytest.mark.parametrize("sub,args", CASES)
def test_documented_command_is_accepted(sub, args, monkeypatch):
    assert sub in cli.COMMANDS, f"unknown subcommand {sub}"
    real = argparse.ArgumentParser.parse_args

    def check(self, _args=None, namespace=None):
        real(self, args)  # SystemExit(2) on an unknown flag or bad value
        raise Parsed

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", check)
    try:
        cli.main([sub, *args])
    except Parsed:
        pass
    except SystemExit as e:
        pytest.fail(f"`keelwater {sub} {' '.join(args)}` rejected by its parser (exit {e.code})")
    # a subcommand not built on this branch returns 2 before parsing; its name is still checked above
