"""`keelwater board serve` and `keelwater render static` (both reach main with their own argv)."""

import argparse
from pathlib import Path

from .. import config


def _reports(db, given):
    if given:
        return Path(given)
    near = Path(db).parent / "reports" / "eval"
    return near if near.is_dir() else config.ROOT / "reports" / "eval"


def main(argv):
    p = argparse.ArgumentParser(prog="keelwater board|render")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "static"):
        s = sub.add_parser(name)
        s.add_argument("--db", default=".local/keelwater.sqlite")
        s.add_argument("--reports", help="folder with <suite>-*.json eval reports (default: reports/eval beside the db, else the repo's)")
        if name == "serve":
            s.add_argument("--host", default="127.0.0.1")
            s.add_argument("--port", type=int, default=8000)
            s.add_argument("--labels-dir", default=str(config.ROOT / "labels" / "human"))
        else:
            s.add_argument("--out", default="site")
    a = p.parse_args(argv)
    if not Path(a.db).is_file():
        print(f"no store at {a.db}")
        return 2
    if a.cmd == "static":
        from .render_static import write_static
        print(write_static(a.db, a.out, _reports(a.db, a.reports)))
        return 0
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(a.db, a.labels_dir, _reports(a.db, a.reports)), host=a.host, port=a.port, log_level="warning")
    return 0
