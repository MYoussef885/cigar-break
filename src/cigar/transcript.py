"""Transcript tail reader (architecture §5).

Reads the session JSONL backwards in blocks until it finds the latest main-agent
assistant entry with `message.usage`. The format is internal to Claude Code
(D-014), so every field access is defensive and a miss returns None.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from cigar import defaults

USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


@dataclass(frozen=True)
class TailReading:
    context_tokens: int
    model: str | None


def parse_entry(line: bytes) -> TailReading | None:
    """A reading from one JSONL line, if it is a usable assistant entry."""
    if b'"usage"' not in line or b'"assistant"' not in line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return None
    if entry.get("isSidechain") is True:
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    model = message.get("model")
    if not isinstance(usage, dict) or model == "<synthetic>":
        return None
    tokens = 0
    for name in USAGE_FIELDS:
        value = usage.get(name)
        if isinstance(value, int):
            tokens += value
    if tokens <= 0:
        return None
    return TailReading(tokens, model if isinstance(model, str) else None)


def read_tail(
    path: str | os.PathLike[str] | None,
    block: int = defaults.TAIL_BLOCK_BYTES,
    max_bytes: int = defaults.TAIL_MAX_BYTES,
) -> TailReading | None:
    """The latest context size and model in the transcript, or None."""
    if not path:
        return None
    try:
        f = open(path, "rb")  # noqa: SIM115 - closed below
    except OSError:
        return None
    with f:
        end = f.seek(0, os.SEEK_END)
        pos = end
        carry = b""
        scanned = 0
        while pos > 0 and scanned < max_bytes:
            size = min(block, pos)
            pos -= size
            f.seek(pos)
            chunk = f.read(size) + carry
            scanned += size
            lines = chunk.split(b"\n")
            # The first piece may be a partial line unless we're at the file start.
            carry = lines.pop(0) if pos > 0 else b""
            for line in reversed(lines):
                reading = parse_entry(line)
                if reading:
                    return reading
    return None
