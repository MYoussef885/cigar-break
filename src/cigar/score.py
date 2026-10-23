"""Fatigue score, nudge policy and nudge text (architecture §6 and §7). Pure functions."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from cigar import defaults
from cigar.signals import weight


@dataclass(frozen=True)
class Score:
    context_tokens: int
    knee: int
    baseline: float
    behavior: float
    pressure: float
    fatigue: float
    events: int
    counts: dict[str, int]
    trigger: str | None  # "a", "b", "c" or None (architecture §6)


def window_size(model: str | None, observed_tokens: int = 0) -> int:
    if model and defaults.EXTENDED_MARKERS.search(model):
        return defaults.EXTENDED_WINDOW
    if observed_tokens > defaults.STANDARD_WINDOW:
        return defaults.EXTENDED_WINDOW
    return defaults.STANDARD_WINDOW


def default_knee(model: str | None, observed_tokens: int = 0, override: int | None = None) -> int:
    """The starting knee for a model (D-017). `override` forces one knee for all."""
    if override and override > 0:
        return override
    window = window_size(model, observed_tokens)
    for pattern, standard, extended in defaults.KNEES:
        if model and re.search(pattern, model, re.IGNORECASE):
            return extended if window == defaults.EXTENDED_WINDOW else standard
    return int(min(defaults.FALLBACK_KNEE_FRACTION * window, defaults.FALLBACK_KNEE_CAP))


def behavior(window: Sequence[Sequence[str]]) -> float:
    """Summed signal weight per event over the window, capped at 1."""
    if not window:
        return 0.0
    return min(1.0, sum(weight(s) for s in window) / len(window))


def baseline(behaviors: Sequence[float]) -> float:
    """Median behavior of low-pressure events, or the default without enough data."""
    if len(behaviors) < defaults.BASELINE_MIN_EVENTS:
        return defaults.DEFAULT_BASELINE
    import statistics  # lazy: slow to import, rarely needed on the hook path

    return float(statistics.median(behaviors))


def evaluate(
    window: Sequence[Sequence[str]],
    context_tokens: int,
    knee: int,
    base: float = defaults.DEFAULT_BASELINE,
    min_tokens: int = defaults.MIN_TOKENS,
) -> Score:
    """Score the last WINDOW_EVENTS main-agent events (their signals, oldest first)."""
    window = list(window)[-defaults.WINDOW_EVENTS :]
    b = behavior(window)
    pressure = context_tokens / knee if knee > 0 else 0.0
    fatigue = 0.5 * min(pressure, defaults.FATIGUE_PRESSURE_CAP) / defaults.FATIGUE_PRESSURE_CAP
    fatigue += 0.5 * b / defaults.DISTRESS_BEHAVIOR
    trigger = None
    if context_tokens >= min_tokens:
        if pressure >= defaults.PRESSURE_KNEE and b >= base + defaults.BEHAVIOR_MARGIN:
            trigger = "a"
        elif pressure >= defaults.PRESSURE_HARD:
            trigger = "b"
        elif b >= defaults.DISTRESS_BEHAVIOR and pressure >= defaults.DISTRESS_PRESSURE:
            trigger = "c"
    counts = Counter(s for signals in window for s in signals)
    return Score(
        context_tokens=context_tokens,
        knee=knee,
        baseline=base,
        behavior=round(b, 4),
        pressure=round(pressure, 4),
        fatigue=round(max(0.0, min(1.0, fatigue)), 4),
        events=len(window),
        counts=dict(counts),
        trigger=trigger,
    )


def nudge_level(
    score: Score,
    nudges_so_far: int,
    events_since_last_nudge: int | None,
    cooldown: int = defaults.COOLDOWN_EVENTS,
    max_nudges: int = defaults.MAX_NUDGES,
) -> int | None:
    """1, 2 or 3 if a nudge should fire now, else None.

    events_since_last_nudge is None when there was no nudge since the last break.
    """
    if score.trigger is None or nudges_so_far >= max_nudges:
        return None
    if events_since_last_nudge is not None and events_since_last_nudge < cooldown:
        return None
    return nudges_so_far + 1


def _k(tokens: int) -> str:
    return f"{round(tokens / 1000)}k"


_PHRASES = (
    ("failure", "{n} failed"),
    ("repeat", "{n} repeated identical calls"),
    ("reread", "{n} files re-read without edits"),
    ("undo", "{n} edits undone"),
    ("check_fail", "{n} failed checks (test, build, lint or type check)"),
)

_REASONS = {
    "a": "Past the knee, sessions usually degrade, and this session's signal rate is above "
    "this model's baseline.",
    "b": "This is well past the knee, where sessions usually degrade.",
    "c": "That signal rate is well above this model's usual rate, even before the knee.",
}

_OPENERS = {
    1: "Cigar session check",
    2: "Second Cigar session check (signals continued after the first)",
    3: "Final Cigar session check (no more checks this session)",
}


def evidence(counts: dict[str, int], events: int) -> str:
    parts = [p.format(n=counts[k]) for k, p in _PHRASES if counts.get(k)]
    if not parts:
        return f"In the last {events} tool calls: no failure signals."
    return f"In the last {events} tool calls: " + ", ".join(parts) + "."


def render_nudge(score: Score, level: int, model: str | None) -> tuple[str, str]:
    """(additionalContext for the agent, systemMessage for the developer). Facts only."""
    model_name = model or "this model"
    agent = (
        f"{_OPENERS.get(level, _OPENERS[3])}: context is at {_k(score.context_tokens)} tokens; "
        f"the knee for {model_name} is ~{_k(score.knee)}. {evidence(score.counts, score.events)} "
        f"{_REASONS.get(score.trigger or 'b', _REASONS['b'])} "
        "The `take_break` tool (cigar MCP) saves a handoff so work can resume in a fresh context."
    )
    signals_total = sum(score.counts.values())
    developer = (
        f"🚬 Cigar: this session shows fatigue ({_k(score.context_tokens)} tokens, "
        f"{signals_total} signals in the last {score.events} calls). "
        "Claude has been offered a break. Run /cigar:break to force one."
    )
    return agent, developer
