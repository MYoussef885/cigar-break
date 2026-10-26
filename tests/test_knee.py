"""Knee estimation (architecture §9): unit tests and recovery of a planted knee."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from helpers import ROOT

from cigar import config, knee, track
from cigar.store import Store

sys.path.insert(0, str(ROOT / "scripts"))
import simulate


def buckets(*rates: float, events: int = 100, sessions: int = 5, start: int = 30) -> list:
    return [
        knee.Bucket(lo=(start + i * 10) * 1000, events=events, sessions=sessions, weight=r * events)
        for i, r in enumerate(rates)
    ]


def test_flat_rate_has_no_knee() -> None:
    f = knee.fit("m", "200k", buckets(*[0.08] * 12), 20, 100_000)
    assert (f.knee, f.baseline, f.confidence) == (None, 0.08, "high")
    assert not f.trusted


def test_step_finds_the_lowest_sustained_rise() -> None:
    rates = [0.08] * 6 + [0.10, 0.2, 0.25, 0.3, 0.35, 0.4]
    f = knee.fit("m", "200k", buckets(*rates), 20, 100_000)
    assert f.knee == 90_000  # 90k: (0.10 + 0.2 + 0.25) / 3 >= 1.5 x 0.08
    assert f.trusted


def test_a_blip_that_falls_back_is_not_a_knee() -> None:
    rates = [0.08] * 5 + [0.3, 0.3, 0.3, 0.05, 0.08, 0.3, 0.3, 0.3]
    f = knee.fit("m", "200k", buckets(*rates), 20, 100_000)
    assert f.knee == 130_000


def test_buckets_without_enough_evidence_do_not_count() -> None:
    few = [
        *buckets(0.08, 0.08, 0.08, 0.08),
        knee.Bucket(lo=70_000, events=49, sessions=9, weight=40.0),  # too few events
        knee.Bucket(lo=80_000, events=500, sessions=2, weight=400.0),  # too few sessions
    ]
    f = knee.fit("m", "200k", few, 20, 100_000)
    assert len(f.counting) == 4 and f.knee is None and f.confidence == "low"


def test_baseline_has_a_floor() -> None:
    f = knee.fit("m", "200k", buckets(0, 0, 0, 0, 0, 0.01, 0.01, 0.01), 20, 100_000)
    assert f.baseline == 0.02 and f.knee is None


@pytest.mark.parametrize(
    ("sessions", "n_buckets", "expected"),
    [(4, 12, "low"), (5, 5, "low"), (5, 6, "medium"), (14, 12, "medium"), (15, 10, "high")],
)
def test_confidence(sessions: int, n_buckets: int, expected: str) -> None:
    assert knee.confidence(sessions, n_buckets) == expected


@pytest.mark.parametrize(
    ("planted", "seed"), [(90_000, 1), (110_000, 2), (115_000, 3), (130_000, 4), (100_000, 5)]
)
def test_estimator_recovers_the_planted_knee(planted: int, seed: int, tmp_path: Path) -> None:
    """Roadmap gate: the planted knee is recovered within +-10k tokens."""
    with Store.open(tmp_path / "c.db") as store:
        simulate.simulate(store, "claude-sonnet-5-5", "200k", planted, seed=seed)
        (fit,) = track.fits(store)
    assert fit.knee is not None and abs(fit.knee - planted) <= 10_000, (planted, fit.knee)
    assert fit.confidence in ("medium", "high")


def test_estimator_on_a_1m_window(tmp_path: Path) -> None:
    with Store.open(tmp_path / "c.db") as store:
        simulate.simulate(store, "claude-opus-5-5", "1m", 170_000, sessions=80, seed=9)
        (fit,) = track.fits(store)
    assert fit.window == "1m" and fit.default_knee == 160_000
    assert fit.knee is not None and abs(fit.knee - 170_000) <= 10_000


def test_learned_knee_replaces_the_default(tmp_path: Path, cigar_home: Path) -> None:
    cfg = config.load()
    with Store.open(cfg.db_path) as store:
        assert track.knee_for(store, cfg, "claude-sonnet-5-5", "200k") == (100_000, "default")
        simulate.simulate(store, "claude-sonnet-5-5", "200k", 120_000, seed=3)
        assert track.refresh_knees(store) is not None
        assert track.refresh_knees(store) is None  # throttled
        learned, source = track.knee_for(store, cfg, "claude-sonnet-5-5", "200k")
        assert abs(learned - 120_000) <= 10_000 and source.startswith("learned (")
        # A different window of the same model keeps its default.
        assert track.knee_for(store, cfg, "claude-sonnet-5-5", "1m") == (140_000, "default")


def test_low_confidence_keeps_the_default(tmp_path: Path, cigar_home: Path) -> None:
    cfg = config.load()
    with Store.open(cfg.db_path) as store:
        simulate.simulate(store, "claude-sonnet-5-5", "200k", 90_000, sessions=4, seed=1)
        (fit,) = track.refresh_knees(store, force=True) or []
        assert fit.confidence == "low"
        assert track.knee_for(store, cfg, "claude-sonnet-5-5", "200k") == (100_000, "default")


def test_cigar_tools_and_subagents_are_not_learned_from(tmp_path: Path) -> None:
    from cigar.signals import extract

    with Store.open(tmp_path / "c.db") as store:
        store.touch_session("s", "p")
        main = store.insert_event("s", extract("Bash", {"command": "ls"}), False, 50_000, "m")
        store.set_event_signals(main, ("failure",), 1.0)
        mine = extract("mcp__plugin_cigar_cigar__status", {})
        store.set_event_signals(store.insert_event("s", mine, False, 50_000, "m"), (), 0.0)
        sub = store.insert_event("s", extract("Bash", {}), True, 50_000, "m")
        store.set_event_signals(sub, ("failure",), 1.0)
        (fit,) = track.fits(store)
    assert [(b.lo, b.events, b.weight) for b in fit.buckets] == [(50_000, 1, 1.0)]


def test_simulate_refuses_the_real_home() -> None:
    assert simulate.main(["--home", str(Path.home() / ".cigar")]) == 2
