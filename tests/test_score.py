from __future__ import annotations

import pytest

from cigar import defaults, score


def window(*signals: tuple[str, ...], size: int = 20) -> list[tuple[str, ...]]:
    return [()] * (size - len(signals)) + list(signals)


@pytest.mark.parametrize(
    ("model", "window", "expected"),
    [
        ("claude-opus-5-5", "200k", 120_000),
        ("claude-sonnet-5-5", "200k", 100_000),
        ("claude-haiku-4-5-20251001", "200k", 70_000),
        ("claude-opus-5-5", "1m", 160_000),
        ("gpt-5", "200k", 100_000),  # fallback: min(0.5 x 200k, 120k)
        ("gpt-5", "1m", 120_000),  # fallback: min(0.5 x 1M, 120k)
        (None, "200k", 100_000),
    ],
)
def test_default_knee(model: str | None, window: str, expected: int) -> None:
    assert score.default_knee(model, window) == expected


@pytest.mark.parametrize(
    ("stored", "configured", "model", "tokens", "expected"),
    [
        (None, None, "claude-opus-5-5", 150_000, "200k"),
        (None, None, "claude-opus-5-5", 200_001, "1m"),  # past 200k: a 1M window
        ("1m", None, "claude-opus-5-5", 40_000, "1m"),  # sticky after compaction
        ("1m", "200k", "claude-opus-5-5", 40_000, "1m"),  # evidence beats config
        (None, "200k", "claude-opus-5-5", 250_000, "1m"),
        (None, "1m", "claude-opus-5-5", 40_000, "1m"),  # the developer knows
        ("200k", "1m", "claude-opus-5-5", 40_000, "1m"),
        (None, None, "claude-opus-5-5[1m]", 50_000, "1m"),
        (None, None, None, 0, "200k"),
    ],
)
def test_context_window(
    stored: str | None, configured: str | None, model: str | None, tokens: int, expected: str
) -> None:
    assert score.context_window(stored, configured, model, tokens) == expected


def test_knee_override() -> None:
    assert score.default_knee("claude-opus-5-5", "200k", override=20_000) == 20_000
    assert score.default_knee("claude-opus-5-5", "200k", override=0) == 120_000


def test_behavior_is_capped() -> None:
    assert score.behavior([("failure", "undo")] * 3) == 1.0
    assert score.behavior([]) == 0.0
    assert score.behavior(window(("failure",), ("reread",))) == pytest.approx(0.075)


def test_baseline_needs_enough_events() -> None:
    assert score.baseline([0.3] * 10) == defaults.DEFAULT_BASELINE
    assert score.baseline([0.2] * defaults.BASELINE_MIN_EVENTS) == 0.2


def test_floor_blocks_every_rule() -> None:
    s = score.evaluate(window(*[("failure",)] * 20), 39_000, 20_000, min_tokens=40_000)
    assert s.trigger is None


def test_rule_a_past_knee_with_elevated_behavior() -> None:
    w = window(("failure",), ("failure",), ("reread",))  # 2.5 / 20 = 0.125
    assert score.evaluate(w, 100_000, 100_000).trigger is None  # 0.125 < 0.08 + 0.10
    w = window(("failure",), ("failure",), ("failure",), ("reread",))  # 0.175 < 0.18
    assert score.evaluate(w, 100_000, 100_000).trigger is None
    w = window(("failure",), ("failure",), ("failure",), ("undo",))  # 0.2
    assert score.evaluate(w, 100_000, 100_000).trigger == "a"
    assert score.evaluate(w, 99_000, 100_000).trigger is None


def test_rule_b_well_past_knee() -> None:
    assert score.evaluate(window(), 130_000, 100_000).trigger == "b"
    assert score.evaluate(window(), 129_000, 100_000).trigger is None


def test_rule_c_distress_before_knee() -> None:
    w = window(*[("failure",)] * 9)  # 0.45
    assert score.evaluate(w, 60_000, 100_000).trigger == "c"
    assert score.evaluate(w, 59_000, 100_000).trigger is None


def test_behavior_rules_need_a_minimum_window() -> None:
    few = [("failure",)] * 9
    assert score.evaluate(few, 100_000, 100_000).trigger is None  # 9 events: too few
    assert score.evaluate([*few, ()], 100_000, 100_000).trigger == "a"
    assert score.evaluate(few, 70_000, 100_000).trigger is None
    assert score.evaluate(few[:1], 130_000, 100_000).trigger == "b"  # pressure alone


def test_fatigue_formula() -> None:
    s = score.evaluate(window(*[("failure",)] * 9), 150_000, 100_000)
    assert s.fatigue == 1.0
    s = score.evaluate(window(), 75_000, 100_000)
    assert s.fatigue == pytest.approx(0.25)


def test_nudge_policy_cooldown_and_cap() -> None:
    s = score.evaluate(window(), 140_000, 100_000)
    assert score.nudge_level(s, 0, None) == 1
    assert score.nudge_level(s, 1, 24) is None
    assert score.nudge_level(s, 1, 25) == 2
    assert score.nudge_level(s, 3, 100) is None
    healthy = score.evaluate(window(), 50_000, 100_000)
    assert score.nudge_level(healthy, 0, None) is None


def test_nudge_text_is_factual_with_evidence() -> None:
    w = window(("failure",), ("failure",), ("reread",), ("undo",))
    s = score.evaluate(w, 142_000, 120_000)
    agent, developer = score.render_nudge(s, 1, "claude-sonnet-5")
    assert agent.startswith("Cigar session check: context is at 142k tokens")
    assert "the knee for claude-sonnet-5 is ~120k" in agent
    assert "2 failed, 1 files re-read without edits, 1 edits undone" in agent
    assert "`take_break`" in agent
    for word in ("must", "MUST", "IMPORTANT", "you should", "immediately"):
        assert word not in agent
    assert developer.startswith("🚬 Cigar: this session shows fatigue (142k tokens, 4 signals")
    assert "/cigar:break" in developer
    stronger, _ = score.render_nudge(s, 3, "m")
    assert stronger.startswith("Final Cigar session check")
