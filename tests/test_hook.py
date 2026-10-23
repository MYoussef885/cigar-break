"""Hook handlers, run in-process through hook.main (stdin JSON in, stdout JSON out)."""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import pytest
from helpers import assistant, run_hook, write_jsonl

from cigar import config, handoff
from cigar.store import Store, project_hash


def payload(project: Path, transcript: Path | None, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": "sess-1",
        "cwd": str(project),
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "description": "List"},
        "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
    }
    if transcript:
        base["transcript_path"] = str(transcript)
    return base | extra


def db() -> Store:
    return Store.open(config.load().db_path)


def logs_text(home: Path) -> str:
    return "".join(p.read_text() for p in (home / "logs").glob("*.log"))


@pytest.fixture
def at_140k(tmp_path: Path) -> Path:
    return write_jsonl(tmp_path / "t.jsonl", [assistant(140_000, "claude-sonnet-5-5")])


def test_session_start_registers_without_output(project: Path) -> None:
    code, out = run_hook(
        "session_start",
        {"session_id": "s0", "source": "startup", "model": "claude-opus-5-5", "cwd": str(project)},
    )
    assert (code, out) == (0, "")
    with db() as s:
        row = s.get_session("s0")
    assert row["model_first"] == "claude-opus-5-5"
    assert row["project_hash"] == project_hash(str(project))


def test_healthy_turn_has_no_output(project: Path, tmp_path: Path) -> None:
    t = write_jsonl(tmp_path / "t.jsonl", [assistant(50_000)])
    assert run_hook("post_tool_use", payload(project, t)) == (0, "")
    with db() as s:
        session = s.get_session("sess-1")
    assert (session["context_tokens"], session["model_last"]) == (50_000, "claude-sonnet-5-5")


def test_nudge_output_shape(project: Path, at_140k: Path, cigar_home: Path) -> None:
    code, out = run_hook("post_tool_use", payload(project, at_140k))
    assert code == 0
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert data["hookSpecificOutput"]["additionalContext"].startswith(
        "Cigar session check: context is at 140k tokens; the knee for claude-sonnet-5-5 is ~100k."
    )
    assert data["systemMessage"].startswith("🚬 Cigar: this session shows fatigue (140k tokens")
    assert data["terminalSequence"].startswith("\x1b]9;") and data["terminalSequence"].endswith(
        "\x07"
    )
    assert "nudge session=sess-1 level=1 trigger=b tokens=140000" in logs_text(cigar_home)


def test_failure_hook_uses_its_event_name(project: Path, at_140k: Path) -> None:
    p = payload(project, at_140k, error="Exit code 1", is_interrupt=False)
    data = json.loads(run_hook("post_tool_use_failure", p)[1])
    assert data["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"
    assert "1 failed" in data["hookSpecificOutput"]["additionalContext"]


def test_interrupt_is_not_a_failure(project: Path, tmp_path: Path) -> None:
    t = write_jsonl(tmp_path / "t.jsonl", [assistant(50_000)])
    run_hook("post_tool_use_failure", payload(project, t, error="Interrupted", is_interrupt=True))
    with db() as s:
        (event,) = s.recent_events("sess-1", 5)
    assert not event.failed


def test_cooldown_cap_and_break_reset(project: Path, at_140k: Path) -> None:
    outputs = []
    for i in range(80):
        p = payload(project, at_140k, tool_input={"command": f"ls {i}"})
        outputs.append(bool(run_hook("post_tool_use", p)[1]))
    nudged = [i for i, fired in enumerate(outputs) if fired]
    assert nudged == [0, 25, 50]  # cooldown 25, at most 3

    tb = payload(project, at_140k, tool_name="mcp__plugin_cigar_cigar__take_break", tool_input={})
    assert run_hook("post_tool_use", tb)[1] == ""
    with db() as s:
        session = s.get_session("sess-1")
    assert (session["nudges"], session["breaks"], session["last_nudge_seq"]) == (0, 1, None)
    assert run_hook("post_tool_use", payload(project, at_140k))[1]  # counter was reset


def test_stop_reminds_once_after_break(project: Path, at_140k: Path) -> None:
    stop = {"session_id": "sess-1", "cwd": str(project)}
    run_hook("post_tool_use", payload(project, at_140k))
    assert run_hook("stop", stop)[1] == ""
    tb = payload(project, at_140k, tool_name="mcp__plugin_cigar_cigar__take_break", tool_input={})
    run_hook("post_tool_use", tb)
    assert json.loads(run_hook("stop", stop)[1]) == {
        "systemMessage": "🚬 Handoff ready. Type /clear to take the break "
        "(or /compact to keep a summary)."
    }
    assert run_hook("stop", stop)[1] == ""


def test_failed_take_break_is_not_a_break(project: Path, at_140k: Path) -> None:
    tb = payload(
        project,
        at_140k,
        tool_name="mcp__plugin_cigar_cigar__take_break",
        tool_input={},
        tool_response={"isError": True},
    )
    run_hook("post_tool_use", tb)
    with db() as s:
        assert s.get_session("sess-1")["breaks"] == 0


def test_subagent_events_are_excluded(project: Path, at_140k: Path) -> None:
    sub = payload(project, at_140k, agent_id="a1", agent_type="general-purpose")
    for _ in range(5):
        assert run_hook("post_tool_use_failure", sub | {"error": "Exit code 1"})[1] == ""
    with db() as s:
        assert s.recent_events("sess-1", 10) == []
        rows = s.conn.execute("SELECT count(*) FROM events WHERE is_subagent = 1").fetchone()
        assert rows[0] == 5


def test_observe_mode_records_without_output(
    project: Path, at_140k: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIGAR_MODE", "observe")
    assert run_hook("post_tool_use", payload(project, at_140k))[1] == ""
    with db() as s:
        assert len(s.recent_events("sess-1", 5)) == 1


def test_env_overrides_make_it_trigger_early(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIGAR_KNEE_TOKENS", "20000")
    monkeypatch.setenv("CIGAR_MIN_TOKENS", "5000")
    t = write_jsonl(tmp_path / "t.jsonl", [assistant(27_000)])
    data = json.loads(run_hook("post_tool_use", payload(project, t))[1])
    assert (
        "the knee for claude-sonnet-5-5 is ~20k" in data["hookSpecificOutput"]["additionalContext"]
    )


def test_lagging_transcript_reuses_last_known(project: Path, tmp_path: Path) -> None:
    t = write_jsonl(tmp_path / "t.jsonl", [assistant(60_000)])
    run_hook("post_tool_use", payload(project, t))
    t.write_text("")  # nothing readable this time
    run_hook("post_tool_use", payload(project, t, tool_input={"command": "pwd"}))
    with db() as s:
        rows = s.conn.execute("SELECT context_tokens FROM events ORDER BY id").fetchall()
    assert [r[0] for r in rows] == [60_000, 60_000]


def save_handoff(project: Path, age: float = 0.0) -> str:
    h = handoff.validate({"goal": "G1", "status": "S1", "next_steps": ["N1", "N2"]})
    md = handoff.render(h, project.name, dt.datetime.now().astimezone())
    _, rel = handoff.save(project, md, "sess-1", dt.datetime.now())
    with db() as s:
        s.add_handoff(project_hash(str(project)), "sess-1", rel, now=time.time() - age)
    return rel


@pytest.mark.parametrize("source", ["clear", "compact"])
def test_restore_after_reset(project: Path, source: str) -> None:
    rel = save_handoff(project)
    start = {"session_id": "sess-2", "source": source, "cwd": str(project)}
    data = json.loads(run_hook("session_start", start)[1])
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert ctx.startswith(handoff.INJECTION_PREAMBLE)
    assert "**Goal:** G1" in ctx and "1. N1" in ctx
    assert rel in data["systemMessage"]
    assert run_hook("session_start", start)[1] == ""  # consumed


def test_no_restore_on_startup_or_when_stale(project: Path) -> None:
    save_handoff(project, age=25 * 3600)
    for source in ("startup", "clear"):
        start = {"session_id": "s", "source": source, "cwd": str(project)}
        assert run_hook("session_start", start)[1] == ""


def test_project_dir_env_wins_over_cwd(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_handoff(project)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    start = {"session_id": "s", "source": "clear", "cwd": str(tmp_path / "elsewhere")}
    assert run_hook("session_start", start)[1]


def test_compaction_model_switch_and_end(project: Path, at_140k: Path) -> None:
    run_hook("post_tool_use", payload(project, at_140k))
    compact = {
        "session_id": "sess-1",
        "cwd": str(project),
        "trigger": "auto",
        "transcript_path": str(at_140k),
    }
    assert run_hook("pre_compact", compact)[1] == ""
    switch = {"session_id": "sess-1", "cwd": str(project), "to_model": "claude-haiku-4-5"}
    assert run_hook("post_model_switch", switch | {"context_tokens": 38_637})[1] == ""
    assert run_hook("session_end", {"session_id": "sess-1", "reason": "clear"})[1] == ""
    with db() as s:
        (c,) = s.conn.execute("SELECT trigger, context_tokens, model FROM compactions").fetchall()
        session = s.get_session("sess-1")
    assert tuple(c) == ("auto", 140_000, "claude-sonnet-5-5")
    assert (session["model_last"], session["context_tokens"]) == ("claude-haiku-4-5", 38_637)
    assert session["ended_at"]
