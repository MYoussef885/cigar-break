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

from cigar import auto, config, defaults, logs, score, signals, transcript
from cigar.store import Store, project_hash

Payload = dict[str, Any]
Output = dict[str, Any] | None

NOTIFY_SEQUENCE = "\x1b]9;Cigar: this session shows fatigue\x07"
STOP_REMINDER = "🚬 Handoff ready. Type /clear to take the break (or /compact to keep a summary)."
STOP_REMINDER_AUTO = (
    "🚬 Handoff ready. Cigar auto mode clears the context now; if it doesn't, type /clear."
)


def _project_dir(payload: Payload) -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(raw)


def _is_cigar_tool(tool: str) -> bool:
    return tool.startswith("mcp__") and "cigar" in tool


def _session_id(payload: Payload) -> str:
    sid = payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError("hook input has no session_id")
    return sid


# --- handlers -------------------------------------------------------------------
def session_start(payload: Payload, cfg: config.Config) -> Output:
    from cigar import handoff

    sid = _session_id(payload)
    source = payload.get("source")
    model = payload.get("model") if isinstance(payload.get("model"), str) else None
    project_dir = _project_dir(payload)
    project = project_hash(str(project_dir))
    with Store.open(cfg.db_path) as store:
        store.touch_session(sid, project, model=model, source=source)
        auto.prune(cfg.home)
        if source not in ("clear", "compact"):
            logs.prune(cfg.home)
            return None
        pending = store.pending_handoff(project, defaults.HANDOFF_MAX_AGE_SECONDS)
        if not pending:
            return None
        markdown = handoff.load(project_dir, pending["path"])
        if markdown is None:
            logs.write(f"restore skipped: handoff file missing ({pending['path']})", cfg.home)
            return None
        text = handoff.for_injection(markdown, pending["path"])
        store.consume_handoff(pending["id"])
    logs.write(f"restore session={sid[:8]} source={source} chars={len(text)}", cfg.home)
    return {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
        "systemMessage": f"🚬 Cigar: restored the handoff from {pending['path']}.",
    }


def _baseline(store: Store, model: str | None, knee: int) -> float:
    if not model:
        return defaults.DEFAULT_BASELINE
    key = f"baseline:{model}:{knee}"
    cached = store.get_meta(key)
    now = time.time()
    if cached:
        value, stamp = json.loads(cached)
        if now - stamp < defaults.BASELINE_CACHE_SECONDS:
            return float(value)
    below = int(knee * defaults.BASELINE_KNEE_FRACTION)
    value = score.baseline(store.low_pressure_behaviors(model, below))
    store.set_meta(key, json.dumps([value, now]))
    return value


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
        tokens = reading.context_tokens if reading else session.get("context_tokens")
        model = (reading.model if reading else None) or session.get("model_last")
        event_id = store.insert_event(sid, event, False, tokens, model)
        updates: dict[str, Any] = {}
        if tokens is not None:
            updates["context_tokens"] = tokens
        if model:
            updates["model_last"] = model
        store.update_session(sid, **updates)

        if _is_cigar_tool(tool):
            # Cigar's own tools are recorded but never scored.
            store.set_event_signals(event_id, (), 0.0)
            if tool.endswith("__take_break") and not event.failed:
                store.record_break(sid)
                if cfg.mode == "auto":
                    auto.mark_ready(cfg.home, sid)
                logs.write(f"break session={sid[:8]} tokens={tokens} mode={cfg.mode}", cfg.home)
            return None

        history = store.recent_events(sid, defaults.UNDO_LOOKBACK_EVENTS, before_id=event_id)
        path_history = (
            store.path_events(sid, event.path, event_id)
            if event.kind == "read" and event.path
            else []
        )
        found = signals.detect(event, history, path_history)
        window = [e.signals for e in history[-(defaults.WINDOW_EVENTS - 1) :]] + [found]
        knee = score.default_knee(model, tokens or 0, cfg.knee_tokens)
        base = _baseline(store, model, knee)
        result = score.evaluate(window, tokens or 0, knee, base, cfg.min_tokens)
        store.set_event_signals(event_id, found, result.behavior)

        if cfg.mode == "observe":
            return None
        seq = int(session.get("main_events") or 0) + 1
        last = session.get("last_nudge_seq")
        level = score.nudge_level(
            result,
            int(session.get("nudges") or 0),
            None if last is None else seq - int(last),
            cfg.cooldown_events,
            cfg.max_nudges,
        )
        if level is None:
            return None
        store.record_nudge(sid, seq)

    agent_text, developer_text = score.render_nudge(result, level, model, cfg.mode == "auto")
    logs.write(
        f"nudge session={sid[:8]} level={level} trigger={result.trigger} "
        f"tokens={result.context_tokens} knee={result.knee} pressure={result.pressure} "
        f"behavior={result.behavior} baseline={result.baseline} "
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
            sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except BaseException as exc:
            logs.error(f"hook {event} write", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
