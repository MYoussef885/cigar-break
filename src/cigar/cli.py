"""`cigar` command line: status, report, share and mode (FR-C6)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cigar import __version__, config, status
from cigar.store import Store, project_hash

MODE_HELP = {
    "suggest": "Cigar nudges the agent and you when the session shows fatigue (default).",
    "observe": "Cigar records signals only, with no nudges.",
    "auto": (
        "After a handoff is saved, Cigar clears the context itself at the end of the turn and "
        "restores the handoff. Needs plugin mods (Claude Code 2.1.287 or newer); tested in the "
        "terminal CLI only."
    ),
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
    path = config.write_value(cfg.home, "mode", args.mode)
    note = ""
    if os.environ.get("CIGAR_MODE") and os.environ["CIGAR_MODE"] != args.mode:
        note = f" Note: CIGAR_MODE={os.environ['CIGAR_MODE']} is set and overrides it."
    print(f"Mode set to {args.mode} in {path}. {MODE_HELP[args.mode]}{note}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from cigar import report, track

    cfg = config.load()
    with Store.open(cfg.db_path) as store:
        fits = track.refresh_knees(store, force=True) or []
        compactions = store.compaction_tokens()
    print(report.render_text(fits, compactions))
    if args.html or args.open:
        path = report.write_html(cfg.home, report.render_html(fits, compactions))
        print(f"\nHTML report: {path}")
        if args.open:
            import webbrowser

            webbrowser.open(path.as_uri())
    return 0


def cmd_share(args: argparse.Namespace) -> int:
    from cigar import share, track

    cfg = config.load()
    with Store.open(cfg.db_path) as store:
        fits = track.refresh_knees(store, force=True) or []
        harnesses = track.harnesses(store)
    return share.run(
        cfg,
        fits,
        harnesses,
        model=args.model,
        window=args.window,
        dry_run=args.dry_run,
        yes=args.yes,
        skill=args.skill,
    )


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

    p_report = sub.add_parser("report", help="your signal rate by context size, per model")
    p_report.add_argument("--html", action="store_true", help="also write the HTML report")
    p_report.add_argument("--open", action="store_true", help="write the HTML and open it")
    p_report.set_defaults(func=cmd_report)

    p_share = sub.add_parser("share", help="share your anonymous curve (opt-in, shows it first)")
    p_share.add_argument("--dry-run", action="store_true", help="print the payload only")
    p_share.add_argument("--yes", action="store_true", help="skip the confirmation question")
    p_share.add_argument("--model", help="which model's curve (default: the most data)")
    p_share.add_argument("--window", choices=["200k", "1m"], help="which context window")
    p_share.add_argument("--skill", help=argparse.SUPPRESS)  # /cigar:share passes its argument
    p_share.set_defaults(func=cmd_share)

    p_mode = sub.add_parser("mode", help="show or set the mode")
    p_mode.add_argument("mode", nargs="?", help="suggest, observe or auto")
    p_mode.set_defaults(func=cmd_mode)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
