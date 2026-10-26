"""Drive a Cigar MCP server with the official MCP Python SDK client (FR-M1, FR-M3).

    uv run python scripts/check_mcp_client.py -- cigar-mcp
    uv run python scripts/check_mcp_client.py -- /tmp/venv/bin/cigar-mcp

The server runs with a temporary CIGAR_HOME and a temporary project folder as
its working directory, outside any plugin: no CLAUDE_* variables are passed.
It prints a short transcript and exits 1 if any step fails.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


async def drive(command: list[str], home: Path, project: Path) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {k: v for k, v in os.environ.items() if not k.startswith(("CIGAR_", "CLAUDE_"))}
    env["CIGAR_HOME"] = str(home)
    params = StdioServerParameters(command=command[0], args=command[1:], env=env, cwd=project)
    lines = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        info = init.server_info
        lines.append(f"initialize: {info.name} {info.version}, protocol {init.protocol_version}")
        tools = sorted(t.name for t in (await session.list_tools()).tools)
        lines.append(f"tools/list: {', '.join(tools)}")
        for i, tokens in enumerate((60_000, 61_000, 150_000)):
            event = {
                "session_id": "sdk-check",
                "tool": "read_file",
                "ok": True,
                "context_tokens": tokens,
                "model": "gpt-5",
                "kind": "read",
                "path": "src/app.py",
            }
            result = await session.call_tool("record_event", event)
            data = json.loads(result.content[0].text)
            lines.append(
                f"record_event #{i + 1} at {tokens // 1000}k: "
                f"break_suggested={data['break_suggested']} signals={data['signals']}"
            )
        saved = await session.call_tool(
            "take_break",
            {"goal": "Check the MCP server", "status": "running", "next_steps": ["resume"]},
        )
        lines.append(f"take_break: {saved.content[0].text.split('. ')[0]}")
        resumed = await session.call_tool("resume", {})
        lines.append(f"resume: {resumed.content[0].text.splitlines()[0]}")
        status = await session.call_tool("status", {})
        lines.append(f"status: {status.content[0].text.splitlines()[0]}")
        await session.send_ping()
        lines.append("ping: ok")
        if any(r.is_error for r in (saved, resumed, status)):
            raise RuntimeError("a tool call returned an error")
    return lines


def main(argv: list[str]) -> int:
    command = argv[argv.index("--") + 1 :] if "--" in argv else argv
    if not command:
        print(__doc__)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        home, project = Path(tmp) / "cigar-home", Path(tmp) / "project"
        project.mkdir()
        print(f"client: official MCP Python SDK {version('mcp')}; server: {' '.join(command)}")
        try:
            for line in asyncio.run(drive(command, home, project)):
                print(f"  {line}")
        except Exception as exc:
            print(f"FAILED: {type(exc).__name__}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
