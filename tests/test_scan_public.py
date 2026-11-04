"""scripts/scan_public.py with a temporary deny-list and fake .env; the real ones are never read."""

import json
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


def load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("scan_public_mod", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def setup(tmp_path, names=NAME):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    deny = tmp_path / "deny.txt"
    deny.write_text(names + "\n", encoding="utf-8")
    return repo, deny, tmp_path / "missing.env"


def assert_no_leak(out):
    low = out.lower()
    assert "emile" not in low and "kowalski" not in low


def test_file_name_is_scanned_and_not_printed(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "Emile Kowalski notes.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add")
    (repo / "untracked Emile Kowalski.txt").write_text("clean\n", encoding="utf-8")
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "path entry" in out and "deny-list entry 1" in out
    assert_no_leak(out)


def test_history_path_of_deleted_file_is_scanned(tmp_path):
    repo, deny, env = setup(tmp_path)
    f = repo / "Emile Kowalski.md"
    f.write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add")
    git(repo, "rm", "-q", f.name)
    git(repo, "commit", "-q", "-m", "rm")
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "path entry" in out
    assert_no_leak(out)


def test_commit_author_and_committer_identity(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "a.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "-c", "user.name=Emile Kowalski", "-c", "user.email=ek@example.test", "commit", "-q", "-m", "m"],
                   cwd=repo, check=True, capture_output=True)
    assert scan(repo, deny, env)[0] == 0
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "history:" in out
    assert_no_leak(out)


def test_committer_name_only(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "a.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", "m"], cwd=repo,
                   check=True, capture_output=True, env={**os.environ, "GIT_COMMITTER_NAME": "Emile Kowalski"})
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "history:" in out
    assert_no_leak(out)


def test_author_email_only(tmp_path):
    repo, deny, env = setup(tmp_path, "kowalski@example.test")
    (repo / "a.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=kowalski@example.test", "commit", "-q", "-m", "m"],
                   cwd=repo, check=True, capture_output=True)
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "kowalski" not in out.lower()


def test_annotated_tag_message_and_branch_name(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "a.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "m")
    git(repo, "tag", "-a", "v1", "-m", "release for Emile Kowalski")
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "history:" in out
    assert_no_leak(out)
    git(repo, "tag", "-d", "v1")
    assert scan(repo, deny, env, "--history")[0] == 0


def test_branch_name_with_space_like_match(tmp_path):
    repo, deny, env = setup(tmp_path, "Kowalski")
    (repo / "a.md").write_text("clean\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "m")
    git(repo, "branch", "fix/Kowalski")
    code, out = scan(repo, deny, env, "--history")
    assert code == 1 and "kowalski" not in out.lower()


def test_merge_commit_diff_is_scanned(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "a.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "b.md").write_text("b\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "side")
    git(repo, "checkout", "-q", "main")
    (repo / "c.md").write_text("c\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "main")
    git(repo, "merge", "-q", "--no-commit", "--no-ff", "side")
    (repo / "a.md").write_text("one\nEmile Kowalski evil merge\nthree\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "merge")
    git(repo, "branch", "-q", "-D", "side")
    m = load()
    sc = m.Scanner(["Emile Kowalski"], [])
    m.scan_history(sc, repo)
    assert any(h.startswith("history:") for h in sc.hits)


def test_utf16_file_is_scanned(tmp_path):
    repo, deny, env = setup(tmp_path)
    (repo / "u.txt").write_bytes("Emile Kowalski\n".encode("utf-16"))
    (repo / "b.txt").write_bytes("\x00\x01binary".encode("latin-1"))
    code, out = scan(repo, deny, env)
    assert code == 1 and "u.txt:1 deny-list entry 1" in out
    assert "b.txt" not in out


def test_missing_env_prints_note(tmp_path):
    repo, deny, env = setup(tmp_path)
    code, out = scan(repo, deny, env)
    assert "no .env found, env value check skipped" in out


def test_github_sources(tmp_path):
    m = load()
    calls = []

    def fake_sh(args, cwd):
        calls.append(args)
        if args[:2] == ["gh", "api"]:
            if "pulls/comments" in args[-1] or "pulls/comments" in " ".join(args):
                return 0, json.dumps({"body": "see Emile Kowalski", "id": 5}) + "\n"
            return 0, json.dumps({"body": "hi Emile Kowalski", "id": 6}) + "\n"
        if args[:2] == ["gh", "pr"]:
            return 0, json.dumps([{"number": 3, "title": "t", "body": "", "comments": [], "reviews": [], "headRefName": "Emile-Kowalski/fix"}])
        return 0, "[]"

    m.sh = fake_sh
    sc = m.Scanner(["Emile Kowalski", "Emile-Kowalski"], [])
    m.scan_github(sc, tmp_path)
    joined = "\n".join(sc.hits)
    assert "pr-review-comment#5" in joined and "commit-comment#6" in joined and "pr#3 head ref" in joined
    assert_no_leak(joined)
    assert not any("1000" in c for c in calls)
