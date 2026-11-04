"""Pre-publish scan (issue #13). Exit 0 only when there are 0 hits.

Checks the working tree (git ls-files plus untracked, non-ignored files), optionally all git history
(--history) and issue/PR bodies and comments (--github, via gh) for: names on the deny-list (ignoring
case and accents, at word boundaries), key-like strings, values from the main checkout's .env, and a
tracked .env. Hits print as `<where>:<line> <kind> entry <n>`; a name or key value is never printed.

Deny-list: KEELWATER_DENYLIST, else ~/keelwater-denylist.txt (one name per line, # comments).
Env file: KEELWATER_ENV, else .env in the main checkout (parent of git's common dir).
"""

import argparse
import codecs
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c))


def sh(args, cwd):
    r = subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


def decode(data):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    return None if 0 in data else data.decode("utf-8", errors="replace")


KEY_PATTERNS = [re.compile(p) for p in (
    r"sk-or-v1-[A-Za-z0-9]{16,}", r"\bsk-[A-Za-z0-9_-]{32,}", r"\bAKIA[0-9A-Z]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    # unquoted values must contain a digit, so code like `token = relationshipTokenGeometry(` is not a hit
    r"(?i)\b[a-z_]*(?:api_?key|secret|token)[a-z_]*\s*[:=]\s*(?:['\"][A-Za-z0-9_\-]{24,}|(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,})",
)]


class Scanner:
    def __init__(self, names, env_values):
        self.res = [re.compile(r"(?<!\w)" + re.escape(fold(n)) + r"(?!\w)") for n in names]
        self.env_values = env_values
        self.hits = []
        self.path_ids = {}

    def kinds(self, line):
        f = fold(line)
        out = [f"deny-list entry {n}" for n, rx in enumerate(self.res, 1) if rx.search(f)]
        if any(p.search(line) for p in KEY_PATTERNS):
            out.append("key-like string")
        out += [f".env value {n}" for n, v in enumerate(self.env_values, 1) if v in line]
        return out

    def text(self, where, text):
        for i, line in enumerate(text.splitlines(), 1):
            for k in self.kinds(line):
                self.hits.append(f"{where}:{i} {k}")

    def label(self, path):
        """The path itself when clean; a numbered placeholder (and hits) when the path string matches."""
        ks = self.kinds(path)
        if not ks:
            return path
        label = f"path entry {self.path_ids.setdefault(path, len(self.path_ids) + 1)}"
        self.hits += [f"{label}:0 {k}" for k in ks]
        return label


def read_names(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.strip().startswith("#")]


def read_env_values(path):
    p = Path(path)
    if not p.is_file():
        return []
    vals = []
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        k, sep, v = line.partition("=")
        v = v.strip().strip("'\"")
        if sep and len(v) >= 8 and re.search(r"KEY|TOKEN|SECRET", k.upper()):
            vals.append(v)
    return vals


def scan_tree(sc, root):
    _, tracked = sh(["git", "ls-files", "-z"], root)
    _, other = sh(["git", "ls-files", "-z", "-o", "--exclude-standard"], root)
    tracked_set = set(tracked.split("\0"))
    for name in [n for n in (tracked + other).split(chr(0)) if n]:
        base = Path(name).name
        shown = sc.label(name)
        if name in tracked_set and (base == ".env" or (base.startswith(".env.") and base != ".env.example")):
            sc.hits.append(f"{shown}:0 tracked env file")
        p = Path(root) / name
        if not p.is_file():
            continue
        text = decode(p.read_bytes())
        if text is not None:
            sc.text(shown, text)


def scan_history(sc, root):
    code, _ = sh(["git", "fetch", "origin", "+refs/pull/*/head:refs/remotes/pr/*"], root)
    if code:
        print("warning: PR heads not fetched (no origin?)", file=sys.stderr)
    _, log = sh(["git", "-c", "core.quotepath=off", "log", "--all", "-p", "-m", "--no-color",
                 "--format=@@COMMIT@@%H%n%an <%ae>%n%cn <%ce>%n%B"], root)
    sha, buf = "none", []
    for line in log.splitlines() + ["@@COMMIT@@end"]:
        if line.startswith("@@COMMIT@@"):
            if buf:
                sc.text(f"history:{sha[:8]}", "\n".join(buf))
            sha, buf = line[10:], []
        else:
            buf.append(line)
    _, paths = sh(["git", "-c", "core.quotepath=off", "log", "--all", "-m", "--name-only", "--format="], root)
    for path in sorted(set(paths.splitlines())):
        if path:
            sc.label(path)
    _, refs = sh(["git", "for-each-ref", "--format=%(refname)%0a%(taggername) %(taggeremail)%0a%(contents)%0a@@REF@@"], root)
    for i, ref in enumerate(refs.split("@@REF@@"), 1):
        sc.text(f"history:ref {i}", ref)


def gh_lines(root, endpoint):
    code, out = sh(["gh", "api", "--paginate", endpoint, "--jq", ".[]"], root)
    if code:
        return None
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def scan_github(sc, root):
    for kind, fields in (("issue", "number,title,body,comments"), ("pr", "number,title,body,comments,reviews,headRefName")):
        code, out = sh(["gh", kind, "list", "--state", "all", "--limit", "1000000", "--json", fields], root)
        if code:
            sc.hits.append(f"github {kind}s:0 gh failed, not scanned")
            continue
        for item in json.loads(out):
            parts = [("title", item["title"]), ("body", item["body"]), ("head ref", item.get("headRefName"))]
            parts += [(f"comment{i}", c["body"]) for i, c in enumerate(item["comments"])]
            parts += [(f"review{i}", c["body"]) for i, c in enumerate(item.get("reviews", []))]
            for label, body in parts:
                sc.text(f"{kind}#{item['number']} {label}", body or "")
    for label, endpoint in (("pr-review-comment", "repos/{owner}/{repo}/pulls/comments"),
                            ("commit-comment", "repos/{owner}/{repo}/comments")):
        items = gh_lines(root, endpoint)
        if items is None:
            sc.hits.append(f"github {label}s:0 gh failed, not scanned")
            continue
        for c in items:
            sc.text(f"{label}#{c.get('id')}", c.get("body") or "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--history", action="store_true", help="also scan all git history and commit messages")
    ap.add_argument("--github", action="store_true", help="also scan issue and PR bodies and comments via gh")
    ap.add_argument("--root", default=".", help="repo to scan (default: current directory)")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    deny = os.environ.get("KEELWATER_DENYLIST") or str(Path.home() / "keelwater-denylist.txt")
    if not Path(deny).is_file():
        print("deny-list file not found: set KEELWATER_DENYLIST", file=sys.stderr)
        return 2
    env = os.environ.get("KEELWATER_ENV")
    if not env:
        _, common = sh(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root)
        env = str(Path(common.strip()).parent / ".env")
    if not Path(env).is_file():
        print("no .env found, env value check skipped", file=sys.stderr)
    sc = Scanner(read_names(deny), read_env_values(env))
    scan_tree(sc, root)
    if a.history:
        scan_history(sc, root)
    if a.github:
        scan_github(sc, root)
    hits = sorted(set(sc.hits))
    print("\n".join(hits))
    print(f"{len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
