"""MCP conformance: the official `mcp` SDK client drives bin/cigar-mcp over stdio."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers import BIN, hook_python3

from cigar import mcp_server

PYTHON3 = hook_python3()
CC = "2025-11-25"  # what Claude Code 2.1.288 sends in initialize (D-014)

HANDOFF = {
    "goal": "Finish the MCP server",
    "status": "take_break works; resume untested",
    "done": ["initialize", "tools/list"],
    "decisions": ["Hand-written JSON-RPC (D-005)"],
    "files": [{"path": "src/cigar/mcp_server.py", "note": "the server"}],
    "next_steps": ["Test resume", "Test status"],
    "open_questions": [],
    "gotchas": ["Claude Code tries server/discover first"],
}


def server_env(home: Path, project: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CIGAR_", "CLAUDE_"))}
    return env | {"CIGAR_HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)}


def test_official_sdk_client(cigar_home: Path, project: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=PYTHON3,
        args=["-I", "-S", str(BIN / "cigar-mcp")],
        env=server_env(cigar_home, project),
    )

    async def session_run() -> dict[str, Any]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            init = await session.initialize()
            tools = await session.list_tools()
            empty = await session.call_tool("resume", {})
            saved = await session.call_tool("take_break", HANDOFF)
            bad = await session.call_tool("take_break", {"goal": "only a goal"})
            resumed = await session.call_tool("resume", {})
            status = await session.call_tool("status", {})
            await session.send_ping()
            return {
                "init": init,
                "tools": tools,
                "empty": empty,
                "saved": saved,
                "bad": bad,
                "resumed": resumed,
                "status": status,
            }

    r = asyncio.run(session_run())
    assert r["init"].server_info.name == "cigar"
    assert r["init"].protocol_version in mcp_server.PROTOCOL_VERSIONS
    assert {t.name for t in r["tools"].tools} == {"take_break", "resume", "status"}
    assert "No Cigar handoff" in r["empty"].content[0].text

    saved = r["saved"].content[0].text
    assert not r["saved"].is_error
    assert saved.startswith("Handoff saved to .cigar/handoffs/")
    assert "/clear" in saved and "/compact" in saved
    files = list((project / ".cigar" / "handoffs").glob("*.md"))
    assert len(files) == 1
    assert len(files[0].read_text()) < 8000
    assert (project / ".cigar" / ".gitignore").read_text() == "*\n"

    assert r["bad"].is_error and "Handoff not saved" in r["bad"].content[0].text
    assert "**Goal:** Finish the MCP server" in r["resumed"].content[0].text
    assert "Pending handoff: .cigar/handoffs/" in r["status"].content[0].text


def test_tool_descriptions_are_short() -> None:
    for tool in mcp_server.TOOLS:
        assert len(tool["description"]) <= 220, tool["name"]


def raw_exchange(messages: list[Any], home: Path, project: Path) -> list[dict[str, Any]]:
    lines = b"".join(
        (m if isinstance(m, bytes) else json.dumps(m).encode()) + b"\n" for m in messages
    )
    result = subprocess.run(
        [PYTHON3, "-I", "-S", str(BIN / "cigar-mcp")],
        input=lines,
        capture_output=True,
        env=server_env(home, project),
        timeout=30,
    )
    assert result.returncode == 0
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_protocol_edges(cigar_home: Path, project: Path) -> None:
    replies = raw_exchange(
        [
            # Claude Code 2.1.288 tries this first, then falls back to initialize (D-014).
            {"jsonrpc": "2.0", "id": "d1", "method": "server/discover", "params": {}},
            {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": CC}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1"}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            b"{not json",
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}},
            {"id": 4, "method": "ping"},
        ],
        cigar_home,
        project,
    )  # fmt: skip
    by_id = {r.get("id"): r for r in replies}
    assert by_id["d1"]["error"]["code"] == -32601
    assert by_id[0]["result"]["protocolVersion"] == CC
    assert by_id[1]["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSIONS[0]
    assert by_id[2]["result"] == {}
    assert by_id[3]["error"]["code"] == -32602
    assert len(replies) == 7  # the notification gets no reply
    codes = sorted(r["error"]["code"] for r in replies if r.get("id") is None and "error" in r)
    assert codes == [-32700, -32600]


@pytest.mark.parametrize("project_arg", [True, False])
def test_project_resolution(
    cigar_home: Path, project: Path, tmp_path: Path, project_arg: bool
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    args = HANDOFF | ({"project": str(other)} if project_arg else {})
    replies = raw_exchange(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "take_break",
                                                                       "arguments": args}}],
        cigar_home,
        project,
    )  # fmt: skip
    assert not replies[0]["result"]["isError"]
    target = other if project_arg else project
    assert list((target / ".cigar" / "handoffs").glob("*.md"))
