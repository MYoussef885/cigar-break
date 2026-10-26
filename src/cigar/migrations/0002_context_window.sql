-- Schema 2 (D-026): the context window per session, "200k" or "1m".
-- Once a session is seen past 200k tokens it stays "1m".
ALTER TABLE sessions ADD COLUMN context_window TEXT
