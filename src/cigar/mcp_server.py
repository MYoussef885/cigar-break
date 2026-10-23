"""`cigar-mcp`: a hand-written stdio JSON-RPC 2.0 MCP server (D-005, architecture §11).

Tools: take_break, resume, status. Messages are newline-delimited JSON.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from cigar import __version__, config, handoff, logs, status
from cigar.store import Store, project_hash

# Newest first. Claude Code 2.1.288 sends 2025-11-25 in `initialize` (D-014).
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

_STR_LIST = {"type": "array", "items": {"type": "string"}}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "take_break",
        "description": (
            "Save a structured handoff of the current work so it can resume in a fresh context "
            "after /clear. Use when Cigar reports fatigue, when the developer asks, or before "
            "a long new phase of work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The overall goal."},
                "status": {"type": "string", "description": "Where the work stands now."},
                "done": _STR_LIST,
                "decisions": _STR_LIST,
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "note": {"type": "string"}},
                        "required": ["path"],
                    },
                },
                "next_steps": {
                    **_STR_LIST,
                    "description": "The first one is the immediate action.",
                },
                "open_questions": _STR_LIST,
                "gotchas": _STR_LIST,
                "project": {"type": "string", "description": "Project directory (optional)."},
            },
            "required": ["goal", "status", "next_steps"],
        },
    },
    {
        "name": "resume",
        "description": "Return the latest Cigar handoff for this project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "status",
        "description": "Cigar's fatigue score, context size, knee, recent signals and mode.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "project": {"type": "string"}},
        },
    },
]


class ToolError(Exception):
    pass


def _project_dir(arguments: dict[str, Any]) -> Path:
    raw = arguments.get("project") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(str(raw)).expanduser().resolve()


def tool_take_break(arguments: dict[str, Any], cfg: config.Config) -> str:
    try:
        parsed = handoff.validate(arguments)
    except handoff.HandoffError as exc:
        raise ToolError(f"Handoff not saved: {exc}.") from exc
    project_dir = _project_dir(arguments)
    project = project_hash(str(project_dir))
    when = dt.datetime.now().astimezone()
    with Store.open(cfg.db_path) as store:
        session = store.latest_session(project)
        session_id = session["id"] if session else None
        markdown = handoff.render(parsed, project_dir.name, when)
        _, rel_path = handoff.save(project_dir, markdown, session_id, when)
        store.add_handoff(project, session_id, rel_path)
    rendered = len(handoff.for_injection(markdown, rel_path))
    logs.write(f"take_break saved={rel_path} chars={len(markdown)} injected_chars={rendered}")
    return (
        f"Handoff saved to {rel_path}. When the developer types /clear, it will be restored "
        "automatically into the fresh session. What to tell the developer: type /clear for a "
        "full fresh start (recommended), or /compact to keep a summary."
    )


def tool_resume(arguments: dict[str, Any], cfg: config.Config) -> str:
    project_dir = _project_dir(arguments)
    with Store.open(cfg.db_path) as store:
        latest = store.latest_handoff(project_hash(str(project_dir)))
    if not latest:
        return "No Cigar handoff exists for this project yet."
    markdown = handoff.load(project_dir, latest["path"])
    if markdown is None:
        raise ToolError(f"The latest handoff file is missing: {latest['path']}.")
    return f"Latest handoff ({latest['path']}):\n\n{markdown}"


def tool_status(arguments: dict[str, Any], cfg: config.Config) -> str:
    project = project_hash(str(_project_dir(arguments)))
    session_id = arguments.get("session_id")
    with Store.open(cfg.db_path) as store:
        info = status.collect(
            store, cfg, session_id if isinstance(session_id, str) else None, project
        )
    return status.render(info)


HANDLERS: dict[str, Callable[[dict[str, Any], config.Config], str]] = {
    "take_break": tool_take_break,
    "resume": tool_resume,
    "status": tool_status,
}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(message: Any) -> dict[str, Any] | None:
    """One JSON-RPC message in, one response out (None for notifications)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Invalid request")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    if not isinstance(method, str):
        return None if is_notification else _error(msg_id, INVALID_REQUEST, "Invalid request")
    if is_notification:
        return None
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return _result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cigar", "version": __version__},
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        if not isinstance(params, dict) or params.get("name") not in HANDLERS:
            return _error(msg_id, INVALID_PARAMS, "Unknown tool")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(msg_id, INVALID_PARAMS, "Tool arguments must be an object")
        try:
            text = HANDLERS[params["name"]](arguments, config.load())
            is_error = False
        except ToolError as exc:
            text, is_error = str(exc), True
        except Exception as exc:
            logs.error(f"mcp tool {params['name']}", exc)
            text, is_error = (
                f"Cigar hit an internal error ({type(exc).__name__}); see ~/.cigar/logs.",
                True,
            )
        return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
    return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def serve(stdin: BinaryIO, stdout: BinaryIO) -> None:
    for line in iter(stdin.readline, b""):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response: dict[str, Any] | None = _error(None, PARSE_ERROR, "Parse error")
        else:
            try:
                response = handle(message)
            except Exception as exc:
                logs.error("mcp handle", exc)
                msg_id = message.get("id") if isinstance(message, dict) else None
                response = _error(msg_id, -32603, "Internal error")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()


def main(argv: list[str] | None = None) -> int:
    del argv
    logs.write(f"mcp start version={__version__} pid={os.getpid()}")
    with contextlib.suppress(BrokenPipeError, KeyboardInterrupt):
        serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
