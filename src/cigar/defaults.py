"""Tuning constants. This is the only module where tuning numbers live.

Every value here is a starting point. The learned knee (Session 2) replaces
the default knees, and config.toml or environment variables can override the
rest (architecture §12). The reasoning for the default knees is in D-017.
"""

from __future__ import annotations

import re

# --- Signals (architecture §6) ---------------------------------------------
WINDOW_EVENTS = 20
# Rules (a) and (c) judge behavior only over at least this many events (D-020).
MIN_WINDOW_EVENTS = 10
UNDO_LOOKBACK_EVENTS = 50

WEIGHTS: dict[str, float] = {
    "failure": 1.0,
    "repeat": 0.8,
    "reread": 0.5,
    "undo": 1.0,
    "check_fail": 0.7,
}

READ_TOOLS = frozenset({"Read", "NotebookRead"})
EDIT_TOOLS = frozenset({"Edit", "MultiEdit", "Write", "NotebookEdit"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

# Shell commands that count as a test, build, lint or type check.
CHECK_PATTERNS: tuple[str, ...] = (
    r"\b(pytest|py\.test|tox|nox|unittest)\b",
    r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?(test|build|lint|typecheck|type-check|check)\b",
    r"\b(jest|vitest|mocha|playwright\s+test|cypress\s+run)\b",
    r"\b(tsc|eslint|biome|prettier\s+--check)\b",
    r"\b(ruff|flake8|pylint|mypy|pyright|black\s+--check)\b",
    r"\bcargo\s+(test|build|check|clippy)\b",
    r"\bgo\s+(test|build|vet)\b|\bgolangci-lint\b",
    r"\b(make|ninja|cmake\s+--build|bazel\s+(build|test)|gradle\w*|mvn)\b",
    r"\b(rspec|rubocop|phpunit|swift\s+(build|test)|dotnet\s+(build|test))\b",
)

# --- Score and nudge policy (architecture §6) -------------------------------
DEFAULT_BASELINE = 0.08
BASELINE_MIN_EVENTS = 200
BASELINE_KNEE_FRACTION = 0.4
BASELINE_CACHE_SECONDS = 3600

BEHAVIOR_MARGIN = 0.10  # rule (a): behavior >= baseline + margin, past the knee
PRESSURE_KNEE = 1.0  # rule (a)
PRESSURE_HARD = 1.3  # rule (b): well past the knee, whatever the behavior
DISTRESS_BEHAVIOR = 0.45  # rule (c)
DISTRESS_PRESSURE = 0.6  # rule (c)
FATIGUE_PRESSURE_CAP = 1.5

MIN_TOKENS = 40_000
COOLDOWN_EVENTS = 25
MAX_NUDGES = 3

# --- Handoffs ---------------------------------------------------------------
HANDOFF_INJECT_MAX_CHARS = 8_000
HANDOFF_MAX_AGE_SECONDS = 24 * 3600

# --- Transcript tail reading --------------------------------------------------
TAIL_BLOCK_BYTES = 64 * 1024
TAIL_MAX_BYTES = 4 * 1024 * 1024

# --- Knees (D-017) -------------------------------------------------------------
STANDARD_WINDOW = 200_000
EXTENDED_WINDOW = 1_000_000

# (pattern on the model ID, knee for a 200k window, knee for a 1M window)
KNEES: tuple[tuple[str, int, int], ...] = (
    (r"opus", 120_000, 160_000),
    (r"sonnet", 100_000, 140_000),
    (r"haiku", 70_000, 70_000),
)
FALLBACK_KNEE_CAP = 120_000
FALLBACK_KNEE_FRACTION = 0.5

# A model ID marked like this runs with a 1M window. Claude Code does not mark
# transcript model IDs (D-014), so seeing more tokens than the standard window
# also counts as evidence of an extended window.
EXTENDED_MARKERS = re.compile(r"\[1m\]|-1m\b|context-1m", re.IGNORECASE)

LOG_RETENTION_DAYS = 7
