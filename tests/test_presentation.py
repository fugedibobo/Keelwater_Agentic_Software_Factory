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
        self.slides = []  # per slide: {"bullets": n, "details": n}
        self._pts = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        a = dict(attrs)
        if tag == "section":
            self.slides.append({"bullets": 0, "details": 0})
        elif self.slides:
            if tag == "ul":
                self._pts = "pts" in (a.get("class") or "").split()
            elif tag == "li" and self._pts:
                self.slides[-1]["bullets"] += 1
            elif tag == "details":
                self.slides[-1]["details"] += 1
        if tag == "a":
            self._a = [dict(attrs).get("href", ""), ""]

    def handle_data(self, data):
        if self._a is not None:
            self._a[1] += data

    def handle_endtag(self, tag):
        if tag == "ul":
            self._pts = False
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
    assert HTML.count("<section") == 8 and len(SCAN.slides) == 8


def test_each_slide_has_at_most_three_bullets_and_one_to_three_expanders():
    for i, s in enumerate(SCAN.slides, 1):
        assert 1 <= s["bullets"] <= 3, (i, s)
        assert 1 <= s["details"] <= 3, (i, s)
    assert HTML.count("<summary>More: ") == sum(s["details"] for s in SCAN.slides)


def test_no_retired_model_names():
    for pat in (r"gpt-oss", r"qwen3-next", r"deepseek-v3\.2", r"glm-5\b"):
        assert not re.search(pat, HTML, re.I), pat
    low = HTML.lower()
    assert "clef" in low and "clef flash" in low  # triage reads Clef, falling back to Clef Flash


def test_no_evidence_labels_on_slides():
    body = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
    for word in ("FOUND", "INFERRED"):
        assert word not in body, word


def test_theme_is_light_by_default_and_storage_is_guarded():
    assert 'color-scheme:light' in HTML and "prefers-color-scheme" not in HTML  # dark only by the visitor's choice
    assert "data-theme=\"dark\"" in HTML
    # every localStorage use sits in its own try{...}catch(e){}
    uses = [m.start() for m in re.finditer(r"localStorage\.", HTML)]
    assert len(uses) == 2
    for i in uses:
        stmt = HTML[HTML.rfind("try{", 0, i):HTML.index("}catch", i)]
        assert "localStorage" in stmt and stmt.count("try{") == 1


def test_images_are_embedded_and_sources_named():
    assert HTML.count("src=\"data:image/") == 3
    assert "fba88af" in HTML and "docs/screenshots/board-about.png" in HTML


def test_space_and_enter_leave_summaries_alone():
    assert 'closest("summary,button,a")' in HTML and "<details>" in HTML


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
    assert "beforeprint" in HTML and "d.open=true" in HTML  # print shows every expander open


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


def test_headline_sticks_and_print_text_is_at_least_11pt():
    assert "position:sticky" in HTML
    print_css = HTML[HTML.index("@media print"):HTML.index("</style>")]
    assert "11pt" in print_css and not re.search(r"font-size:\s*(\d|10)(\.\d+)?(px|pt)", print_css)
