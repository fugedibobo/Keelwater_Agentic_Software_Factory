"""The presentation deck (site/presentation/index.html) is one self-contained file: no network, keyboard-driven."""
import re
from html.parser import HTMLParser
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "site" / "presentation" / "index.html"
HTML = FILE.read_text(encoding="utf-8")


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []  # (tag, attrs dict)
        self.anchors = []  # (href, visible text)
        self._a = None

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "a":
            self._a = [dict(attrs).get("href", ""), ""]

    def handle_data(self, data):
        if self._a is not None:
            self._a[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.anchors.append(tuple(self._a))
            self._a = None


SCAN = Scan()
SCAN.feed(HTML)


def test_file_exists_and_is_one_page():
    assert FILE.is_file()
    assert HTML.lstrip().lower().startswith("<!doctype html>")
    assert FILE.stat().st_size < 6 * 1024 * 1024


def test_slide_count():
    assert 6 <= HTML.count("<section") <= 8


def test_no_external_requests():
    assert 'src="http' not in HTML and "src='http" not in HTML
    assert not re.search(r"url\(\s*['\"]?https?:", HTML)
    assert "@import" not in HTML
    assert "fetch(" not in HTML and "XMLHttpRequest" not in HTML
    for tag, attrs in SCAN.tags:
        if tag == "link":
            assert not (attrs.get("href") or "").startswith(("http:", "https:", "//"))


def test_http_only_in_anchor_hrefs_that_show_the_url():
    for tag, attrs in SCAN.tags:
        for name, value in attrs.items():
            if tag == "a" and name == "href":
                continue
            assert "http://" not in (value or "") and "https://" not in (value or ""), (tag, name)
    for href, text in SCAN.anchors:
        if href.startswith(("http://", "https://")):
            assert text.strip() == href, f"link text must be the URL itself: {href}"


def test_keyboard_handlers():
    for key in ("ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown"):
        assert f'"{key}"' in HTML, key
    assert "hashchange" in HTML and "prefers-reduced-motion" in HTML and "@media print" in HTML


def test_markers_for_refresh():
    assert HTML.count("<!-- EVAL-RESULTS START -->") == 1 and HTML.count("<!-- EVAL-RESULTS END -->") == 1
    n = HTML.count("<!-- TELEMETRY START -->")
    assert n >= 1 and n == HTML.count("<!-- TELEMETRY END -->")
    a, b = HTML.index("<!-- EVAL-RESULTS START -->"), HTML.index("<!-- EVAL-RESULTS END -->")
    assert a < b and "FAIL" in HTML[a:b]


def test_accessibility_basics():
    assert all(a.get("alt") for t, a in SCAN.tags if t == "img")
    assert all(a.get("role") == "img" or a.get("aria-hidden") for t, a in SCAN.tags if t == "svg" and "class" in a and "chart" in a["class"])
    assert all(a.get("aria-labelledby") for t, a in SCAN.tags if t == "section")
    assert 'lang="en-GB"' in HTML


def test_house_style():
    assert "—" not in HTML and "–" not in HTML  # no em or en dashes
    low = HTML.lower()
    assert "interview" not in low and "assessment" not in low
