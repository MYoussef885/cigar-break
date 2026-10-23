"""`cigar` command line: status and mode (FR-C6). Report and share arrive in Session 2."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cigar import __version__, config, status
from cigar.store import Store, project_hash

AUTO_UNAVAILABLE = (
    "Auto mode is unavailable: in testing (D-007), a plugin could not start a /clear on the "
    "developer's behalf, so Cigar can only suggest a break. Modes available: suggest, observe."
)

MODE_HELP = {
    "suggest": "Cigar nudges the agent and you when the session shows fatigue (default).",
    "observe": "Cigar records signals only, with no nudges.",
    "auto": "Cigar would reset the context without you (only if supported).",
}


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load()
    project_dir = args.project or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    project = project_hash(str(Path(project_dir)))
    with Store.open(cfg.db_path) as store:
        info = status.collect(store, cfg, args.session, project)
    print(json.dumps(info, indent=2) if args.json else status.render(info))
    return 0


def cmd_mode(args: argparse.Namespace) -> int:
    cfg = config.load()
    mode = (args.mode or "").strip().lower()
    if not mode:
        print(f"Mode: {cfg.mode}. {MODE_HELP[cfg.mode]}")
        return 0
    if mode not in config.MODES:
        print(f"Unknown mode {mode!r}. Choose one of: {', '.join(config.MODES)}.")
        return 2
    args.mode = mode
    if args.mode == "auto" and not status.AUTO_AVAILABLE:
        print(AUTO_UNAVAILABLE)
        return 1
    path = config.write_value(cfg.home, "mode", args.mode)
    note = ""
    if os.environ.get("CIGAR_MODE") and os.environ["CIGAR_MODE"] != args.mode:
        note = f" Note: CIGAR_MODE={os.environ['CIGAR_MODE']} is set and overrides it."
    print(f"Mode set to {args.mode} in {path}. {MODE_HELP[args.mode]}{note}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cigar", description="Cigar: take a break before the context rots."
    )
    parser.add_argument("--version", action="version", version=f"cigar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="score, context size, knee, recent signals and mode")
    p_status.add_argument("--session", help="session ID (default: the latest in this project)")
    p_status.add_argument("--project", help="project directory (default: current directory)")
    p_status.add_argument("--json", action="store_true", help="print JSON")
    p_status.set_defaults(func=cmd_status)

    p_mode = sub.add_parser("mode", help="show or set the mode")
    p_mode.add_argument("mode", nargs="?", help="suggest, observe or auto")
    p_mode.set_defaults(func=cmd_mode)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
