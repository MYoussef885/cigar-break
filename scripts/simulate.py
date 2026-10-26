"""Seed data generator: several weeks of fake sessions with a known knee (roadmap S2).

    python3 scripts/simulate.py --home /tmp/cigar-sim
    CIGAR_HOME=/tmp/cigar-sim python3 bin/cigar report --html

Each session's context grows from about 30k tokens. Below the planted knee the
signal rate is flat; from the knee on it rises by `slope` x baseline per 10k
tokens. Sessions are marked harness "simulated" and hold no paths. The script
refuses to write into the real ~/.cigar (D-027).
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cigar import defaults
from cigar.signals import Event
from cigar.store import Store

# (signal, share of signal events, the tool that would show it)
MIX = (
    ("failure", 0.35, "Bash"),
    ("reread", 0.25, "Read"),
    ("repeat", 0.15, "Grep"),
    ("check_fail", 0.15, "Bash"),
    ("undo", 0.10, "Edit"),
)
MEAN_WEIGHT = sum(share * defaults.WEIGHTS[name] for name, share, _ in MIX)
CLEAN_TOOLS = ("Read", "Edit", "Bash", "Grep", "Glob", "Write")
KINDS = {"Read": "read", "Edit": "edit", "Write": "edit", "Bash": "shell"}
PROFILES = (
    # model, window, planted knee, sessions (six weeks at two to three a day)
    ("claude-sonnet-5-5", "200k", 110_000, 120),
    ("claude-opus-5-5", "1m", 170_000, 80),
)


def rate(tokens: int, knee: int, base: float, slope: float) -> float:
    """Expected signal weight per event at this context size."""
    return base * (1 + slope * max(0, tokens - knee) / defaults.KNEE_BUCKET_TOKENS)


def _event(rng: random.Random, signal: str | None) -> Event:
    if signal is None:
        tool = rng.choice(CLEAN_TOOLS)
    else:
        tool = next(t for name, _, t in MIX if name == signal)
    return Event(
        tool=tool,
        kind=KINDS.get(tool, "other"),
        args_hash=f"{rng.getrandbits(64):016x}",
        failed=signal in ("failure", "check_fail"),
        exit_code=1 if signal == "check_fail" else None,
        is_check=signal == "check_fail",
    )


def simulate(
    store: Store,
    model: str,
    window: str,
    knee: int,
    sessions: int = 120,
    seed: int = 7,
    weeks: int = 6,
    base: float = 0.08,
    slope: float = 0.5,
    start: float | None = None,
) -> int:
    """Write `sessions` fake sessions into `store`. Returns the number of events."""
    rng = random.Random(seed)
    size = defaults.WINDOWS[window]
    start = time.time() - weeks * 7 * 86400 if start is None else start
    total = 0
    store.conn.execute("BEGIN")
    try:
        for n in range(sessions):
            sid = f"sim-{seed}-{model}-{n}"
            ts = start + (n + rng.random()) * weeks * 7 * 86400 / sessions
            store.touch_session(sid, f"simproject{seed % 3}", model=model, now=ts)
            store.update_session(sid, harness="simulated", context_window=window)
            tokens = rng.randint(28_000, 38_000)
            peak = rng.randint(int(0.6 * knee), int(min(0.95 * size, 1.9 * knee)))
            recent: list[float] = []
            while tokens < peak:
                p = min(0.95, rate(tokens, knee, base, slope) / MEAN_WEIGHT)
                signal = None
                if rng.random() < p:
                    pick, acc = rng.random(), 0.0
                    for name, share, _ in MIX:
                        acc += share
                        if pick <= acc:
                            signal = name
                            break
                event_id = store.insert_event(sid, _event(rng, signal), False, tokens, model, ts)
                recent = [*recent, defaults.WEIGHTS[signal] if signal else 0.0][-20:]
                store.set_event_signals(
                    event_id, (signal,) if signal else (), min(1.0, sum(recent) / len(recent))
                )
                total += 1
                ts += rng.uniform(10, 90)
                tokens += rng.randint(500, 2_200)
            if peak >= 0.9 * size or rng.random() < 0.15:
                trigger = "auto" if peak >= 0.9 * size else "manual"
                store.conn.execute(
                    "INSERT INTO compactions (session_id, ts, trigger, context_tokens, model) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sid, ts, trigger, tokens, model),
                )
            store.update_session(sid, last_seen=ts, ended_at=ts)
        store.conn.execute("COMMIT")
    except BaseException:
        store.conn.execute("ROLLBACK")
        raise
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--home", required=True, help="a scratch CIGAR_HOME to write into")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    home = Path(args.home).expanduser().resolve()
    if home == (Path.home() / ".cigar").resolve():
        print("Refusing to write simulated data into the real ~/.cigar (D-027).")
        return 2
    with Store.open(home / "cigar.db") as store:
        for i, (model, window, knee, sessions) in enumerate(PROFILES):
            events = simulate(store, model, window, knee, sessions, seed=args.seed + i)
            print(f"{model} ({window} window): {sessions} sessions, {events} events, knee {knee}")
    print(f"Wrote {home / 'cigar.db'}. Try: CIGAR_HOME={home} python3 bin/cigar report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
