"""Auto mode markers (D-007, D-021, D-026).

In `auto` mode, once a handoff is saved for the session, the hook writes
<CIGAR_HOME>/auto/<session id>.json with state "ready" and the handoff's path.
The mod in mods/auto.ts reads it at the end of the turn, marks it "fired" and
runs /clear. With no marker, or one without a handoff path, it never clears.
Only these markers cross between the two.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

MAX_AGE_SECONDS = 24 * 3600
FIRED_MAX_AGE_SECONDS = 600  # a clear that fired longer ago than this is not "just now"


def marker_path(home: Path, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return home / "auto" / f"{safe}.json"


def mark_ready(home: Path, session_id: str, handoff: str) -> Path:
    path = marker_path(home, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    marker = {"state": "ready", "session": session_id, "handoff": handoff, "ts": time.time()}
    tmp.write_text(json.dumps(marker))
    tmp.replace(path)
    return path


def take_fired(home: Path, max_age: float = FIRED_MAX_AGE_SECONDS) -> str | None:
    """The handoff path of a clear the mod just fired, removing its marker."""
    folder = home / "auto"
    if not folder.is_dir():
        return None
    found: tuple[float, str] | None = None
    cutoff = time.time() - max_age
    for path in folder.glob("*.json"):
        try:
            marker = json.loads(path.read_text())
            if marker.get("state") != "fired" or path.stat().st_mtime < cutoff:
                continue
            handoff = marker.get("handoff")
            if isinstance(handoff, str) and handoff:
                stamp = path.stat().st_mtime
                if found is None or stamp > found[0]:
                    found = (stamp, handoff)
            path.unlink()
        except (OSError, ValueError, AttributeError):
            continue
    return found[1] if found else None


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
