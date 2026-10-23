"""Generate the synthetic replay transcripts in tests/fixtures/transcripts/.

Run: uv run python tests/fixtures/make_transcripts.py
Each scenario is deterministic and has a known expected outcome (tests/test_replay.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers import assistant, noise, tool_result, write_jsonl  # noqa: E402

OUT = Path(__file__).with_name("transcripts")
P = "/work/proj/src"


def call(tokens: int, model: str, i: int, name: str, tool_input: dict[str, Any], **res: Any):
    tool_id = f"toolu_{i:04d}"
    yield assistant(tokens, model, [(tool_id, name, tool_input)])
    yield tool_result(tool_id, **res)
    yield from noise(i)


def healthy_call(tokens: int, model: str, i: int):
    kind = i % 3
    if kind == 0:
        yield from call(tokens, model, i, "Read", {"file_path": f"{P}/mod{i}.py"})
    elif kind == 1:
        edit = {"file_path": f"{P}/mod{i - 1}.py", "old_string": f"a{i}", "new_string": f"b{i}"}
        yield from call(tokens, model, i, "Edit", edit)
    else:
        yield from call(tokens, model, i, "Bash", {"command": f"ls dir{i}", "description": "List"})


def degraded_call(tokens: int, model: str, i: int):
    kind = i % 5
    if kind == 0:
        yield from call(
            tokens, model, i, "Bash", {"command": "uv run pytest -q", "description": "Run tests"},
            content="Exit code 1\n3 failed", is_error=True,
        )  # fmt: skip
    elif kind == 1:
        yield from call(tokens, model, i, "Read", {"file_path": f"{P}/core.py"})
    elif kind == 2:
        edit = {"file_path": f"{P}/core.py", "old_string": "x = 1", "new_string": "x = 2"}
        yield from call(tokens, model, i, "Edit", edit)
    elif kind == 3:
        edit = {"file_path": f"{P}/core.py", "old_string": "x = 2", "new_string": "x = 1"}
        yield from call(tokens, model, i, "Edit", edit)
    else:
        yield from call(tokens, model, i, "Grep", {"pattern": "def run", "path": P})


def degrading():
    model = "claude-sonnet-5-5"
    for i in range(1, 141):
        tokens = 30_000 + int((i - 1) * 130_000 / 139)
        yield from (healthy_call if i <= 80 else degraded_call)(tokens, model, i)


def healthy():
    model = "claude-opus-5-5"
    for i in range(1, 121):
        yield from healthy_call(30_000 + int((i - 1) * 120_000 / 119), model, i)


def early_struggle():
    model = "claude-sonnet-5-5"
    for i in range(1, 41):
        tokens = 10_000 + int((i - 1) * 28_000 / 39)
        yield from call(
            tokens, model, i, "Bash", {"command": "npm test", "description": "Run tests"},
            content="Exit code 1\nFAIL", is_error=True,
        )  # fmt: skip


def distress():
    model = "claude-opus-5-5"
    for i in range(1, 31):
        tokens = 73_000 + i * 200
        yield from degraded_call(tokens, model, i)


SCENARIOS = {
    "degrading": degrading,
    "healthy": healthy,
    "early_struggle": early_struggle,
    "distress": distress,
}

if __name__ == "__main__":
    for name, scenario in SCENARIOS.items():
        path = write_jsonl(OUT / f"{name}.jsonl", scenario())
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
