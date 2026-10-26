"""Knee estimation (architecture §9, FR-L1 to FR-L3). Pure functions, no I/O.

Events of one model and window are grouped into 10k-token buckets. A bucket
counts when it has enough events from enough sessions. The knee is the lowest
counting bucket where the signal rate rises clearly above the model's own
baseline and stays above it.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from cigar import defaults


@dataclass(frozen=True)
class Bucket:
    lo: int  # tokens, inclusive
    events: int
    sessions: int
    weight: float  # summed signal weight of the bucket's events

    @property
    def hi(self) -> int:
        return self.lo + defaults.KNEE_BUCKET_TOKENS

    @property
    def rate(self) -> float:
        return self.weight / self.events if self.events else 0.0

    @property
    def counts(self) -> bool:
        return (
            self.events >= defaults.KNEE_MIN_BUCKET_EVENTS
            and self.sessions >= defaults.KNEE_MIN_BUCKET_SESSIONS
        )


@dataclass(frozen=True)
class Fit:
    model: str
    window: str  # "200k" or "1m"
    sessions: int
    events: int
    buckets: tuple[Bucket, ...]  # every bucket with events, by tokens
    baseline: float | None
    knee: int | None
    confidence: str  # "low", "medium" or "high"
    default_knee: int

    @property
    def counting(self) -> tuple[Bucket, ...]:
        return tuple(b for b in self.buckets if b.counts)

    @property
    def trusted(self) -> bool:
        """A learned knee replaces the default only at medium confidence or above (FR-L3)."""
        return self.knee is not None and self.confidence in ("medium", "high")


def confidence(sessions: int, counting_buckets: int) -> str:
    high_sessions, high_buckets = defaults.KNEE_HIGH
    medium_sessions, medium_buckets = defaults.KNEE_MEDIUM
    if sessions >= high_sessions and counting_buckets >= high_buckets:
        return "high"
    if sessions >= medium_sessions and counting_buckets >= medium_buckets:
        return "medium"
    return "low"


def baseline(counting: Sequence[Bucket]) -> float | None:
    """Median rate of the counting buckets that hold the lowest 40% of their events."""
    if not counting:
        return None
    total = sum(b.events for b in counting)
    low: list[Bucket] = []
    seen = 0
    for b in counting:
        seen += b.events
        if seen > defaults.KNEE_LOW_FRACTION * total and low:
            break
        low.append(b)
    value = float(statistics.median(b.rate for b in low))
    return max(value, defaults.KNEE_BASELINE_FLOOR)


def find_knee(counting: Sequence[Bucket], base: float) -> int | None:
    """The lowest bucket where it and the next two average >= 1.5 x baseline, and the
    rate never drops back below baseline after it.

    The bucket's own rate must be above baseline too (D-029): otherwise a sharp
    rise is reported one or two flat buckets early.
    """
    run = defaults.KNEE_RUN_BUCKETS
    for i in range(len(counting) - run + 1):
        if counting[i].rate <= base:
            continue
        mean = sum(b.rate for b in counting[i : i + run]) / run
        if mean < defaults.KNEE_RISE * base:
            continue
        if all(b.rate >= base for b in counting[i + 1 :]):
            return counting[i].lo
    return None


def fit(
    model: str,
    window: str,
    buckets: Sequence[Bucket],
    sessions: int,
    default_knee: int,
) -> Fit:
    ordered = tuple(sorted(buckets, key=lambda b: b.lo))
    counting = [b for b in ordered if b.counts]
    base = baseline(counting)
    knee = find_knee(counting, base) if base is not None else None
    return Fit(
        model=model,
        window=window,
        sessions=sessions,
        events=sum(b.events for b in ordered),
        buckets=ordered,
        baseline=None if base is None else round(base, 4),
        knee=knee,
        confidence=confidence(sessions, len(counting)),
        default_knee=default_knee,
    )
