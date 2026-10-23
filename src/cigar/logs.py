"""Local logs in ~/.cigar/logs/ (one file per day). Logging never raises."""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

from cigar import defaults
from cigar.config import cigar_home


def log_dir(home: Path | None = None) -> Path:
    return (home or cigar_home()) / "logs"


def write(line: str, home: Path | None = None) -> None:
    try:
        directory = log_dir(home)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(directory / f"cigar-{time.strftime('%Y-%m-%d')}.log", "a", encoding="utf-8") as f:
            f.write(f"{stamp} pid={os.getpid()} {line}\n")
    except Exception:
        pass


def error(context: str, exc: BaseException, home: Path | None = None) -> None:
    # Tracebacks carry code locations and exception messages, never payload values.
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
    write(f"ERROR {context}: {type(exc).__name__}: {exc}\n{detail}", home)


def prune(home: Path | None = None, days: int = defaults.LOG_RETENTION_DAYS) -> None:
    try:
        cutoff = time.time() - days * 86400
        for path in log_dir(home).glob("cigar-*.log"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
    except Exception:
        pass
