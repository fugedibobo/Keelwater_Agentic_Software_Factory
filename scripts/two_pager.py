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
    if re.search(r"FOUND|INFERRED", md, re.I):  # working-with-AI labels do not belong in a document handed to people (#66)
        sys.exit("FOUND/INFERRED label in the source")
    body = markdown.markdown(md, extensions=["tables"])
    # Byline "Name, date" follows the h1: style it as a subtitle.
    body = re.sub(r"(</h1>\s*)<p>(Andras Fugedi, [^<]+)</p>", r'\1<p class="by">\2</p>', body, count=1)
    # #66: the two tables that are visuals get a class; the stylesheet draws them (stage chevrons, phase band).
    body = re.sub(r"<table>(\s*<thead>\s*<tr>\s*<th>Sense</th>)", r'<table class="leaks">\1', body, count=1)
    body = re.sub(r"<table>(\s*<thead>\s*<tr>\s*<th></th>\s*<th>Day 30</th>)", r'<table class="plan">\1', body, count=1)
    body = re.sub(r'<table class="leaks">.*?</table>',
                  lambda m: m.group(0).replace("<td>—</td>", '<td class="none">—</td>'), body, count=1, flags=re.S)
    body = re.sub(r"<table>(\s*<thead>\s*<tr>\s*<th>I leave alone)", r'<table class="split">\1', body, count=1)
    # short bullet lists run in two columns
    body = re.sub(r"(<p>(?:Adoption is the harder half:|Before adding squads[^<]*)</p>\s*)<ul>", r'\1<ul class="cols">', body)
    body = re.sub(r"(<blockquote>\s*<p><strong>Assumed[^<]*</strong></p>\s*)<ul>", r'\1<ul class="cols">', body)
    body = body.replace("<h2>3. ", '<h2 class="pb">3. ', 1)  # page 2 starts at section 3
    # #12: keep an intro paragraph with the table it introduces (part1.css only keeps h2 with the next block).
    keep = "<style>p:has(+ table){break-after:avoid}</style>"
    HTML.write_text(
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        "<title>Keelwater: product lifecycle diagnosis and 90-day plan</title>"
        '<link rel="stylesheet" href="part1.css">' + keep + "</head><body>" + body + "</body></html>",
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
