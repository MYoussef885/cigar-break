from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from cigar import handoff

WHEN = dt.datetime(2026, 10, 24, 1, 30, tzinfo=dt.UTC)

FULL = {
    "goal": "Ship the transcript tail reader",
    "status": "Reader works; lag test failing",
    "done": ["Wrote read_tail", "Added unit tests"],
    "decisions": ["Read in 64 KB blocks"],
    "files": [
        {"path": "src/cigar/transcript.py", "note": "the reader"},
        "tests/test_transcript.py",
    ],
    "next_steps": ["Fix the partial-line case", "Run the perf test"],
    "open_questions": ["Is 4 MB enough?"],
    "gotchas": ["The format is internal to Claude Code"],
}


def test_validate_and_render() -> None:
    h = handoff.validate(FULL)
    md = handoff.render(h, "cigar-break", WHEN)
    assert md.startswith("# Cigar handoff · cigar-break · 2026-10-24T01:30+00:00\n")
    assert "**Goal:** Ship the transcript tail reader" in md
    assert "## Next steps\n1. Fix the partial-line case\n2. Run the perf test" in md
    assert "- `src/cigar/transcript.py` — the reader" in md
    assert "- `tests/test_transcript.py`\n" in md
    for heading in ("Done", "Decisions", "Files (path — note)", "Open questions", "Gotchas"):
        assert f"## {heading}\n" in md


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"goal": "g"},
        {"goal": "g", "status": "s"},  # no next steps
        {"goal": " ", "status": "s", "next_steps": ["a"]},
        {"goal": "g", "status": "s", "next_steps": "a", "done": [1]},
        {"goal": "g", "status": "s", "next_steps": ["a"], "files": [{"note": "x"}]},
        [],
    ],
)
def test_validate_rejects(bad: object) -> None:
    with pytest.raises(handoff.HandoffError):
        handoff.validate(bad)


def test_injection_short_handoff_is_whole() -> None:
    md = handoff.render(handoff.validate(FULL), "p", WHEN)
    text = handoff.for_injection(md, ".cigar/handoffs/x.md")
    assert text.startswith(handoff.INJECTION_PREAMBLE)
    assert md.strip() in text


def test_injection_long_handoff_is_cut_to_goal_status_next_steps() -> None:
    data = dict(FULL, done=["d" * 500] * 40)
    md = handoff.render(handoff.validate(data), "p", WHEN)
    assert len(md) > 8000
    text = handoff.for_injection(md, ".cigar/handoffs/x.md")
    assert len(text) <= 8000
    assert "**Goal:**" in text and "**Status:**" in text and "## Next steps" in text
    assert "## Done" not in text
    assert text.endswith("(Cut to fit. The full handoff is at .cigar/handoffs/x.md.)")


def test_injection_hard_cut_when_even_short_form_is_too_long() -> None:
    data = dict(FULL, goal="g" * 20_000)
    md = handoff.render(handoff.validate(data), "p", WHEN)
    text = handoff.for_injection(md, ".cigar/handoffs/x.md")
    assert len(text) <= 8000
    assert text.endswith(".cigar/handoffs/x.md.)")


def test_save_creates_self_ignoring_folder(project: Path) -> None:
    md = handoff.render(handoff.validate(FULL), project.name, WHEN)
    path, rel = handoff.save(project, md, "ab12cd34", WHEN)
    assert rel == ".cigar/handoffs/2026-10-24T0130-ab12.md"
    assert path.read_text(encoding="utf-8") == md
    assert (project / ".cigar" / ".gitignore").read_text() == "*\n"
    assert not (project / ".gitignore").exists()
    _, rel2 = handoff.save(project, md, "ab12cd34", WHEN)
    assert rel2 == ".cigar/handoffs/2026-10-24T0130-ab12-2.md"
    assert handoff.load(project, rel) == md


def test_load_refuses_paths_outside_handoffs(project: Path) -> None:
    (project / "secret.txt").write_text("x")
    assert handoff.load(project, "secret.txt") is None
    assert handoff.load(project, ".cigar/handoffs/../../secret.txt") is None
    assert handoff.load(project, ".cigar/handoffs/missing.md") is None


def test_files_split_path_and_note_written_together() -> None:
    # Seen in the Session 1 end-to-end run: the note was packed into the path.
    h = handoff.validate(
        dict(FULL, files=["/p/calc.py — add and mul", {"path": "/p/t.py — the tests"}])
    )
    assert h.files == (("/p/calc.py", "add and mul"), ("/p/t.py", "the tests"))
