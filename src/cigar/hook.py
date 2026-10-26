"""`cigar-hook <event>`: Claude Code hook entry point (architecture §4).

Fail-open (NFR-1): any exception exits 0 with no stdout and is logged. Output is
written only once a handler has fully succeeded.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cigar import auto, config, defaults, logs, score, signals, track, transcript
from cigar.store import Store, project_hash

Payload = dict[str, Any]
Output = dict[str, Any] | None

NOTIFY_SEQUENCE = "\x1b]9;Cigar: this session shows fatigue\x07"
STOP_REMINDER = "🚬 Handoff ready. Type /clear to take the break (or /compact to keep a summary)."
STOP_REMINDER_AUTO = (
    "🚬 Handoff ready. Cigar auto mode clears the context now; if it doesn't, type /clear."
)
RESTORED = "🚬 Cigar: restored the handoff from {path}."
AUTO_RESTORED = "🚬 Cigar auto mode cleared the context and restored the handoff from {path}."
AUTO_NOT_RESTORED = (
    "🚬 Cigar auto mode cleared the context, but the handoff {path} could not be restored. "
    "The resume tool (cigar MCP) returns the latest handoff."
)


def _project_dir(payload: Payload) -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(raw)


def _session_id(payload: Payload) -> str:
    sid = payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError("hook input has no session_id")
    return sid


# --- handlers -------------------------------------------------------------------
def session_start(payload: Payload, cfg: config.Config) -> Output:
    output = _session_start(payload, cfg)
    try:  # learning must never cost the restore above
        with Store.open(cfg.db_path) as store:
            if track.refresh_knees(store) is not None:
                logs.write("knees refit", cfg.home)
    except Exception as exc:
        logs.error("knee refresh", exc, cfg.home)
    return output


def _session_start(payload: Payload, cfg: config.Config) -> Output:
    from cigar import handoff

    sid = _session_id(payload)
    source = payload.get("source")
    model = payload.get("model") if isinstance(payload.get("model"), str) else None
    project_dir = _project_dir(payload)
    project = project_hash(str(project_dir))
    with Store.open(cfg.db_path) as store:
        store.touch_session(sid, project, model=model, source=source)
        fired = auto.take_fired(cfg.home) if source == "clear" else None
        auto.prune(cfg.home)
        if source not in ("clear", "compact"):
            logs.prune(cfg.home)
            return None
        pending = store.pending_handoff(project, defaults.HANDOFF_MAX_AGE_SECONDS)
        markdown = handoff.load(project_dir, pending["path"]) if pending else None
        if not pending or markdown is None:
            if pending:
                logs.write(f"restore skipped: handoff file missing ({pending['path']})", cfg.home)
            if fired:
                return {"systemMessage": AUTO_NOT_RESTORED.format(path=fired)}
            return None
        text = handoff.for_injection(markdown, pending["path"])
        store.consume_handoff(pending["id"])
    logs.write(
        f"restore session={sid[:8]} source={source} chars={len(text)} auto={bool(fired)}", cfg.home
    )
    line = AUTO_RESTORED if fired == pending["path"] else RESTORED
    return {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
        "systemMessage": line.format(path=pending["path"]),
    }


def _record_break(
    store: Store, cfg: config.Config, sid: str, project: str, started: float, tokens: int | None
) -> None:
    """Count a break only if a handoff for this session is really saved (D-026).

    The tool reporting success is not enough: in auto mode the marker is what
    lets the mod run /clear, so it is written only with a saved handoff's path.
    """
    saved = store.session_handoff(project, started)
    if saved is None:
        logs.write(f"break ignored session={sid[:8]}: no handoff saved this session", cfg.home)
        return
    store.record_break(sid)
    if cfg.mode == "auto":
        auto.mark_ready(cfg.home, sid, saved["path"])
    logs.write(f"break session={sid[:8]} tokens={tokens} mode={cfg.mode}", cfg.home)


def post_tool_use(payload: Payload, cfg: config.Config, failed: bool = False) -> Output:
    sid = _session_id(payload)
    tool = str(payload.get("tool_name") or "unknown")
    is_subagent = bool(payload.get("agent_id"))
    if failed and payload.get("is_interrupt") is True:
        failed = False  # the developer stopped it; not an agent failure (D-018)
    event = signals.extract(
        tool,
        payload.get("tool_input"),
        payload.get("tool_response"),
        error=payload.get("error") if isinstance(payload.get("error"), str) else None,
        failed=failed,
        checks=signals.compile_checks(cfg.check_patterns),
    )
    project = project_hash(str(_project_dir(payload)))

    with Store.open(cfg.db_path) as store:
        session = store.touch_session(sid, project)
        if is_subagent:
            store.insert_event(sid, event, True, None, None)
            return None

        reading = transcript.read_tail(payload.get("transcript_path"))
        if reading is None:
            logs.write(
                f"transcript: no usage in tail session={sid[:8]}; using last known", cfg.home
            )
        outcome = track.record(
            store,
            cfg,
            session,
            event,
            reading.context_tokens if reading else None,
            reading.model if reading else None,
        )
        if track.is_cigar_tool(tool):
            if tool.endswith("__take_break") and not event.failed:
                tokens = reading.context_tokens if reading else session.get("context_tokens")
                _record_break(store, cfg, sid, project, float(session["started_at"]), tokens)
            return None
    result, level = outcome.score, outcome.level
    if result is None or level is None:
        return None

    agent_text, developer_text = score.render_nudge(
        result, level, outcome.model, cfg.mode == "auto"
    )
    logs.write(
        f"nudge session={sid[:8]} level={level} trigger={result.trigger} "
        f"tokens={result.context_tokens} knee={result.knee} ({outcome.knee_source}) "
        f"pressure={result.pressure} behavior={result.behavior} baseline={result.baseline} "
        f"counts={json.dumps(result.counts, sort_keys=True)}",
        cfg.home,
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure" if failed else "PostToolUse",
            "additionalContext": agent_text,
        },
        "systemMessage": developer_text,
        "terminalSequence": NOTIFY_SEQUENCE,
    }


def post_tool_use_failure(payload: Payload, cfg: config.Config) -> Output:
    return post_tool_use(payload, cfg, failed=True)


def post_model_switch(payload: Payload, cfg: config.Config) -> Output:
    sid = _session_id(payload)
    model = payload.get("to_model")
    tokens = payload.get("context_tokens")
    project = project_hash(str(_project_dir(payload)))
    with Store.open(cfg.db_path) as store:
        store.touch_session(sid, project, model=model if isinstance(model, str) else None)
        if isinstance(tokens, int):
            store.update_session(sid, context_tokens=tokens)
    return None


def pre_compact(payload: Payload, cfg: config.Config) -> Output:
    sid = _session_id(payload)
    project = project_hash(str(_project_dir(payload)))
    reading = transcript.read_tail(payload.get("transcript_path"))
    with Store.open(cfg.db_path) as store:
        session = store.touch_session(sid, project)
        tokens = reading.context_tokens if reading else session.get("context_tokens")
        model = (reading.model if reading else None) or session.get("model_last")
        store.record_compaction(sid, payload.get("trigger"), tokens, model)
    logs.write(
        f"compaction session={sid[:8]} trigger={payload.get('trigger')} tokens={tokens}", cfg.home
    )
    return None


def stop(payload: Payload, cfg: config.Config) -> Output:
    sid = _session_id(payload)
    with Store.open(cfg.db_path) as store:
        session = store.get_session(sid)
        if not session or not session.get("break_at") or session.get("reminded"):
            return None
        store.update_session(sid, reminded=1)
    return {"systemMessage": STOP_REMINDER_AUTO if cfg.mode == "auto" else STOP_REMINDER}


def session_end(payload: Payload, cfg: config.Config) -> Output:
    sid = _session_id(payload)
    with Store.open(cfg.db_path) as store:
        store.update_session(sid, ended_at=time.time())
    return None


HANDLERS: dict[str, Callable[[Payload, config.Config], Output]] = {
    "session_start": session_start,
    "post_tool_use": post_tool_use,
    "post_tool_use_failure": post_tool_use_failure,
    "post_model_switch": post_model_switch,
    "pre_compact": pre_compact,
    "stop": stop,
    "session_end": session_end,
}


def run(event: str, raw: bytes) -> Output:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("hook input is not a JSON object")
    handler = HANDLERS.get(event)
    if handler is None:
        raise ValueError(f"unknown hook event {event!r}")
    return handler(payload, config.load())


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    args = sys.argv[1:] if argv is None else argv
    event = args[0] if args else "?"
    outcome = "ok"
    output: Output = None
    try:
        output = run(event, sys.stdin.buffer.read())
    except BaseException as exc:  # fail open on everything (NFR-1)
        output = None
        outcome = "error"
        logs.error(f"hook {event}", exc)
    ms = (time.perf_counter() - started) * 1000
    logs.write(f"hook {event} {outcome} ms={ms:.1f}{' output' if output else ''}")
    if output:
        try:
            # ASCII-escaped: a Windows console encoding can't print the emoji (D-030).
            sys.stdout.write(json.dumps(output) + "\n")
            sys.stdout.flush()
        except BaseException as exc:
            logs.error(f"hook {event} write", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
