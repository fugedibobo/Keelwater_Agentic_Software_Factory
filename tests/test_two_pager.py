"""The Part 1 two-pager is handed to people: no working-with-AI labels, and exactly two A4 pages (#66)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LABEL = re.compile(r"FOUND|INFERRED", re.I)


def test_source_and_html_carry_no_labels():
    for rel in ("docs/part1-diagnosis-and-plan.md", "docs/two-pager/part1.html"):
        assert not LABEL.search((ROOT / rel).read_text(encoding="utf-8")), rel


def test_pdf_is_two_a4_pages_without_labels():
    pypdf = pytest.importorskip("pypdf")  # not a project dependency; the render script needs it
    r = pypdf.PdfReader(str(ROOT / "docs" / "keelwater-part1-two-pager.pdf"))
    assert len(r.pages) == 2
    assert {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages} == {(595, 842)}
    assert not LABEL.search("\n".join(p.extract_text() for p in r.pages))
