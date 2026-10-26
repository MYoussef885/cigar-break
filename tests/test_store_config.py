from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from cigar import config, store
from cigar.signals import extract
from cigar.store import Store


def test_migrations_match_schema_version() -> None:
    numbers = [n for n, _ in store._migrations()]
    assert numbers == list(range(1, store.SCHEMA_VERSION + 1))


def test_open_migrates_once_with_wal(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    with Store.open(db) as s:
        assert s.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert s.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 2000
        assert s.get_meta("schema_version") == str(store.SCHEMA_VERSION)
    with Store.open(db) as s:
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == store.SCHEMA_VERSION


def test_concurrent_opens_migrate_safely(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Store.open(db) as s:
                s.touch_session("s", "p")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_project_hash_is_16_hex_of_absolute_path(tmp_path: Path) -> None:
    h = store.project_hash(str(tmp_path))
    assert len(h) == 16 and int(h, 16) >= 0
    assert store.project_hash(str(tmp_path / "x" / "..")) == h


def test_sessions_events_and_handoffs(tmp_path: Path) -> None:
    with Store.open(tmp_path / "c.db") as s:
        s.touch_session("s1", "p", model="m1", now=1.0)
        s.touch_session("s1", "p", model="m2", now=2.0)
        row = s.get_session("s1")
        assert (row["model_first"], row["model_last"], row["last_seen"]) == ("m1", "m2", 2.0)
        s.touch_session("s2", "p", now=3.0)
        assert s.latest_session("p")["id"] == "s2"

        e = extract("Read", {"file_path": "/a"})
        eid = s.insert_event("s1", e, False, 50_000, "m2")
        s.set_event_signals(eid, ("reread",), 0.5)
        s.insert_event("s1", e, True, None, None)
        events = s.recent_events("s1", 10)
        assert len(events) == 1 and events[0].signals == ("reread",)
        assert s.get_session("s1")["main_events"] == 1
        assert s.low_pressure_behaviors("m2", 60_000) == [0.5]

        first = s.add_handoff("p", "s1", ".cigar/handoffs/a.md", now=100.0)
        second = s.add_handoff("p", "s1", ".cigar/handoffs/b.md", now=200.0)
        assert s.pending_handoff("p", 3600, now=300.0)["id"] == second
        assert s.pending_handoff("p", 50, now=300.0) is None  # too old
        s.consume_handoff(second)
        assert s.pending_handoff("p", 3600, now=300.0) is None
        assert s.latest_handoff("p")["id"] == second != first


def test_no_raw_arguments_are_stored(tmp_path: Path) -> None:
    secret = "API_KEY=hunter2"
    with Store.open(tmp_path / "c.db") as s:
        s.touch_session("s", "p")
        s.insert_event("s", extract("Bash", {"command": f"echo {secret}"}), False, 1, "m")
        edit = {"file_path": "/a", "old_string": secret, "new_string": "x"}
        s.insert_event("s", extract("Edit", edit), False, 1, "m")
    raw = b"".join(p.read_bytes() for p in tmp_path.glob("c.db*"))
    assert raw
    assert b"hunter2" not in raw


def test_corrupt_db_raises_database_error(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    db.write_bytes(b"this is not a database" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        Store.open(db)


def test_config_precedence(cigar_home: Path) -> None:
    assert config.load().mode == "suggest"
    config.write_value(cigar_home, "mode", "observe")
    config.write_value(cigar_home, "min_tokens", 30_000)
    cfg = config.load()
    assert (cfg.mode, cfg.min_tokens, cfg.knee_tokens) == ("observe", 30_000, None)
    env = {"CIGAR_HOME": str(cigar_home), "CIGAR_MODE": "suggest", "CIGAR_MIN_TOKENS": "5000"}
    cfg = config.load(env | {"CIGAR_KNEE_TOKENS": "20000"})
    assert (cfg.mode, cfg.min_tokens, cfg.knee_tokens) == ("suggest", 5000, 20_000)
    assert config.load(env | {"CIGAR_MIN_TOKENS": "0"}).min_tokens == 0


def test_config_defaults_and_bad_mode(cigar_home: Path) -> None:
    cigar_home.mkdir(parents=True)
    (cigar_home / "config.toml").write_text(
        'mode = "nonsense"\ncooldown_events = 5\ncheck_patterns = ["foo"]\n'
    )
    cfg = config.load()
    assert (cfg.mode, cfg.cooldown_events, cfg.check_patterns) == ("suggest", 5, ("foo",))
    assert cfg.max_nudges == 3


def test_write_value_keeps_other_keys(cigar_home: Path) -> None:
    config.write_value(cigar_home, "min_tokens", 1)
    config.write_value(cigar_home, "check_patterns", ['a"b', "c"])
    config.write_value(cigar_home, "mode", "observe")
    cfg = config.load()
    assert (cfg.min_tokens, cfg.check_patterns, cfg.mode) == (1, ('a"b', "c"), "observe")


def test_schema_1_database_migrates_keeping_rows(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(store._migrations()[0][1] + "; PRAGMA user_version = 1;")
    conn.execute(
        "INSERT INTO sessions (id, project_hash, started_at, last_seen) VALUES ('s', 'p', 1, 1)"
    )
    conn.commit()
    conn.close()
    with Store.open(db) as s:
        row = s.get_session("s")
        assert row is not None and row["context_window"] is None
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == 2


@pytest.mark.parametrize(
    ("env_value", "toml", "expected"),
    [("1m", None, "1m"), ("200K", None, "200k"), ("", "1m", "1m"), ("huge", None, None)],
)
def test_context_window_config(
    env_value: str, toml: str | None, expected: str | None, cigar_home: Path
) -> None:
    if toml:
        config.write_value(cigar_home, "context_window", toml)
    cfg = config.load({"CIGAR_HOME": str(cigar_home), "CIGAR_CONTEXT_WINDOW": env_value})
    assert cfg.context_window == expected
