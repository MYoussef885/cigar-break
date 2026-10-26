"""NFR-2: a tool-call hook takes p95 < 150 ms end to end, on a 5 MB transcript.

Each run is a fresh process started exactly as hooks.json starts it
(`python3 -I -S bin/cigar-hook post_tool_use`), including the re-exec when
python3 is older than 3.11. Run with -s to see the numbers.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import time
from pathlib import Path

import pytest
from helpers import BIN, assistant, hook_python3, noise, tool_result

from cigar import config
from cigar.signals import extract
from cigar.store import Store

PYTHON3 = hook_python3()
RUNS = 200
TARGET_MS = 150.0
TRANSCRIPT_BYTES = 5 * 1024 * 1024


def build_transcript(path: Path) -> int:
    """About 5 MB in the observed layout; the newest usage sits near the end."""
    with path.open("w") as f:
        i = 0
        while f.tell() < TRANSCRIPT_BYTES:
            tool_id = f"toolu_{i:05d}"
            call = (tool_id, "Read", {"file_path": f"/w/src/f{i}.py"})
            f.write(json.dumps(assistant(30_000 + i * 20, tool_uses=[call])) + "\n")
            f.write(json.dumps(tool_result(tool_id, content="x" * 2_000)) + "\n")
            for entry in noise(i):
                f.write(json.dumps(entry) + "\n")
            i += 1
        f.write(json.dumps(assistant(152_000)) + "\n")
        for entry in noise(i):
            f.write(json.dumps(entry) + "\n")
    return path.stat().st_size


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[94]


@pytest.mark.perf
def test_hook_p95_under_150ms(cigar_home: Path, project: Path, tmp_path: Path) -> None:
    transcript = tmp_path / "big.jsonl"
    size = build_transcript(transcript)
    assert size >= TRANSCRIPT_BYTES

    with Store.open(config.load().db_path) as s:  # a session with history
        s.touch_session("perf", "p")
        for i in range(300):
            s.insert_event("perf", extract("Read", {"file_path": f"/w/{i % 40}"}), False, 1, "m")

    env = {k: v for k, v in os.environ.items() if not k.startswith(("CIGAR_", "CLAUDE_"))}
    env["CIGAR_HOME"] = str(cigar_home)
    wall: list[float] = []
    for i in range(RUNS):
        payload = {
            "session_id": "perf",
            "cwd": str(project),
            "transcript_path": str(transcript),
            "tool_name": ["Read", "Edit", "Bash"][i % 3],
            "tool_input": {"file_path": f"/w/{i % 40}", "command": f"ls {i}"},
            "tool_response": {},
        }
        started = time.perf_counter()
        result = subprocess.run(
            [PYTHON3, "-I", "-S", str(BIN / "cigar-hook"), "post_tool_use"],
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=env,
            timeout=30,
        )
        wall.append((time.perf_counter() - started) * 1000)
        assert result.returncode == 0

    logged = "".join(p.read_text() for p in (cigar_home / "logs").glob("*.log"))
    inner = [float(m) for m in re.findall(r"hook post_tool_use ok ms=([\d.]+)", logged)]
    assert len(inner) == RUNS
    version = subprocess.run(
        [PYTHON3, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(
        f"\nhook perf: {RUNS} runs, transcript {size / 1024 / 1024:.1f} MB, "
        f"python3 on PATH = {PYTHON3} ({version})\n"
        f"  end to end (process start to exit): p50 {statistics.median(wall):.1f} ms, "
        f"p95 {p95(wall):.1f} ms, max {max(wall):.1f} ms\n"
        f"  inside the hook (parse, store, transcript, score): "
        f"p50 {statistics.median(inner):.1f} ms, "
        f"p95 {p95(inner):.1f} ms"
    )
    if os.environ.get("CI"):
        # Shared CI runners are noisy (p95 193 ms with p50 48 ms seen); NFR-2 is
        # measured on a developer machine, so CI only prints the numbers (D-030).
        return
    assert p95(wall) < TARGET_MS
