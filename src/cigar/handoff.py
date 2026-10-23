"""Handoffs: validate, render, truncate for injection, save and load (FR-H1 to FR-H5).

`validate`, `render` and `for_injection` are pure. `save` and `load` do I/O.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cigar import defaults

HANDOFF_DIR = Path(".cigar") / "handoffs"
INJECTION_PREAMBLE = (
    "This session continues earlier work. The handoff written before the context reset follows."
)
LIST_FIELDS = ("done", "decisions", "next_steps", "open_questions", "gotchas")


class HandoffError(ValueError):
    pass


@dataclass(frozen=True)
class Handoff:
    goal: str
    status: str
    done: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    files: tuple[tuple[str, str], ...] = ()
    next_steps: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    gotchas: tuple[str, ...] = ()


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"`{key}` is required and must be a non-empty string")
    return value.strip()


def _items(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise HandoffError(f"`{key}` must be a list of strings")
    return tuple(v.strip() for v in value if v.strip())


def _split_note(path: str, note: str) -> tuple[str, str]:
    """Agents often write "path — note" in one string; keep the two apart."""
    if not note and " — " in path:
        path, note = (part.strip() for part in path.split(" — ", 1))
    return path, note


def _files(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    value = data.get("files")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise HandoffError("`files` must be a list of {path, note}")
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(_split_note(item.strip(), ""))
        elif isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip():
            note = item.get("note")
            out.append(
                _split_note(item["path"].strip(), note.strip() if isinstance(note, str) else "")
            )
        else:
            raise HandoffError("each entry of `files` needs a `path` string")
    return tuple(out)


def validate(data: Any) -> Handoff:
    if not isinstance(data, dict):
        raise HandoffError("the handoff must be an object")
    fields = {key: _items(data, key) for key in LIST_FIELDS}
    handoff = Handoff(
        goal=_text(data, "goal"), status=_text(data, "status"), files=_files(data), **fields
    )
    if not handoff.next_steps:
        raise HandoffError("`next_steps` needs at least one step (the immediate action first)")
    return handoff


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def render(handoff: Handoff, project_name: str, when: dt.datetime) -> str:
    files = (
        "\n".join(f"- `{path}` — {note}" if note else f"- `{path}`" for path, note in handoff.files)
        if handoff.files
        else "- (none)"
    )
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(handoff.next_steps, 1))
    return (
        f"# Cigar handoff · {project_name} · {when.isoformat(timespec='minutes')}\n"
        f"**Goal:** {handoff.goal}\n"
        f"**Status:** {handoff.status}\n\n"
        f"## Done\n{_bullets(handoff.done)}\n\n"
        f"## Decisions\n{_bullets(handoff.decisions)}\n\n"
        f"## Files (path — note)\n{files}\n\n"
        f"## Next steps\n{steps}\n\n"
        f"## Open questions\n{_bullets(handoff.open_questions)}\n\n"
        f"## Gotchas\n{_bullets(handoff.gotchas)}\n"
    )


def for_injection(
    markdown: str, rel_path: str, limit: int = defaults.HANDOFF_INJECT_MAX_CHARS
) -> str:
    """The text injected after a reset: under `limit` chars (FR-H5).

    A long handoff is cut to its goal, status and next steps, followed by the
    path to the full version.
    """
    full = f"{INJECTION_PREAMBLE}\n\n{markdown.strip()}"
    if len(full) <= limit:
        return full
    sections = markdown.strip().split("\n## ")
    head = sections[0]
    steps = next((s for s in sections[1:] if s.startswith("Next steps")), "")
    tail = f"\n\n(Cut to fit. The full handoff is at {rel_path}.)"
    body = f"{INJECTION_PREAMBLE}\n\n{head}\n\n## {steps}".rstrip()
    room = limit - len(tail)
    if len(body) > room:
        body = body[: max(0, room - 1)].rstrip() + "…"
    return body + tail


def _ensure_dir(project_dir: Path) -> Path:
    root = project_dir / ".cigar"
    target = project_dir / HANDOFF_DIR
    target.mkdir(parents=True, exist_ok=True)
    ignore = root / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return target


def save(
    project_dir: Path, markdown: str, session_id: str | None, when: dt.datetime
) -> tuple[Path, str]:
    """Write the handoff file. Returns (absolute path, path relative to the project)."""
    target = _ensure_dir(project_dir)
    stem = f"{when:%Y-%m-%dT%H%M}-{(session_id or 'nosession')[:4]}"
    path = target / f"{stem}.md"
    n = 2
    while path.exists():
        path = target / f"{stem}-{n}.md"
        n += 1
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(path)
    return path, path.relative_to(project_dir).as_posix()


def load(project_dir: Path, rel_path: str) -> str | None:
    path = (project_dir / rel_path).resolve()
    handoffs = (project_dir / HANDOFF_DIR).resolve()
    if handoffs not in path.parents:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
