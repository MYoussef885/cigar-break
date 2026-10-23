"""Test helpers: synthetic transcript entries (layout observed in D-014) and a replayer."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cigar import hook

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "bin"
FIXTURES = Path(__file__).with_name("fixtures")


def hook_python3() -> str:
    """The `python3` a Claude Code hook would get: PATH without this test venv."""
    venv = Path(sys.prefix).resolve()
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    outside = [d for d in dirs if not Path(d).resolve().is_relative_to(venv)]
    return shutil.which("python3", path=os.pathsep.join(outside)) or sys.executable


def usage(tokens: int) -> dict[str, int]:
    return {
        "input_tokens": 2,
        "cache_creation_input_tokens": 500,
        "cache_read_input_tokens": max(0, tokens - 502),
        "output_tokens": 120,
    }


def assistant(
    tokens: int,
    model: str = "claude-sonnet-5-5",
    tool_uses: Iterable[tuple[str, str, dict[str, Any]]] = (),
    text: str | None = None,
    sidechain: bool = False,
    session: str = "sess-1",
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for tool_id, name, tool_input in tool_uses:
        content.append({"type": "tool_use", "id": tool_id, "name": name, "input": tool_input})
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "sessionId": session,
        "message": {
            "role": "assistant",
            "model": model,
            "content": content,
            "usage": usage(tokens),
        },
    }


def tool_result(
    tool_id: str, content: str = "ok", is_error: bool = False, result: Any = None
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "user",
        "isSidechain": False,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
    }
    if result is not None:
        entry["toolUseResult"] = result
    return entry


def noise(i: int) -> list[dict[str, Any]]:
    """Non-message entries Claude Code interleaves (shape only, synthetic)."""
    return [
        {"type": "attachment", "attachment": {"type": "todo", "n": i}},
        {"type": "file-history-snapshot", "messageId": f"m{i}", "snapshot": {}},
    ]


def write_jsonl(path: Path, entries: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


def run_hook(event: str, payload: dict[str, Any] | bytes) -> tuple[int, str]:
    """Run the hook in-process with stdin/stdout swapped. Returns (code, stdout)."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin = io.TextIOWrapper(io.BytesIO(raw))
    sys.stdout = out = io.StringIO()
    try:
        code = hook.main([event])
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return code, out.getvalue()


@dataclass
class Step:
    index: int  # tool call number, from 1
    tool: str
    tokens: int
    output: dict[str, Any] | None


def replay(source: Path, workdir: Path, session: str = "replay-1") -> Iterator[Step]:
    """Feed a transcript through the hooks the way Claude Code would.

    Lines are appended to a live transcript one by one; every tool_result fires
    PostToolUse or PostToolUseFailure for its tool_use.
    """
    live = workdir / f"{session}.jsonl"
    live.write_text("")
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    tokens = 0
    count = 0
    run_hook("session_start", {"session_id": session, "source": "startup", "cwd": str(workdir)})
    with source.open(encoding="utf-8") as src, live.open("a", encoding="utf-8") as dst:
        for line in src:
            dst.write(line)
            dst.flush()
            entry = json.loads(line)
            message = entry.get("message") or {}
            content = message.get("content")
            if not isinstance(content, list):
                continue
            if entry.get("type") == "assistant" and not entry.get("isSidechain"):
                tokens = sum(
                    message.get("usage", {}).get(k, 0)
                    for k in (
                        "input_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    )
                )
                for block in content:
                    if block.get("type") == "tool_use":
                        pending[block["id"]] = (block["name"], block.get("input") or {})
            if entry.get("type") != "user":
                continue
            for block in content:
                if block.get("type") != "tool_result" or block.get("tool_use_id") not in pending:
                    continue
                name, tool_input = pending.pop(block["tool_use_id"])
                failed = bool(block.get("is_error"))
                text = block.get("content")
                payload: dict[str, Any] = {
                    "session_id": session,
                    "transcript_path": str(live),
                    "cwd": str(workdir),
                    "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
                    "tool_name": name,
                    "tool_input": tool_input,
                    "tool_use_id": block["tool_use_id"],
                }
                if failed:
                    payload["error"] = text if isinstance(text, str) else "error"
                    payload["is_interrupt"] = False
                else:
                    payload["tool_response"] = entry.get("toolUseResult") or {}
                event = "post_tool_use_failure" if failed else "post_tool_use"
                _, out = run_hook(event, payload)
                count += 1
                yield Step(count, name, tokens, json.loads(out) if out.strip() else None)
