"""Renders the board page with Jinja: live (served by app.py) or static (one index.html that opens from file://)."""

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config
from ..contracts import ReasonCode, Status
from ..store import Store
from . import read

HERE = Path(__file__).parent
DIAGRAMS = (("production-architecture.html", "Architecture"), ("agentic-pdlc.html", "Product development lifecycle"))
ENV = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
ENV.filters["md"] = read.md
ENV.filters["uk"] = read.uk


def _scrub(value):
    """Drop the local checkout path from exported audit data (rows written before ids became repo-relative)."""
    if isinstance(value, str):
        for root in {str(config.ROOT), config.ROOT.as_posix()}:
            if root in value:
                value = value.replace(root, "").lstrip("\\/").replace("\\", "/")
        return value
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return [_scrub(v) for v in value] if isinstance(value, list) else value


def context(store, reports_dir, static):
    listing = read.opportunities(store)
    opps = [read.opportunity(store, o["opportunity_id"], listing) for o in listing]
    aud = read.audit_both(store)
    aud["audit_event"]["rows"] = [_scrub(r) for r in aud["audit_event"]["rows"]]
    prefix = "diagrams/" if static else "/diagrams/"
    return dict(
        static=static, hdr=read.header(store), strip=read.since_last_week(store), opps=opps, tagq=read.tag_queue(store),
        labelq=read.label_queue(store), buckets=read.buckets(), squads=read.squads(), statuses=[s.value for s in Status],
        reasons=[r.value for r in ReasonCode], handoffs=read.handoffs(store), outtakes=read.outtakes(store), pipe=read.pipeline(store),
        ev=read.evals(store, reports_dir), aud=aud, diagrams=[dict(src=prefix + f, title=t, exists=(config.ROOT / "docs" / "diagrams" / f).is_file()) for f, t in DIAGRAMS],
        raw_href=(lambda rid: f"#raw-{rid}") if static else (lambda rid: f"/raw/{rid}"),
        raws=[read.raw_record(store, e["raw_id"]) for o in opps for e in o["evidence"]] if static else [],
        data={"run_id": (read.latest_run(store) or {}).get("run_id"), "audit": {t: v["rows"] for t, v in aud.items()}},
    )


def render_page(store, reports_dir, static=False):
    ctx = context(store, reports_dir, static)
    if static:
        ctx.update(css=(HERE / "static" / "board.css").read_text(encoding="utf-8"), js=(HERE / "static" / "board.js").read_text(encoding="utf-8"))
    return ENV.get_template("index.html").render(**ctx)


def write_static(db, out_dir, reports_dir=None):
    """Write out_dir/index.html (data inlined, no fetch) and copy the Archify diagrams beside it."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store = Store(db)
    try:
        html = render_page(store, reports_dir, static=True)
    finally:
        store.close()
    (out / "index.html").write_text(html, encoding="utf-8")
    for f, _ in DIAGRAMS:
        src = config.ROOT / "docs" / "diagrams" / f
        if src.is_file():
            (out / "diagrams").mkdir(exist_ok=True)
            shutil.copyfile(src, out / "diagrams" / f)
    return out / "index.html"
