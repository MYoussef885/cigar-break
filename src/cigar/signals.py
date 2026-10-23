"""Signal detectors (architecture §6). Pure functions over events, no I/O.

`extract` turns one hook payload into an Event. `detect` names the signals
that event shows, given the session's earlier main-agent events.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from cigar import defaults

EXIT_CODE_RE = re.compile(r"^\s*Exit code (-?\d+)")
# Fields that describe a call but don't change what it does.
NON_SEMANTIC_KEYS = frozenset({"description"})


@dataclass(frozen=True)
class Event:
    tool: str
    kind: str  # read | edit | shell | other
    args_hash: str | None = None
    path: str | None = None
    edit_old_hash: str | None = None
    edit_new_hash: str | None = None
    failed: bool = False
    exit_code: int | None = None
    is_check: bool = False
    id: int = 0
    signals: tuple[str, ...] = field(default=())


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _text_hash(value: Any) -> str | None:
    """Hash of a non-empty string, else None (empty text never matches)."""
    return short_hash(value) if isinstance(value, str) and value else None


def args_hash(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        tool_input = {k: v for k, v in tool_input.items() if k not in NON_SEMANTIC_KEYS}
    canonical = json.dumps(tool_input, sort_keys=True, separators=(",", ":"), default=str)
    return short_hash(canonical)


def kind_of(tool: str) -> str:
    if tool in defaults.READ_TOOLS:
        return "read"
    if tool in defaults.EDIT_TOOLS:
        return "edit"
    if tool in defaults.SHELL_TOOLS:
        return "shell"
    return "other"


def compile_checks(patterns: Iterable[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def _edit_hashes(tool: str, tool_input: dict[str, Any], response: Any) -> tuple[str | None, ...]:
    if tool == "Edit":
        return _text_hash(tool_input.get("old_string")), _text_hash(tool_input.get("new_string"))
    if tool == "MultiEdit":
        edits = [e for e in tool_input.get("edits") or [] if isinstance(e, dict)]
        old = "\0".join(str(e.get("old_string", "")) for e in edits)
        new = "\0".join(str(e.get("new_string", "")) for e in edits)
        return _text_hash(old), _text_hash(new)
    if tool == "Write":
        original = response.get("originalFile") if isinstance(response, dict) else None
        return _text_hash(original), _text_hash(tool_input.get("content"))
    if tool == "NotebookEdit":
        return None, _text_hash(tool_input.get("new_source"))
    return None, None


def extract(
    tool: str,
    tool_input: Any,
    tool_response: Any = None,
    error: str | None = None,
    failed: bool = False,
    checks: re.Pattern[str] | None = None,
) -> Event:
    """Build an Event from a PostToolUse / PostToolUseFailure payload."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    kind = kind_of(tool)
    if isinstance(tool_response, dict) and tool_response.get("isError") is True:
        failed = True

    path = None
    old_hash = new_hash = None
    if kind in ("read", "edit"):
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        path = raw if isinstance(raw, str) else None
    if kind == "edit":
        old_hash, new_hash = _edit_hashes(tool, tool_input, tool_response)

    exit_code = None
    is_check = False
    if kind == "shell":
        command = tool_input.get("command")
        if failed:
            match = EXIT_CODE_RE.match(error or "")
            exit_code = int(match.group(1)) if match else None
        else:
            exit_code = 0
        checks = checks or compile_checks(defaults.CHECK_PATTERNS)
        is_check = isinstance(command, str) and bool(checks.search(command))

    return Event(
        tool=tool,
        kind=kind,
        args_hash=args_hash(tool_input),
        path=path,
        edit_old_hash=old_hash,
        edit_new_hash=new_hash,
        failed=failed,
        exit_code=exit_code,
        is_check=is_check,
    )


def detect(
    current: Event,
    history: Sequence[Event],
    path_history: Sequence[Event] = (),
) -> tuple[str, ...]:
    """Signals shown by `current`.

    history: earlier main-agent events of the session, oldest first (the last
        UNDO_LOOKBACK_EVENTS are enough).
    path_history: earlier main-agent events on current.path, oldest first.
    """
    found: list[str] = []
    if current.failed:
        found.append("failure")

    window = history[-(defaults.WINDOW_EVENTS - 1) :]
    if current.kind == "read":
        # A read of the same path and range, with no edit to it since (D-018).
        for prior in reversed(path_history):
            if prior.kind == "edit":
                break
            if prior.kind == "read" and prior.args_hash == current.args_hash:
                found.append("reread")
                break
    elif any(e.tool == current.tool and e.args_hash == current.args_hash for e in window):
        found.append("repeat")

    if current.kind == "edit" and current.edit_new_hash and current.path:
        lookback = history[-defaults.UNDO_LOOKBACK_EVENTS :]
        if any(
            e.kind == "edit" and e.path == current.path and e.edit_old_hash == current.edit_new_hash
            for e in lookback
        ):
            found.append("undo")

    if current.kind == "shell" and current.is_check and current.failed and current.exit_code != 0:
        found.append("check_fail")

    return tuple(found)


def weight(signals: Iterable[str]) -> float:
    return sum(defaults.WEIGHTS.get(s, 0.0) for s in signals)
