"""Replay synthetic transcripts through the hooks and check when nudges fire.

The fixtures come from tests/fixtures/make_transcripts.py. Real transcripts in
tests/fixtures/private/ (gitignored) are replayed too, locally only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import FIXTURES, Step, replay

TRANSCRIPTS = FIXTURES / "transcripts"


def run(name: str, tmp_path: Path) -> list[Step]:
    return list(replay(TRANSCRIPTS / f"{name}.jsonl", tmp_path, session=name))


def nudges(steps: list[Step]) -> list[Step]:
    return [s for s in steps if s.output]


def context(step: Step) -> str:
    assert step.output
    return step.output["hookSpecificOutput"]["additionalContext"]


def test_degrading_session_nudges_past_the_knee_three_times(tmp_path: Path) -> None:
    steps = run("degrading", tmp_path)
    assert len(steps) == 140
    fired = nudges(steps)
    assert len(fired) == 3
    first, second, third = fired
    # Healthy until call 80 (~104k); degradation starts after it, past the 100k knee.
    assert first.index > 80 and 100_000 <= first.tokens < 115_000
    assert "Past the knee" in context(first)
    assert second.index - first.index >= 25 and third.index - second.index >= 25
    assert context(second).startswith("Second Cigar session check")
    assert context(third).startswith("Final Cigar session check")


def test_healthy_session_is_never_nudged_below_hard_pressure(tmp_path: Path) -> None:
    steps = run("healthy", tmp_path)
    assert steps[-1].tokens >= 145_000  # past the 120k opus knee, under 1.3x
    assert nudges(steps) == []


def test_early_struggle_below_floor_is_not_fatigue(tmp_path: Path) -> None:
    steps = run("early_struggle", tmp_path)
    assert all(s.tokens < 40_000 for s in steps)
    assert nudges(steps) == []


def test_distress_before_knee_fires_rule_c_after_enough_events(tmp_path: Path) -> None:
    fired = nudges(run("distress", tmp_path))
    assert fired, "expected a distress nudge"
    assert fired[0].index >= 10 and fired[0].tokens < 120_000
    assert "even before the knee" in context(fired[0])


PRIVATE = sorted((FIXTURES / "private").glob("*.jsonl"))


@pytest.mark.skipif(not PRIVATE, reason="no private transcripts in tests/fixtures/private/")
@pytest.mark.parametrize("source", PRIVATE, ids=lambda p: p.name)
def test_private_replay(source: Path, tmp_path: Path) -> None:
    steps = list(replay(source, tmp_path, session="private"))
    for step in nudges(steps):
        print(f"nudge at call {step.index} ({step.tokens} tokens): {context(step)[:160]}")
    assert len(nudges(steps)) <= 3
