"""Build site/presentation/index.html from scripts/deck_template.html, the charts in scripts/deck_charts.py and three images.

    uv run python scripts/build_deck.py                 images from the repo (main fba88af after PR #69)
    uv run python scripts/build_deck.py --images DIR    images from DIR (pipeline.png, board-about.png, board-opportunities.png)

The images are downscaled and re-encoded by headless Edge (no Python imaging library here) and embedded as data URIs.
Refresh after the board or pipeline pictures change: re-run this command, then run tests/test_presentation.py.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import deck_charts  # noqa: E402

EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
# placeholder -> (default file in the repo, mime type, output width in px, quality, crop x/y/w/h in source px or None)
# IMG_OPPS keeps one opportunity card (score, factors, check line) of the 2880x1800 screenshot.
IMAGES = {"IMG_PIPELINE": ("docs/diagrams/pipeline.png", "image/webp", 900, 0.9, None),
          "IMG_ABOUT": ("docs/screenshots/board-about.png", "image/jpeg", 1500, 0.8, None),
          "IMG_OPPS": ("docs/screenshots/board-opportunities.png", "image/jpeg", 2000, 0.85, [300, 1050, 2280, 720])}
JS = """const jobs=%s;const res={};let left=jobs.length;
jobs.forEach(([k,src,t,w,q,cr])=>{const im=new Image();im.onload=()=>{const c=document.createElement('canvas');c.width=w;
const [sx,sy,sw,sh]=cr||[0,0,im.naturalWidth,im.naturalHeight];c.height=Math.round(sh*w/sw);
const x=c.getContext('2d');x.imageSmoothingQuality='high';x.drawImage(im,sx,sy,sw,sh,0,0,c.width,c.height);res[k]=c.toDataURL(t,q);if(--left==0)document.getElementById('out').textContent=JSON.stringify(res)};
im.onerror=()=>{document.getElementById('out').textContent='ERR '+k};im.src=src});"""


def encode_images(folder):
    jobs = []
    for key, (rel, mime, w, q, crop) in IMAGES.items():
        p = (Path(folder) / Path(rel).name) if folder else ROOT / rel
        jobs.append([key, p.resolve().as_uri(), mime, w, q, crop])
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "enc.html"
        page.write_text('<!doctype html><meta charset="utf-8"><pre id="out">pending</pre><script>' + JS % json.dumps(jobs) + "</script>", encoding="utf-8")
        r = subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=30000",
                            "--dump-dom", page.as_uri()], capture_output=True, text=True, encoding="utf-8", timeout=120)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    if not m or not m.group(1).startswith("{"):
        sys.exit("image encoding failed: " + (m.group(1)[:80] if m else "no output"))
    return json.loads(m.group(1))


def build(folder=None, out=None):
    html = (ROOT / "scripts" / "deck_template.html").read_text(encoding="utf-8")
    pieces = {k: fn() for k, fn in deck_charts.PIECES.items()}
    pieces.update(encode_images(folder))
    for k, v in pieces.items():
        html = html.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if left:
        sys.exit(f"unfilled placeholders: {sorted(set(left))}")
    out = Path(out or ROOT / "site" / "presentation" / "index.html")
    out.write_text(html, encoding="utf-8", newline="\n")
    return out, len(html.encode("utf-8"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", help="folder with pipeline.png, board-about.png, board-opportunities.png (default: the repo's own)")
    ap.add_argument("--out")
    a = ap.parse_args()
    print(*build(a.images, a.out))
