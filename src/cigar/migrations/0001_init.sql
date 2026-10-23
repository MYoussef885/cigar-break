-- Cigar store, schema 1 (architecture §8, columns added in D-019).
-- No prompts, assistant text, file contents or raw tool arguments are stored.

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    project_hash    TEXT NOT NULL,
    harness         TEXT NOT NULL DEFAULT 'claude-code',
    model_first     TEXT,
    model_last      TEXT,
    started_at      REAL NOT NULL,
    ended_at        REAL,
    last_seen       REAL NOT NULL,
    source          TEXT,
    context_tokens  INTEGER,
    main_events     INTEGER NOT NULL DEFAULT 0,
    nudges          INTEGER NOT NULL DEFAULT 0,
    last_nudge_seq  INTEGER,
    breaks          INTEGER NOT NULL DEFAULT 0,
    break_at        REAL,
    reminded        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX sessions_project ON sessions (project_hash, last_seen);

CREATE TABLE events (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL,
    ts              REAL NOT NULL,
    tool            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    args_hash       TEXT,
    path            TEXT,
    edit_old_hash   TEXT,
    edit_new_hash   TEXT,
    failed          INTEGER NOT NULL DEFAULT 0,
    exit_code       INTEGER,
    is_check        INTEGER NOT NULL DEFAULT 0,
    is_subagent     INTEGER NOT NULL DEFAULT 0,
    context_tokens  INTEGER,
    model           TEXT,
    signals_json    TEXT,
    behavior        REAL
);
CREATE INDEX events_session ON events (session_id, is_subagent, id);
CREATE INDEX events_path ON events (session_id, path, id);
CREATE INDEX events_model ON events (model, is_subagent, context_tokens);

CREATE TABLE compactions (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL,
    ts              REAL NOT NULL,
    trigger         TEXT,
    context_tokens  INTEGER,
    model           TEXT
);

-- path is relative to the project (".cigar/handoffs/<name>.md"), never absolute.
CREATE TABLE handoffs (
    id              INTEGER PRIMARY KEY,
    project_hash    TEXT NOT NULL,
    session_id      TEXT,
    path            TEXT NOT NULL,
    created_at      REAL NOT NULL,
    consumed_at     REAL
);
CREATE INDEX handoffs_project ON handoffs (project_hash, created_at);

CREATE TABLE meta (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
