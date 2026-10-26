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
    return "".join(p.read_text(encoding="utf-8") for p in (home / "logs").glob("*.log"))


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

    save_handoff(project)
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
    save_handoff(project)
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


def test_auto_mode_marks_ready_after_break(
    project: Path, at_140k: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cigar import auto

    monkeypatch.setenv("CIGAR_MODE", "auto")
    data = json.loads(run_hook("post_tool_use", payload(project, at_140k))[1])
    assert "Cigar is in auto mode" in data["hookSpecificOutput"]["additionalContext"]
    assert "in auto mode the context resets" in data["systemMessage"]
    marker = auto.marker_path(cigar_home, "sess-1")
    assert not marker.exists()  # a nudge alone never resets
    rel = save_handoff(project)
    tb = payload(project, at_140k, tool_name="mcp__plugin_cigar_cigar__take_break", tool_input={})
    run_hook("post_tool_use", tb)
    assert json.loads(marker.read_text()) | {"ts": 0} == {
        "state": "ready",
        "session": "sess-1",
        "handoff": rel,
        "ts": 0,
    }
    stop = json.loads(run_hook("stop", {"session_id": "sess-1"})[1])
    assert "auto mode clears the context" in stop["systemMessage"]


def test_suggest_mode_never_writes_markers(project: Path, at_140k: Path, cigar_home: Path) -> None:
    save_handoff(project)
    tb = payload(project, at_140k, tool_name="mcp__plugin_cigar_cigar__take_break", tool_input={})
    run_hook("post_tool_use", tb)
    assert not (cigar_home / "auto").exists()


def test_auto_markers_are_pruned(cigar_home: Path) -> None:
    import os

    from cigar import auto

    ready = auto.mark_ready(cigar_home, "a", "h.md")
    fired = auto.mark_ready(cigar_home, "b", "h.md")
    fired.write_text(json.dumps({"state": "fired"}))
    old = auto.mark_ready(cigar_home, "c", "h.md")
    os.utime(old, (time.time() - 2 * 86400,) * 2)
    broken = cigar_home / "auto" / "d.json"
    broken.write_text("{nope")
    auto.prune(cigar_home)
    assert sorted(p.name for p in (cigar_home / "auto").iterdir()) == [ready.name]
    assert auto.marker_path(cigar_home, "../../etc/x").parent == cigar_home / "auto"


TAKE_BREAK = "mcp__plugin_cigar_cigar__take_break"


@pytest.mark.parametrize("mode", ["suggest", "auto"])
def test_take_break_without_a_saved_handoff_is_not_a_break(
    mode: str, project: Path, at_140k: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool reporting success is not enough: no saved handoff, no break (D-026)."""
    monkeypatch.setenv("CIGAR_MODE", mode)
    run_hook("post_tool_use", payload(project, at_140k))
    run_hook("post_tool_use", payload(project, at_140k, tool_name=TAKE_BREAK, tool_input={}))
    with db() as s:
        assert s.get_session("sess-1")["breaks"] == 0
    assert not (cigar_home / "auto").exists()
    assert run_hook("stop", {"session_id": "sess-1"})[1] == ""
    assert "break ignored session=sess-1: no handoff saved this session" in logs_text(cigar_home)


def test_handoff_from_an_earlier_session_does_not_count(
    project: Path, at_140k: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIGAR_MODE", "auto")
    save_handoff(project, age=3600)  # pending, but older than this session
    run_hook("post_tool_use", payload(project, at_140k, tool_name=TAKE_BREAK, tool_input={}))
    assert not (cigar_home / "auto").exists()


def test_auto_clear_line_names_the_handoff(
    project: Path, at_140k: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cigar import auto

    monkeypatch.setenv("CIGAR_MODE", "auto")
    run_hook("session_start", {"session_id": "sess-1", "source": "startup", "cwd": str(project)})
    rel = save_handoff(project)
    run_hook("post_tool_use", payload(project, at_140k, tool_name=TAKE_BREAK, tool_input={}))
    marker = auto.marker_path(cigar_home, "sess-1")
    marker.write_text(json.dumps(json.loads(marker.read_text()) | {"state": "fired"}))  # the mod
    start = {"session_id": "sess-2", "source": "clear", "cwd": str(project)}
    data = json.loads(run_hook("session_start", start)[1])
    assert data["systemMessage"] == (
        f"🚬 Cigar auto mode cleared the context and restored the handoff from {rel}."
    )
    assert not marker.exists()


def test_auto_clear_without_restore_still_says_so(
    project: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cigar import auto

    marker = auto.mark_ready(cigar_home, "sess-1", ".cigar/handoffs/x.md")
    marker.write_text(json.dumps(json.loads(marker.read_text()) | {"state": "fired"}))
    start = {"session_id": "sess-2", "source": "clear", "cwd": str(project)}
    message = json.loads(run_hook("session_start", start)[1])["systemMessage"]
    assert message.startswith("🚬 Cigar auto mode cleared the context, but the handoff ")
    assert ".cigar/handoffs/x.md" in message


def test_window_turns_1m_past_200k_and_stays(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = tmp_path / "t.jsonl"
    for i, tokens in enumerate((150_000, 230_000, 60_000)):
        write_jsonl(t, [assistant(tokens, "claude-sonnet-5-5")])
        run_hook("post_tool_use", payload(project, t, tool_input={"command": f"ls {i}"}))
        with db() as s:
            window = s.get_session("sess-1")["context_window"]
        assert window == ("200k" if i == 0 else "1m")
    from cigar import status

    with db() as s:
        info = status.collect(s, config.load(), "sess-1")
    assert (info["session"]["context_window"], info["session"]["knee"]) == ("1m", 140_000)


def test_configured_window_is_stored(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIGAR_CONTEXT_WINDOW", "1M")
    t = write_jsonl(tmp_path / "t.jsonl", [assistant(150_000, "claude-sonnet-5-5")])
    assert run_hook("post_tool_use", payload(project, t))[1] == ""  # 150k < 1M knee of 140k x 1.3
    with db() as s:
        assert s.get_session("sess-1")["context_window"] == "1m"


def test_hook_output_is_ascii(project: Path, at_140k: Path) -> None:
    """A Windows console encoding can't print the emoji; escaped JSON always can (D-030)."""
    nudge = run_hook("post_tool_use", payload(project, at_140k))[1]
    save_handoff(project)
    start = {"session_id": "sess-2", "source": "clear", "cwd": str(project)}
    restore = run_hook("session_start", start)[1]
    for out in (nudge, restore):
        assert out and out.isascii()
        assert json.loads(out)["systemMessage"].startswith("🚬 Cigar")


def test_failing_knee_refit_never_costs_the_restore(
    project: Path, cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cigar import track

    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("refit failed")

    monkeypatch.setattr(track, "refresh_knees", broken)
    save_handoff(project)
    start = {"session_id": "sess-2", "source": "clear", "cwd": str(project)}
    data = json.loads(run_hook("session_start", start)[1])
    assert data["systemMessage"].startswith("🚬 Cigar: restored the handoff")
    assert "ERROR knee refresh: RuntimeError: refit failed" in logs_text(cigar_home)
