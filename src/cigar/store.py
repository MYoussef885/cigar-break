"""SQLite store at ~/.cigar/cigar.db (architecture §8).

WAL mode, a 2 s busy timeout (hooks run concurrently) and numbered SQL
migrations applied at open. Open it once per hook run.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from cigar import __version__
from cigar.signals import Event

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 2000


def project_hash(project_dir: str) -> str:
    """First 16 hex chars of the SHA-256 of the absolute project path."""
    absolute = str(Path(project_dir).expanduser().resolve())
    return hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:16]


def _migrations() -> list[tuple[int, str]]:
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        found.append((int(path.name[:4]), path.read_text(encoding="utf-8")))
    return found


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @classmethod
    def open(cls, db_path: Path) -> Store:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        store = cls(conn)
        store.migrate()
        return store

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- schema ------------------------------------------------------------
    def migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-check under the write lock: another hook may have migrated.
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for number, sql in _migrations():
                if number > version:
                    for statement in sql.split(";"):
                        if statement.strip():
                            self.conn.execute(statement)
                    self.conn.execute(f"PRAGMA user_version = {number}")
            self.set_meta("schema_version", str(SCHEMA_VERSION))
            self.set_meta("cigar_version", __version__)
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # --- sessions ------------------------------------------------------------
    def touch_session(
        self,
        session_id: str,
        project: str,
        model: str | None = None,
        source: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Create the session row if needed, refresh last_seen and model, return it."""
        now = time.time() if now is None else now
        self.conn.execute(
            "INSERT INTO sessions (id, project_hash, model_first, model_last, started_at, "
            "last_seen, source) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET last_seen = excluded.last_seen, "
            "model_last = COALESCE(excluded.model_last, model_last), "
            "model_first = COALESCE(model_first, excluded.model_last)",
            (session_id, project, model, model, now, now, source),
        )
        return self.get_session(session_id) or {}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def latest_session(self, project: str | None = None) -> dict[str, Any] | None:
        if project:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE project_hash = ? ORDER BY last_seen DESC LIMIT 1",
                (project,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM sessions ORDER BY last_seen DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self.conn.execute(
            f"UPDATE sessions SET {assignments} WHERE id = ?", (*fields.values(), session_id)
        )

    def record_nudge(self, session_id: str, seq: int) -> None:
        self.conn.execute(
            "UPDATE sessions SET nudges = nudges + 1, last_nudge_seq = ? WHERE id = ?",
            (seq, session_id),
        )

    def record_break(self, session_id: str, now: float | None = None) -> None:
        """A break resets the nudge counter and cooldown (architecture §6)."""
        self.conn.execute(
            "UPDATE sessions SET breaks = breaks + 1, nudges = 0, last_nudge_seq = NULL, "
            "break_at = ?, reminded = 0 WHERE id = ?",
            (time.time() if now is None else now, session_id),
        )

    # --- events --------------------------------------------------------------
    def insert_event(
        self,
        session_id: str,
        event: Event,
        is_subagent: bool,
        context_tokens: int | None,
        model: str | None,
        now: float | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO events (session_id, ts, tool, kind, args_hash, path, edit_old_hash, "
            "edit_new_hash, failed, exit_code, is_check, is_subagent, context_tokens, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                time.time() if now is None else now,
                event.tool,
                event.kind,
                event.args_hash,
                event.path,
                event.edit_old_hash,
                event.edit_new_hash,
                int(event.failed),
                event.exit_code,
                int(event.is_check),
                int(is_subagent),
                context_tokens,
                model,
            ),
        )
        if not is_subagent:
            self.conn.execute(
                "UPDATE sessions SET main_events = main_events + 1 WHERE id = ?", (session_id,)
            )
        return int(cur.lastrowid or 0)

    def set_event_signals(self, event_id: int, signals: tuple[str, ...], behavior: float) -> None:
        self.conn.execute(
            "UPDATE events SET signals_json = ?, behavior = ? WHERE id = ?",
            (json.dumps(list(signals)), behavior, event_id),
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> Event:
        raw = row["signals_json"]
        return Event(
            id=row["id"],
            tool=row["tool"],
            kind=row["kind"],
            args_hash=row["args_hash"],
            path=row["path"],
            edit_old_hash=row["edit_old_hash"],
            edit_new_hash=row["edit_new_hash"],
            failed=bool(row["failed"]),
            exit_code=row["exit_code"],
            is_check=bool(row["is_check"]),
            signals=tuple(json.loads(raw)) if raw else (),
        )

    def recent_events(
        self, session_id: str, limit: int, before_id: int | None = None
    ) -> list[Event]:
        """The session's latest main-agent events, oldest first."""
        rows = self.conn.execute(
            "SELECT * FROM events WHERE session_id = ? AND is_subagent = 0 AND id < ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, before_id if before_id is not None else 2**62, limit),
        ).fetchall()
        return [self._event(r) for r in reversed(rows)]

    def path_events(
        self, session_id: str, path: str, before_id: int, limit: int = 50
    ) -> list[Event]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE session_id = ? AND path = ? AND is_subagent = 0 "
            "AND id < ? ORDER BY id DESC LIMIT ?",
            (session_id, path, before_id, limit),
        ).fetchall()
        return [self._event(r) for r in reversed(rows)]

    def low_pressure_behaviors(
        self, model: str, below_tokens: int, limit: int = 5000
    ) -> list[float]:
        rows = self.conn.execute(
            "SELECT behavior FROM events WHERE model = ? AND is_subagent = 0 "
            "AND context_tokens < ? AND behavior IS NOT NULL ORDER BY id DESC LIMIT ?",
            (model, below_tokens, limit),
        ).fetchall()
        return [float(r[0]) for r in rows]

    # --- compactions ----------------------------------------------------------
    def record_compaction(
        self, session_id: str, trigger: str | None, context_tokens: int | None, model: str | None
    ) -> None:
        self.conn.execute(
            "INSERT INTO compactions (session_id, ts, trigger, context_tokens, model) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, time.time(), trigger, context_tokens, model),
        )

    # --- handoffs -------------------------------------------------------------
    def add_handoff(
        self, project: str, session_id: str | None, rel_path: str, now: float | None = None
    ) -> int:
        now = time.time() if now is None else now
        # Only the newest handoff is pending; older unconsumed ones are superseded.
        self.conn.execute(
            "UPDATE handoffs SET consumed_at = ? WHERE project_hash = ? AND consumed_at IS NULL",
            (now, project),
        )
        cur = self.conn.execute(
            "INSERT INTO handoffs (project_hash, session_id, path, created_at) VALUES (?, ?, ?, ?)",
            (project, session_id, rel_path, now),
        )
        return int(cur.lastrowid or 0)

    def pending_handoff(
        self, project: str, max_age: float, now: float | None = None
    ) -> dict | None:
        now = time.time() if now is None else now
        row = self.conn.execute(
            "SELECT * FROM handoffs WHERE project_hash = ? AND consumed_at IS NULL "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
            (project, now - max_age),
        ).fetchone()
        return dict(row) if row else None

    def session_handoff(self, project: str, since: float) -> dict | None:
        """The pending handoff saved for the project since `since` (the session start)."""
        row = self.conn.execute(
            "SELECT * FROM handoffs WHERE project_hash = ? AND consumed_at IS NULL "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
            (project, since),
        ).fetchone()
        return dict(row) if row else None

    def latest_handoff(self, project: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM handoffs WHERE project_hash = ? ORDER BY created_at DESC LIMIT 1",
            (project,),
        ).fetchone()
        return dict(row) if row else None

    def consume_handoff(self, handoff_id: int) -> None:
        self.conn.execute(
            "UPDATE handoffs SET consumed_at = ? WHERE id = ?", (time.time(), handoff_id)
        )
