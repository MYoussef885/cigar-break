"""Any agent (FR-M1, FR-M2): record_event over MCP and cigar.track in-process."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from helpers import BIN, hook_python3
from test_mcp import server_env

from cigar import config
from cigar.store import Store
from cigar.track import Tracker


def test_record_event_over_the_official_sdk(cigar_home: Path, project: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=hook_python3(),
        args=["-I", "-S", str(BIN / "cigar-mcp")],
        env=server_env(cigar_home, project),
    )

    def event(i: int, **extra: Any) -> dict[str, Any]:
        base = {
            "session_id": "agent-run-1",
            "tool": "read_file",
            "ok": True,
            "context_tokens": 140_000 + i * 500,
            "model": "gpt-5",
            "kind": "read",
            "path": f"src/f{i}.py",
        }
        return base | extra

    async def go() -> dict[str, Any]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            first = await session.call_tool("record_event", event(0))
            quiet = [await session.call_tool("record_event", event(i)) for i in range(1, 5)]
            failed = await session.call_tool(
                "record_event", event(5, tool="run_tests", kind="shell", ok=False, exit_code=1,
                                      args={"command": "pytest -q"}, path=None)
            )  # fmt: skip
            bad = await session.call_tool("record_event", {"session_id": "x", "tool": "t"})
            wrong_kind = await session.call_tool("record_event", event(6, kind="teleport"))
            saved = await session.call_tool(
                "take_break", {"goal": "G", "status": "S", "next_steps": ["N"]}
            )
            return {"first": first, "quiet": quiet, "failed": failed, "bad": bad,
                    "wrong_kind": wrong_kind, "saved": saved}  # fmt: skip

    r = asyncio.run(go())
    first = json.loads(r["first"].content[0].text)
    assert first["break_suggested"] is True  # 140k vs gpt-5's 100k default knee: rule (b)
    assert first["message"].startswith("Cigar session check: context is at 140k tokens")
    assert (first["knee"], first["knee_source"]) == (100_000, "default")
    assert all(not json.loads(q.content[0].text)["break_suggested"] for q in r["quiet"])
    failed = json.loads(r["failed"].content[0].text)
    assert failed["signals"] == {"failure": 1, "check_fail": 1}
    assert r["bad"].is_error and "is required" in r["bad"].content[0].text
    assert r["wrong_kind"].is_error and "kind must be one of" in r["wrong_kind"].content[0].text
    assert not r["saved"].is_error

    with Store.open(config.load().db_path) as store:
        session = store.get_session("agent-run-1")
        stored = store.conn.execute("SELECT * FROM events").fetchall()
    assert session["harness"] == "mcp" and session["main_events"] == 6  # rejected calls: none
    assert all("pytest" not in json.dumps(dict(row)) for row in stored)  # args are hashed


def test_tracker_detects_rereads_for_a_python_loop(cigar_home: Path, project: Path) -> None:
    tracker = Tracker(session_id="py-1", model="my-model", project=project)
    first = tracker.record("open", True, 50_000, kind="read", path="a.py", args={"n": 1})
    again = tracker.record("open", True, 51_000, kind="read", path="a.py", args={"n": 1})
    assert first.signals == {} and again.signals == {"reread": 1}
    assert not again.break_suggested
    with Store.open(config.load().db_path) as store:
        assert store.get_session("py-1")["harness"] == "python"


def test_tracker_undo_and_default_session_id(cigar_home: Path, project: Path) -> None:
    tracker = Tracker(model="m", project=project)
    assert tracker.session_id.startswith("py-")
    tracker.record("edit", True, 60_000, kind="edit", path="b.py",
                   args={"old_string": "x = 1", "new_string": "x = 2"})  # fmt: skip
    undo = tracker.record("edit", True, 61_000, kind="edit", path="b.py",
                          args={"old_string": "x = 2", "new_string": "x = 1"})  # fmt: skip
    assert undo.signals == {"undo": 1}


def test_tracker_rejects_unknown_kinds(cigar_home: Path) -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        Tracker(model="m").record("x", kind="teleport")
