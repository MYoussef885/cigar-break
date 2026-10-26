# CLAUDE.md: Cigar

You are the engineering agent for Cigar. Planning and review happen in Claude Chat. You implement one roadmap session at a time.

## What this is
Cigar is an open-source Claude Code plugin and MCP server that lets coding agents take a "cigar break":
1. It detects when a session is degrading as the context fills up, using free signals: failed tool calls, loops, re-reads, undone edits and failed checks.
2. It gets the agent to write a structured handoff.
3. It resets the context and restores the handoff.
4. It learns, per model, the context size where the developer's sessions start to slip, and can share that curve if the developer opts in.

The audience is developers who will install it on their own machines. **Trust is the product:** it must never break a session, never leak data, and never nag without evidence.

## Read first, every session
1. `roadmap.md`: find the current session and do only that session.
2. `SRS.md`: requirements (FR-*, DR-*, NFR-*), and the end-to-end check in §7.
3. `architecture.md`: layout, hooks, the scoring rules, store, MCP tools and tests.
4. `decisions.md`: settled choices. Don't relitigate them. If one blocks you, stop and report.

## Hard rules
- **One session at a time.** Never start the next session. End with the session report in the format at the bottom of `roadmap.md`.
- **Fail open** (NFR-1): every hook path is wrapped. Any exception exits 0 with no stdout and is logged to `~/.cigar/logs/`. Never exit 2 from a hook. Never block a tool call, prompt or compaction.
- **No runtime dependencies** (D-004): the standard library only, under `src/cigar/`. Dev dependencies go in the `dev` group.
- **Privacy** (DR-1 to DR-5):
  - Store no prompts, assistant text, file contents or raw tool arguments. Store hashes, plus file paths only where the signals need them.
  - Never put a path or project name in anything that is shared.
  - The only network call is the share the developer confirms.
- **Factual injected text** (NFR-5): `additionalContext` states facts and evidence, never system-style orders. Keep it short.
- **Small footprint** (NFR-6): short tool and skill descriptions, and no hook output on healthy turns.
- **Speed** (NFR-2): a tool-call hook takes p95 < 150 ms. Read the transcript from its tail only. Open the DB once per hook run.
- **Honesty:** never claim a feature works for an agent or client you didn't test. The README lists only verified setups.
- **Owner config is off-limits** (D-027): probes run against an isolated config; never write to the owner's real Claude Code settings or `~/.cigar/`.
- **Secrets:** none are needed in Session 1. In Session 2, stop and ask the owner for the PyPI token or any login. Never commit tokens.

## Conventions
- Python 3.11+, fully type-hinted, `ruff` clean (format and lint).
- Pure functions for `signals`, `score`, `knee` and `handoff.render`. I/O stays in `hook`, `store`, `mcp_server`, `cli` and `share`.
- The constants in `defaults.py` are the only place tuning numbers live.
- Tests use `pytest`. Every bug fix comes with a test. Fixtures are synthetic unless they're under `tests/fixtures/private/` (gitignored).
- Commits are small, with an imperative subject that references the session, for example `S1: transcript tail reader`.

## Commands
```
uv sync --group dev
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run pytest tests/test_perf.py -s      # prints the hook p95
claude --plugin-dir .                     # load the plugin from this folder in a scratch project
```
Keep these working, and add any that are missing in Session 1.

## When to stop and ask
Stop and report instead of guessing when:
- a requirement conflicts with another
- a gate item can't be met
- a Claude Code behavior differs from the docs (record it in D-014 first)
- you need an owner login or token (GitHub, PyPI)
- you're about to make the repo public
- the session is growing past one prompt's worth of work

## Decisions you make
Append them to `decisions.md` as D-NNN, with the date, decision, why and consequences, and list them in the session report.
