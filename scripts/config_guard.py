"""D-027 guard: snapshot the developer's real Claude Code and Cigar config, then diff it.

    python3 scripts/config_guard.py snapshot <file>   # before a probe
    python3 scripts/config_guard.py diff <file>       # after it; exit 1 on any change

It records file hashes, plus the top-level keys of ~/.claude.json (whose
"projects" entry and usage counters Claude Code itself rewrites constantly).
It reads only; it never writes outside <file>.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HOME = Path.home()
FILES = (
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/keybindings.json",
    ".claude/plugins/installed_plugins.json",
    ".claude/plugins/known_marketplaces.json",
    ".cigar/config.toml",
)
# ~/.claude.json keys that the running Claude Code updates on its own.
VOLATILE = ("projects", "numStartups", "tipsHistory", "cached", "lastPlanModeUse", "promptQueue")


def _hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def snapshot() -> dict[str, object]:
    state: dict[str, object] = {name: _hash(HOME / name) for name in FILES}
    state[".cigar exists"] = (HOME / ".cigar").exists()
    try:
        top = json.loads((HOME / ".claude.json").read_text())
    except (OSError, ValueError):
        top = {}
    for key, value in top.items():
        if not key.startswith(VOLATILE):
            text = json.dumps(value, sort_keys=True, default=str)
            state[f"~/.claude.json:{key}"] = hashlib.sha256(text.encode()).hexdigest()
    return state


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("snapshot", "diff"):
        print(__doc__)
        return 2
    out = Path(argv[1])
    if argv[0] == "snapshot":
        out.write_text(json.dumps(snapshot(), indent=1, sort_keys=True))
        print(f"snapshot saved: {len(snapshot())} entries")
        return 0
    before = json.loads(out.read_text())
    after = snapshot()
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if changed:
        print("CHANGED owner config: " + ", ".join(changed))
        return 1
    print(f"owner config unchanged ({len(after)} entries checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
