"""How reliably the knee estimator recovers a planted knee, and how often flat data fools it.

    uv run python scripts/estimator_check.py

Runs scripts/simulate.py's generator over many seeds in temporary stores.
The test suite checks a few fixed seeds; this sweep backs the claim in D-029.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import simulate

from cigar import track
from cigar.store import Store

SEEDS = range(20)
CASES = (
    ("claude-sonnet-5-5", "200k", 120, (80_000, 95_000, 110_000, 125_000, 140_000)),
    ("claude-opus-5-5", "1m", 80, (150_000, 170_000, 220_000)),
)


def fit_once(model: str, window: str, knee: int, sessions: int, seed: int, slope: float):
    with tempfile.TemporaryDirectory() as tmp, Store.open(Path(tmp) / "c.db") as store:
        simulate.simulate(store, model, window, knee, sessions, seed=seed, slope=slope)
        (fit,) = track.fits(store)
        return fit


def main() -> int:
    for model, window, sessions, knees in CASES:
        errors = [
            fit_once(model, window, k, sessions, 1000 + s, 0.5).knee for k in knees for s in SEEDS
        ]
        planted = [k for k in knees for _ in SEEDS]
        hits = sum(
            1 for got, k in zip(errors, planted, strict=True) if got and abs(got - k) <= 10_000
        )
        print(
            f"{window} window, {sessions} sessions, knees {[k // 1000 for k in knees]}k x "
            f"{len(SEEDS)} seeds: {hits}/{len(planted)} recovered within +-10k"
        )
    for sessions in (40, 120):
        found = [
            f.knee
            for s in range(30)
            if (f := fit_once("claude-sonnet-5-5", "200k", 110_000, sessions, 2000 + s, 0.0)).knee
        ]
        print(
            f"flat data (no knee), {sessions} sessions x 30 seeds: spurious knee in {len(found)}/30"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
