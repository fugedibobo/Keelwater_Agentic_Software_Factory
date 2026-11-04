"""FastAPI app: JSON API of docs/signal-board.md section 9 plus the page. Local only (binds 127.0.0.1)."""

import getpass
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..contracts import (Row, AcceptBody, ConfirmTagBody, EditBody, LabelBody, MergeBody, ParkBody, ReassignBody,
                         RejectBody, RemoveTagBody, SplitBody, UndoBody)
from ..store import Store
from . import actions, read, render_static

HERE = Path(__file__).parent


class EditIn(EditBody):
    original_wrong: bool = False  # "was the original wrong?"; board-local so contracts.py stays untouched


class NoteIn(Row):
    note: str | None = None


def create_app(db, labels_dir=None, reports_dir=None):
    store = Store(db)
    b = actions.Board(store, labels_dir or config.ROOT / "labels" / "human", reports_dir)
    app = FastAPI(title="Signal Board", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.exception_handler(PermissionError)
    async def _403(_r, e):
        return JSONResponse({"detail": str(e)}, 403)

    @app.exception_handler(actions.Missing)
    async def _404(_r, e):
        return JSONResponse({"detail": str(e)}, 404)

    @app.exception_handler(actions.Conflict)
    async def _409(_r, e):
        return JSONResponse({"detail": str(e)}, 409)

    @app.exception_handler(actions.Invalid)
    async def _422(_r, e):
        return JSONResponse({"detail": str(e)}, 422)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return render_static.render_page(store, reports_dir, static=False)

    @app.get("/api/me")
    def me():
        user = getpass.getuser()
        return {"actor": user if user in config.people() else next(iter(config.people()))}

    @app.get("/diagrams/{name}")
    def diagram(name: str):
        if name not in dict(render_static.DIAGRAMS):
            raise HTTPException(404)
        path = config.ROOT / "docs" / "diagrams" / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/raw/{raw_id}", response_class=HTMLResponse)
    def raw(raw_id: str):
        import html
        import json
        r = read.raw_record(store, raw_id)
        if not r:
            raise HTTPException(404)
        return f"<!doctype html><meta charset=utf-8><title>Raw record</title><body><h1>{html.escape(r['source'])} {html.escape(r['source_id'])}</h1><p>Synthetic record.</p><pre>{html.escape(json.dumps(r['payload_json'], indent=2))}</pre>"

    # ---- reads ----
    @app.get("/api/runs/latest")
    def runs_latest():
        return read.run_info(store) or {}

    @app.get("/api/since-last-week")
    def since():
        return read.since_last_week(store)

    @app.get("/api/opportunities")
    def opps(status: str | None = None, bucket: str | None = None, squad: str | None = None):
        return read.opportunities(store, status, bucket, squad)

    @app.get("/api/opportunities/{oid}")
    def opp(oid: str):
        r = read.opportunity(store, oid)
        if r is None:
            raise HTTPException(404, f"unknown opportunity {oid}")
        return r

    @app.get("/api/labels/queue")
    def label_queue(x_actor: str | None = Header(None)):
        return read.label_queue(store, x_actor or None)

    @app.get("/api/pipeline")
    def pipeline():
        return read.pipeline(store)

    @app.get("/api/evals")
    def evals():
        return read.evals(store, reports_dir)

    @app.get("/api/handoffs")
    def handoffs():
        return read.handoffs(store)

    @app.get("/api/outtakes")
    def outtakes(kind: str | None = None):
        return read.outtakes(store, kind)

    @app.get("/api/audit")
    def audit(request: Request):
        qp = request.query_params  # `from` is a Python keyword, so read the query string directly
        table = qp.get("table") if qp.get("table") in ("audit_event", "model_call") else "audit_event"
        return read.audit(store, table, qp.get("run"), qp.get("stage"), qp.get("model"), qp.get("actor"), qp.get("from"), qp.get("to"),
                          qp.get("cached") in ("1", "true", "on"), qp.get("page", 1))

    # ---- writes (each one annotation + one audit_event; X-Actor must be a person) ----
    @app.post("/api/opportunities/{oid}/accept")
    def accept(oid: str, body: AcceptBody, x_actor: str = Header("")):
        return actions.accept(b, oid, x_actor, body.confirmed)

    @app.post("/api/opportunities/{oid}/merge")
    def merge(oid: str, body: MergeBody, x_actor: str = Header("")):
        return actions.merge(b, oid, x_actor, body.target_id)

    @app.post("/api/opportunities/{oid}/reject")
    def reject(oid: str, body: RejectBody, x_actor: str = Header("")):
        return actions.reject(b, oid, x_actor, body.reason_code.value, body.note)

    @app.post("/api/opportunities/{oid}/park")
    def park(oid: str, body: ParkBody, x_actor: str = Header("")):
        return actions.park(b, oid, x_actor, body.note)

    @app.post("/api/opportunities/{oid}/reassign")
    def reassign(oid: str, body: ReassignBody, x_actor: str = Header("")):
        return actions.do_reassign(b, oid, x_actor, body.squad)

    @app.post("/api/opportunities/{oid}/edit")
    def edit(oid: str, body: EditIn, x_actor: str = Header("")):
        return actions.edit(b, oid, x_actor, body.title, body.problem_statement, body.original_wrong)

    @app.post("/api/opportunities/{oid}/confirm_tag")
    def confirm_tag(oid: str, body: ConfirmTagBody = Body(default_factory=ConfirmTagBody), x_actor: str = Header("")):
        return actions.tag(b, oid, x_actor, True)

    @app.post("/api/opportunities/{oid}/remove_tag")
    def remove_tag(oid: str, body: RemoveTagBody = Body(default_factory=RemoveTagBody), x_actor: str = Header("")):
        return actions.tag(b, oid, x_actor, False, body.note)

    @app.post("/api/opportunities/{oid}/split")
    def split(oid: str, body: SplitBody):
        raise HTTPException(501, "split is designed, not built in v1")

    @app.post("/api/undo")
    def undo(body: UndoBody, x_actor: str = Header("")):
        return actions.undo(b, body.audit_event_id, x_actor)

    @app.post("/api/labels")
    def labels(body: LabelBody, x_actor: str = Header("")):
        return actions.add_label(b, x_actor, body)

    @app.post("/api/outtakes/{out_id}/accept")
    def outtake_accept(out_id: str, body: NoteIn = Body(default_factory=NoteIn), x_actor: str = Header("")):
        return actions.outtake(b, out_id, x_actor, "accepted", body.note)

    @app.post("/api/outtakes/{out_id}/reject")
    def outtake_reject(out_id: str, body: NoteIn = Body(default_factory=NoteIn), x_actor: str = Header("")):
        return actions.outtake(b, out_id, x_actor, "rejected", body.note)

    app.state.store = store
    return app
