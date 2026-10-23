"""Configuration: ~/.cigar/config.toml, overridden by environment variables.

Precedence (highest first): environment, config.toml, defaults.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from cigar import defaults

MODES = ("suggest", "observe", "auto")


def cigar_home() -> Path:
    return Path(os.environ.get("CIGAR_HOME") or "~/.cigar").expanduser()


@dataclass(frozen=True)
class Config:
    home: Path
    mode: str = "suggest"
    min_tokens: int = defaults.MIN_TOKENS
    knee_tokens: int | None = None
    cooldown_events: int = defaults.COOLDOWN_EVENTS
    max_nudges: int = defaults.MAX_NUDGES
    check_patterns: tuple[str, ...] = field(default=defaults.CHECK_PATTERNS)

    @property
    def db_path(self) -> Path:
        return self.home / "cigar.db"

    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    @property
    def log_dir(self) -> Path:
        return self.home / "logs"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import tomllib

    with path.open("rb") as f:
        return tomllib.load(f)


def _int(*values: Any) -> int | None:
    """The first value that is set, as an int."""
    for value in values:
        if value is not None and value != "":
            return int(value)
    return None


def load(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ) if env is None else env
    home = Path(env.get("CIGAR_HOME") or "~/.cigar").expanduser()
    cfg = Config(home=home)
    data = _read_toml(cfg.config_path)

    mode = env.get("CIGAR_MODE") or data.get("mode") or cfg.mode
    if mode not in MODES:
        mode = "suggest"
    min_tokens = _int(env.get("CIGAR_MIN_TOKENS"), data.get("min_tokens"))
    knee = _int(env.get("CIGAR_KNEE_TOKENS"), data.get("knee_tokens"))
    cooldown = _int(data.get("cooldown_events"))
    max_nudges = _int(data.get("max_nudges"))
    patterns = data.get("check_patterns")

    return replace(
        cfg,
        mode=mode,
        min_tokens=min_tokens if min_tokens is not None else cfg.min_tokens,
        knee_tokens=knee,
        cooldown_events=cooldown if cooldown is not None else cfg.cooldown_events,
        max_nudges=max_nudges if max_nudges is not None else cfg.max_nudges,
        check_patterns=tuple(patterns) if isinstance(patterns, list) else cfg.check_patterns,
    )


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def write_value(home: Path, key: str, value: Any) -> Path:
    """Set one top-level key in config.toml, keeping the other keys."""
    path = home / "config.toml"
    data = _read_toml(path)
    data[key] = value
    home.mkdir(parents=True, exist_ok=True)
    lines = [f"{k} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
