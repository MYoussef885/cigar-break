"""D-026: auto mode never clears without a saved handoff.

The real hooks and the real MCP take_break write the state; the real
mods/auto.ts (run under node with a fake `$`, see mod_harness.mjs) decides
whether to run /clear at each turn end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers import assistant, run_hook, write_jsonl

from cigar import auto, config, mcp_server

HARNESS = Path(__file__).with_name("mod_harness.mjs")
NODE = shutil.which("node")


def _node_strips_types() -> bool:
    if not NODE:
        return False
    out = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout
    major, minor = (int(x) for x in out.strip().lstrip("v").split(".")[:2])
    return (major, minor) >= (22, 18)


pytestmark = pytest.mark.skipif(
    not _node_strips_types(), reason="needs node >= 22.18 to run mods/auto.ts"
)


def turn_end(home: Path, session: str = "sess-1", reason: str = "answer", agent: str = "") -> list:
    assert NODE
    result = subprocess.run(
        [NODE, str(HARNESS), str(home), session, reason, agent],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["commands"]


def tool_call(project: Path, transcript: Path, i: int, **extra: Any) -> dict[str, Any]:
    data = {
        "session_id": "sess-1",
        "cwd": str(project),
        "transcript_path": str(transcript),
        "tool_name": "Bash",
        "tool_input": {"command": f"ls {i}"},
        "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
    }
    return data | extra


@pytest.fixture
def auto_session(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    monkeypatch.setenv("CIGAR_MODE", "auto")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    run_hook("session_start", {"session_id": "sess-1", "source": "startup", "cwd": str(project)})
    return project, write_jsonl(tmp_path / "t.jsonl", [assistant(140_000)])


def test_nudges_without_take_break_never_clear(
    auto_session: tuple[Path, Path], cigar_home: Path
) -> None:
    project, transcript = auto_session
    nudges = 0
    for i in range(80):  # every nudge the session allows, and then some
        out = run_hook("post_tool_use", tool_call(project, transcript, i))[1]
        if out:
            nudges += 1
            assert "auto mode" in json.loads(out)["systemMessage"]
        if i % 5 == 4:
            run_hook("stop", {"session_id": "sess-1"})
            assert turn_end(cigar_home) == []
    assert nudges == 3
    assert not (cigar_home / "auto").exists()


def test_take_break_reported_but_not_saved_never_clears(
    auto_session: tuple[Path, Path], cigar_home: Path
) -> None:
    project, transcript = auto_session
    run_hook("post_tool_use", tool_call(project, transcript, 0))
    take_break = "mcp__plugin_cigar_cigar__take_break"
    run_hook("post_tool_use", tool_call(project, transcript, 1, tool_name=take_break))
    assert turn_end(cigar_home) == []


def test_marker_without_a_handoff_never_clears(cigar_home: Path) -> None:
    path = auto.marker_path(cigar_home, "sess-1")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"state": "ready", "session": "sess-1"}))  # Session 1 format
    assert turn_end(cigar_home) == []


def test_saved_handoff_clears_once_at_a_main_agent_answer(
    auto_session: tuple[Path, Path], cigar_home: Path
) -> None:
    project, transcript = auto_session
    run_hook("post_tool_use", tool_call(project, transcript, 0))
    reply = mcp_server.tool_take_break(
        {"goal": "G", "status": "S", "next_steps": ["N"]}, config.load()
    )
    assert "auto mode" in reply
    take_break = "mcp__plugin_cigar_cigar__take_break"
    run_hook("post_tool_use", tool_call(project, transcript, 1, tool_name=take_break))

    assert turn_end(cigar_home, agent="agent-1") == []  # a subagent's turn
    assert turn_end(cigar_home, reason="interrupted") == []
    assert turn_end(cigar_home, session="other") == []
    assert turn_end(cigar_home) == ["clear"]
    assert turn_end(cigar_home) == []  # fired once

    start = {"session_id": "sess-2", "source": "clear", "cwd": str(project)}
    message = json.loads(run_hook("session_start", start)[1])["systemMessage"]
    assert message.startswith("🚬 Cigar auto mode cleared the context and restored the handoff")
    assert ".cigar/handoffs/" in message
