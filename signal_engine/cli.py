"""keelwater command line (architecture section 11). Subcommands are lazy `module:function` strings.

Every subcommand except `run` hands its remaining argv to its function, so later issues own their own flags.
"""

import argparse
import sys

# name: (module:function, issue that builds it, help)
COMMANDS = {
    "generate": ("generator.cli:main", 2, "build synthetic exports and ground truth"),
    "probe": ("signal_engine.gateway:probe_main", 1, "one call per model stage with its real parameters"),
    "run": ("signal_engine.pipeline:run_pipeline", 1, "run the pipeline into a fresh store"),
    "eval": ("signal_engine.evals.cli:main", 7, "score the store against ground truth, labels and seed 43"),
    "labels": ("signal_engine.evals.labels:main", 7, "seed, import and export labels"),
    "handoff": ("signal_engine.handoff:main", 9, "draft the intent doc and factory job for an accepted opportunity"),
    "board": ("signal_engine.board.cli:main", 8, "serve the Signal Board"),
    "render": ("signal_engine.board.cli:main", 8, "write a static snapshot of the board"),
    "cache": ("signal_engine.gateway:cache_main", 1, "prune cached model responses"),
}


def run_parser():
    p = argparse.ArgumentParser(prog="keelwater run", description=COMMANDS["run"][2])
    p.add_argument("--profile", choices=["replay", "demo", "aws", "self-hosted"], default="replay")
    p.add_argument("--seed", type=int, choices=[42, 43], default=42)
    p.add_argument("--as-of", default="03/11/2026", help="DD/MM/YYYY, used for all recency maths")
    p.add_argument("--batch", choices=["all", "sep", "oct"], default="all")
    p.add_argument("--data", help="data root (default data/raw, or data/holdout/raw with --seed 43)")
    p.add_argument("--stages", help="comma-separated subset of pipeline stages")
    p.add_argument("--db", default=".local/keelwater.sqlite")
    p.add_argument("--cache-dir", default="fixtures/llm_cache")
    p.add_argument("--report-dir", default="reports")
    p.add_argument("--max-usd", type=float, default=1.00)
    p.add_argument("--phoenix", action="store_true")
    return p


def top_parser():
    p = argparse.ArgumentParser(prog="keelwater", description="Keelwater Signal Engine")
    sub = p.add_subparsers(dest="command", metavar="<command>", required=True)
    for name, (_, _, text) in COMMANDS.items():
        sub.add_parser(name, help=text, add_help=False)
    return p


def _load(spec):
    from .pipeline import resolve
    return resolve(spec)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        top_parser().parse_args(argv or ["--help"])
        return 2
    name, rest = argv[0], argv[1:]
    spec, issue, _ = COMMANDS[name]
    arg = run_parser().parse_args(rest) if name == "run" else rest
    fn = _load(spec)
    if fn is None:
        print(f"not built yet: see issue #{issue}")
        return 2
    return fn(arg)


if __name__ == "__main__":
    raise SystemExit(main())
