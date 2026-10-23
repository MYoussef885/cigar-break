"""Auto mode markers (D-007, D-021).

In `auto` mode a successful take_break writes <CIGAR_HOME>/auto/<session id>.json
with state "ready". The mod in mods/auto.ts reads it at the end of the turn,
marks it "fired" and runs /clear. Only these markers cross between the two.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

MAX_AGE_SECONDS = 24 * 3600


def marker_path(home: Path, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return home / "auto" / f"{safe}.json"


def mark_ready(home: Path, session_id: str) -> Path:
    path = marker_path(home, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"state": "ready", "session": session_id, "ts": time.time()}))
    tmp.replace(path)
    return path


def prune(home: Path, max_age: float = MAX_AGE_SECONDS) -> None:
    """Remove fired markers and any older than max_age."""
    folder = home / "auto"
    if not folder.is_dir():
        return
    cutoff = time.time() - max_age
    for path in folder.glob("*.json"):
        try:
            fired = json.loads(path.read_text()).get("state") == "fired"
            if fired or path.stat().st_mtime < cutoff:
                path.unlink()
        except (OSError, ValueError, AttributeError):
            path.unlink(missing_ok=True)
