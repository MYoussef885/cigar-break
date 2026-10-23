from __future__ import annotations

import re
from pathlib import Path

import pytest
from helpers import ROOT

from cigar import cli, config

SKILLS = ROOT / "skills"


def test_mode_show_set_and_refuse_auto(
    cigar_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["mode"]) == 0
    assert capsys.readouterr().out.startswith("Mode: suggest.")
    assert cli.main(["mode", "observe"]) == 0
    assert config.load().mode == "observe"
    assert cli.main(["mode", ""]) == 0  # the skill passes "$ARGUMENTS", maybe empty
    assert capsys.readouterr().out.splitlines()[-1].startswith("Mode: observe.")
    assert cli.main(["mode", "auto"]) == 1
    assert "Auto mode is unavailable" in capsys.readouterr().out
    assert config.load().mode == "observe"
    assert cli.main(["mode", "turbo"]) == 2


def test_status_without_sessions(cigar_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["status"]) == 0
    assert "no session recorded yet" in capsys.readouterr().out
    assert cli.main(["status", "--json"]) == 0
    assert '"mode": "suggest"' in capsys.readouterr().out


@pytest.mark.parametrize("name", ["status", "break", "mode"])
def test_skills_are_user_only_and_short(name: str) -> None:
    text = (SKILLS / name / "SKILL.md").read_text()
    front = text.split("---")[1]
    assert f"name: {name}" in front
    assert "disable-model-invocation: true" in front
    description = re.search(r"^description: (.+)$", front, re.M)
    assert description and len(description.group(1)) <= 100


@pytest.mark.parametrize("name", ["status", "mode"])
def test_skill_shell_lines_never_abort(name: str) -> None:
    # A non-zero exit aborts a skill's inline shell and hides the output (D-014).
    lines = [
        ln for ln in (SKILLS / name / "SKILL.md").read_text().splitlines() if ln.startswith("!")
    ]
    assert lines and all(ln.endswith("2>&1 || true`") for ln in lines)
