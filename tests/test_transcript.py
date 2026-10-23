from __future__ import annotations

import json
from pathlib import Path

from helpers import assistant, noise, tool_result, write_jsonl

from cigar import transcript


def test_reads_latest_main_assistant_usage(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [
            assistant(30_000, "claude-sonnet-5-5"),
            tool_result("a"),
            assistant(45_000, "claude-opus-5-5"),
            *noise(1),
            tool_result("b"),
        ],
    )
    reading = transcript.read_tail(path)
    assert reading == transcript.TailReading(45_000, "claude-opus-5-5")


def test_formula_sums_three_input_fields(tmp_path: Path) -> None:
    entry = assistant(0)
    entry["message"]["usage"] = {
        "input_tokens": 2,
        "cache_creation_input_tokens": 10_765,
        "cache_read_input_tokens": 22_062,
        "output_tokens": 116,
    }
    path = write_jsonl(tmp_path / "t.jsonl", [entry])
    assert transcript.read_tail(path).context_tokens == 32_829


def test_skips_sidechain_and_synthetic(tmp_path: Path) -> None:
    synthetic = assistant(1, "<synthetic>")
    path = write_jsonl(
        tmp_path / "t.jsonl",
        [assistant(50_000), assistant(90_000, sidechain=True), synthetic],
    )
    assert transcript.read_tail(path).context_tokens == 50_000


def test_missing_usage_returns_none(tmp_path: Path) -> None:
    entry = assistant(10)
    del entry["message"]["usage"]
    path = write_jsonl(tmp_path / "t.jsonl", [entry, *noise(1)])
    assert transcript.read_tail(path) is None


def test_lagging_transcript_with_partial_last_line(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "t.jsonl", [assistant(60_000)])
    with path.open("a") as f:
        f.write(json.dumps(assistant(70_000))[:50])  # being written right now
    assert transcript.read_tail(path).context_tokens == 60_000


def test_entry_spanning_block_boundary(tmp_path: Path) -> None:
    big = assistant(80_000, text="x" * 200_000)
    path = write_jsonl(tmp_path / "t.jsonl", [assistant(10_000), big, *noise(1)])
    assert transcript.read_tail(path, block=4096).context_tokens == 80_000


def test_scan_limit(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "t.jsonl", [assistant(10_000)] + noise(1) * 3000)
    assert transcript.read_tail(path, max_bytes=64 * 1024) is None
    assert transcript.read_tail(path).context_tokens == 10_000


def test_bad_inputs(tmp_path: Path) -> None:
    assert transcript.read_tail(None) is None
    assert transcript.read_tail(tmp_path / "missing.jsonl") is None
    garbage = tmp_path / "g.jsonl"
    garbage.write_bytes(b'\xff\xfe{"usage" "assistant" not json\n\x00\x01')
    assert transcript.read_tail(garbage) is None
    empty = tmp_path / "e.jsonl"
    empty.write_text("")
    assert transcript.read_tail(empty) is None
