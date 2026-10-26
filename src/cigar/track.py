"""The scoring core, shared by the hooks, the `record_event` MCP tool and custom agent
loops (FR-M2).

`record` stores one main-agent event, scores it and applies the nudge policy.
`knee_for` picks the knee: an override, a learned one (medium confidence or
above, FR-L3), or the default. `Tracker` is the small public helper for Python
agent loops:

    from cigar.track import Tracker

    tracker = Tracker(session_id="run-42", model="gpt-5")
    result = tracker.record("read_file", ok=True, context_tokens=84_000,
                            kind="read", path="src/app.py")
    if result.break_suggested:
        print(result.message)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cigar import config, defaults, score, signals
from cigar.store import Store, project_hash

if TYPE_CHECKING:
    from cigar.knee import Fit

KINDS = ("read", "edit", "shell", "other")


def is_cigar_tool(tool: str) -> bool:
    return tool.startswith("mcp__") and "cigar" in tool


# --- knees ------------------------------------------------------------------------
def knee_for(store: Store, cfg: config.Config, model: str | None, window: str) -> tuple[int, str]:
    """(knee, source) where source is "override", "learned (<confidence>)" or "default"."""
    if cfg.knee_tokens and cfg.knee_tokens > 0:
        return cfg.knee_tokens, "override"
    if model:
        cached = store.get_meta(f"knee:{model}:{window}")
        try:
            data = json.loads(cached) if cached else None
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("trusted") and isinstance(data.get("knee"), int):
            return data["knee"], f"learned ({data.get('confidence')})"
    return score.default_knee(model, window), "default"


def fits(store: Store) -> list[Fit]:
    """A knee fit per (model, window), most events first."""
    from cigar import knee

    rows = store.knee_rows(defaults.KNEE_BUCKET_TOKENS)
    weights: dict[tuple[str, str, int], list[float]] = {}
    for model, window, bucket, raw, n in rows["signals"]:
        names = json.loads(raw) if raw else []
        entry = weights.setdefault((model, window, bucket), [0, 0.0])
        entry[0] += n
        entry[1] += n * signals.weight(names)
    sessions = {(m, w, b): n for m, w, b, n in rows["sessions"]}
    out = []
    for model, window, n_sessions, _ in rows["groups"]:
        buckets = [
            knee.Bucket(
                lo=b * defaults.KNEE_BUCKET_TOKENS,
                events=int(events),
                sessions=sessions.get((m, w, b), 0),
                weight=round(total, 6),
            )
            for (m, w, b), (events, total) in weights.items()
            if (m, w) == (model, window)
        ]
        default = score.default_knee(model, window)
        out.append(knee.fit(model, window, buckets, int(n_sessions), default))
    return sorted(out, key=lambda f: -f.events)


def harnesses(store: Store) -> dict[tuple[str, str], list[str]]:
    rows = store.knee_rows(defaults.KNEE_BUCKET_TOKENS)["groups"]
    return {(m, w): sorted(set((h or "").split(","))) for m, w, _, h in rows}


def refresh_knees(store: Store, force: bool = False, now: float | None = None) -> list[Fit] | None:
    """Refit every knee and cache it in meta for the hooks. Throttled unless forced."""
    now = time.time() if now is None else now
    stamp = store.get_meta("knees_at")
    if not force and stamp and now - float(stamp) < defaults.KNEE_REFRESH_SECONDS:
        return None
    result = fits(store)
    for f in result:
        cached = {"knee": f.knee, "confidence": f.confidence, "trusted": f.trusted, "ts": now}
        store.set_meta(f"knee:{f.model}:{f.window}", json.dumps(cached))
    store.set_meta("knees_at", str(now))
    return result


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


# --- one event ----------------------------------------------------------------------
@dataclass(frozen=True)
class Outcome:
    score: score.Score | None  # None for Cigar's own tools, which are never scored
    level: int | None  # nudge level when a nudge fires now (cooldown and cap applied)
    model: str | None
    window: str
    knee_source: str


def record(
    store: Store,
    cfg: config.Config,
    session: dict[str, Any],
    event: signals.Event,
    tokens: int | None,
    model: str | None,
) -> Outcome:
    """Store one main-agent event of `session`, score it, apply the nudge policy."""
    sid = session["id"]
    tokens = tokens if tokens is not None else session.get("context_tokens")
    model = model or session.get("model_last")
    event_id = store.insert_event(sid, event, False, tokens, model)
    window = score.context_window(
        session.get("context_window"), cfg.context_window, model, tokens or 0
    )
    updates: dict[str, Any] = {}
    if tokens is not None:
        updates["context_tokens"] = tokens
    if model:
        updates["model_last"] = model
    if window != session.get("context_window"):
        updates["context_window"] = window
    store.update_session(sid, **updates)

    if is_cigar_tool(event.tool):
        store.set_event_signals(event_id, (), 0.0)
        return Outcome(None, None, model, window, "")

    history = store.recent_events(sid, defaults.UNDO_LOOKBACK_EVENTS, before_id=event_id)
    path_history = (
        store.path_events(sid, event.path, event_id) if event.kind == "read" and event.path else []
    )
    found = signals.detect(event, history, path_history)
    recent = [e.signals for e in history[-(defaults.WINDOW_EVENTS - 1) :]] + [found]
    knee, source = knee_for(store, cfg, model, window)
    base = _baseline(store, model, knee)
    result = score.evaluate(recent, tokens or 0, knee, base, cfg.min_tokens)
    store.set_event_signals(event_id, found, result.behavior)

    level = None
    if cfg.mode != "observe":
        seq = int(session.get("main_events") or 0) + 1
        last = session.get("last_nudge_seq")
        level = score.nudge_level(
            result,
            int(session.get("nudges") or 0),
            None if last is None else seq - int(last),
            cfg.cooldown_events,
            cfg.max_nudges,
        )
        if level is not None:
            store.record_nudge(sid, seq)
    return Outcome(result, level, model, window, source)


# --- custom agent loops (FR-M2) -----------------------------------------------------
@dataclass(frozen=True)
class Result:
    break_suggested: bool
    message: str | None  # the factual nudge text, when a break is suggested
    fatigue: float
    behavior: float
    pressure: float
    context_tokens: int | None
    knee: int
    knee_source: str
    signals: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def record_external(
    cfg: config.Config,
    session_id: str,
    tool: str,
    ok: bool = True,
    context_tokens: int | None = None,
    model: str | None = None,
    path: str | None = None,
    args: dict[str, Any] | None = None,
    kind: str | None = None,
    exit_code: int | None = None,
    project: str | os.PathLike[str] | None = None,
    harness: str = "custom",
) -> Result:
    """Record one tool call from an agent loop that has no Claude Code hooks."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    error = None if ok or exit_code is None else f"Exit code {exit_code}"
    event = signals.extract(
        tool, dict(args or {}), None, error=error, failed=not ok, kind=kind, path=path
    )
    if ok and exit_code not in (None, 0):
        event = replace(event, failed=True, exit_code=exit_code)
    project_dir = Path(project or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    with Store.open(cfg.db_path) as store:
        session = store.touch_session(session_id, project_hash(str(project_dir)), model=model)
        if session.get("harness") != harness and not session.get("main_events"):
            store.update_session(session_id, harness=harness)
        outcome = record(store, cfg, session, event, context_tokens, model)
    s = outcome.score
    if s is None:
        knee, source = score.default_knee(outcome.model, outcome.window), "default"
        return Result(False, None, 0.0, 0.0, 0.0, context_tokens, knee, source, {})
    message = None
    if outcome.level is not None:
        message = score.render_nudge(s, outcome.level, outcome.model)[0]
    return Result(
        break_suggested=outcome.level is not None,
        message=message,
        fatigue=s.fatigue,
        behavior=s.behavior,
        pressure=s.pressure,
        context_tokens=s.context_tokens,
        knee=s.knee,
        knee_source=outcome.knee_source,
        signals=s.counts,
    )


class Tracker:
    """Cigar detection for a custom Python agent loop. One instance per agent session."""

    def __init__(
        self,
        session_id: str | None = None,
        model: str | None = None,
        project: str | os.PathLike[str] | None = None,
        harness: str = "python",
    ) -> None:
        self.session_id = session_id or f"py-{uuid.uuid4().hex[:12]}"
        self.model = model
        self.project = project
        self.harness = harness

    def record(
        self,
        tool: str,
        ok: bool = True,
        context_tokens: int | None = None,
        *,
        model: str | None = None,
        kind: str | None = None,
        path: str | None = None,
        args: dict[str, Any] | None = None,
        exit_code: int | None = None,
    ) -> Result:
        return record_external(
            config.load(),
            self.session_id,
            tool,
            ok=ok,
            context_tokens=context_tokens,
            model=model or self.model,
            path=path,
            args=args,
            kind=kind,
            exit_code=exit_code,
            project=self.project,
            harness=self.harness,
        )
