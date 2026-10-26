from __future__ import annotations

from pathlib import Path

import pytest

ENV_VARS = (
    "CIGAR_HOME",
    "CIGAR_MODE",
    "CIGAR_MIN_TOKENS",
    "CIGAR_KNEE_TOKENS",
    "CLAUDE_PROJECT_DIR",
    "CIGAR_REEXEC",
    "CIGAR_CONTEXT_WINDOW",
)


@pytest.fixture(autouse=True)
def cigar_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own ~/.cigar and a clean Cigar environment."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "cigar-home"
    monkeypatch.setenv("CIGAR_HOME", str(home))
    return home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    path = tmp_path / "proj"
    path.mkdir()
    return path
