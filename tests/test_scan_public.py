"""scripts/scan_public.py with a temporary deny-list and fake .env; the real ones are never read."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan_public.py"
NAME = "Émile Kowalski"  # planted fake name
FAKE_KEY = "zz" + "fake9876543210value"


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args], cwd=repo,
                   check=True, capture_output=True, encoding="utf-8")


def scan(repo, deny, env, *flags):
    e = {**os.environ, "KEELWATER_DENYLIST": str(deny), "KEELWATER_ENV": str(env)}
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(repo), *flags], env=e,
                       capture_output=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def test_finds_name_any_case_and_accent_without_printing_it(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.md").write_text("Met EMILE KOWALSKI today.\nclean line\n", encoding="utf-8")
    (repo / "b.md").write_text("see émile kowalski here; emile kowalskis is a different word\n", encoding="utf-8")
    (repo / "c.txt").write_text(f"note {FAKE_KEY}\n", encoding="utf-8")
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "commit mentions Emile Kowalski")
    deny = tmp_path / "deny.txt"
    deny.write_text(f"# comment\nOther Person\n{NAME}\n", encoding="utf-8")
    env = tmp_path / "fake.env"
    env.write_text(f"FAKE_API_KEY={FAKE_KEY}\n", encoding="utf-8")

    code, out = scan(repo, deny, env, "--history")
    assert code == 1
    assert "a.md:1 deny-list entry 2" in out and "b.md:1 deny-list entry 2" in out
    assert "history:" in out
    assert "c.txt:1 .env value 1" in out
    assert ".env:0 tracked env file" in out
    assert "emile" not in out.lower() and "kowalski" not in out.lower() and FAKE_KEY not in out


def test_clean_repo_has_zero_hits(tmp_path):
    repo = tmp_path / "clean"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "ok.md").write_text("nothing here; emile kowalskis is not the name\n", encoding="utf-8")
    deny = tmp_path / "deny.txt"
    deny.write_text(NAME + "\n", encoding="utf-8")
    code, out = scan(repo, deny, tmp_path / "missing.env")
    assert code == 0 and "0 hits" in out
