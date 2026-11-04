"""Build docs/keelwater-part1-two-pager.pdf from docs/part1-diagnosis-and-plan.md.

Run: uv run --with markdown python scripts/two_pager.py   (EDGE_PATH overrides msedge.exe)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "part1-diagnosis-and-plan.md"
HTML = ROOT / "docs" / "two-pager" / "part1.html"
PDF = ROOT / "docs" / "keelwater-part1-two-pager.pdf"


def edge() -> str:
    cands = [os.environ.get("EDGE_PATH", "")] + [
        os.path.join(os.environ.get(v, ""), "Microsoft", "Edge", "Application", "msedge.exe")
        for v in ("ProgramFiles(x86)", "ProgramFiles")
    ]
    for c in cands:
        if c and Path(c).is_file():
            return c
    sys.exit("msedge.exe not found; set EDGE_PATH")


def main() -> None:
    md = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables", "footnotes"])
    # Byline "Name, date" follows the h1: style it as a subtitle.
    body = re.sub(r"(</h1>\s*)<p>(Andras Fugedi, [^<]+)</p>", r'\1<p class="by">\2</p>', body, count=1)
    HTML.write_text(
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        "<title>Keelwater: product lifecycle diagnosis and 90-day plan</title>"
        '<link rel="stylesheet" href="part1.css"></head><body>' + body + "</body></html>",
        encoding="utf-8",
    )
    profile = tempfile.mkdtemp(prefix="edge-prof-")
    try:
        subprocess.run(
            [edge(), "--headless", f"--print-to-pdf={PDF}", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", "--disable-gpu", HTML.as_uri()],
            check=True, timeout=120, capture_output=True,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    from pypdf import PdfReader  # run with: --with markdown --with pypdf
    r = PdfReader(str(PDF))
    sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
    print(f"pages={len(r.pages)} size_pt={sorted(sizes)}")


if __name__ == "__main__":
    main()
