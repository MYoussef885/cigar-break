# Architecture: Cigar (v0.1)

## 1. Overview

```
Claude Code session
  │  hooks (stdin JSON)                        MCP (stdio)
  ▼                                            ▼
cigar-hook  ──► transcript tail ──► signals ──► score ──► nudge (additionalContext + systemMessage)
  │                                   │                         │
  └──────────────► store (~/.cigar/cigar.db) ◄───────── cigar MCP server: take_break · resume · status · record_event
                                      │                         │
                       knee · report · share (S2)      <project>/.cigar/handoffs/*.md
                                                                │
                              SessionStart(clear|compact) ──► inject pending handoff
```

There are three entry points, all in one Python package (`src/cigar/`):
- **`cigar-hook <event>`**: called by Claude Code hooks. It is short-lived, fast and fails open.
- **`cigar-mcp`**: a stdio MCP server, started by the plugin or by any MCP client.
- **`cigar`**: the CLI for status, report, share and mode.

## 2. Stack

- **Python ≥ 3.11, standard library only at runtime** (D-004): `sqlite3`, `json`, `hashlib`, `tomllib` and `argparse`.
- **The MCP server is hand-written over stdio JSON-RPC** with no SDK (D-005). It is checked in tests against the official `mcp` Python SDK client, which is a dev dependency.
- **Dev tools:** `pytest`, `ruff`, the `mcp` SDK for the conformance test, and `uv` for development and publishing only.
- **Optional:** a small JavaScript mod in `mods/`, only if the D-007 spike succeeds.

## 3. Repo layout

```
cigar-break/
├── .claude-plugin/
│   ├── plugin.json            # name "cigar", version, description
│   └── marketplace.json       # this repo as a one-plugin marketplace (S2)
├── hooks/hooks.json           # hook registrations, exec form, ${CLAUDE_PLUGIN_ROOT}
├── .mcp.json                  # plugin MCP server "cigar" → bin/cigar-mcp
├── skills/                    # /cigar:status, /cigar:break, /cigar:mode, /cigar:report (S2), /cigar:share (S2)
├── bin/                       # thin launchers: cigar-hook, cigar-mcp, cigar (put src/ on sys.path)
├── mods/                      # only if D-007 passes
├── src/cigar/
│   ├── hook.py                # dispatch per event, fail-open wrapper, timing
│   ├── transcript.py          # tail reader: context tokens, model ID
│   ├── signals.py             # detectors (pure functions over events)
│   ├── score.py               # fatigue score + nudge policy
│   ├── defaults.py            # default knees per model family, window sizes
│   ├── store.py               # SQLite schema, migrations, queries
│   ├── handoff.py             # schema, validation, render, save, load, truncate
│   ├── mcp_server.py          # JSON-RPC stdio server and tools
│   ├── config.py              # ~/.cigar/config.toml + env overrides
│   ├── cli.py                 # `cigar` command
│   ├── knee.py                # S2
│   ├── report.py              # S2 (text + HTML)
│   ├── share.py               # S2
│   └── track.py               # S2: helper for custom agent loops
├── tests/  (fixtures/transcripts/ synthetic; fixtures/private/ gitignored)
├── data/curves/               # S2: accepted shared curves
├── scripts/ingest_curves.py   # S2
├── docs/sessions/N/           # gate evidence
├── pyproject.toml · README.md · LICENSE (MIT) · CHANGELOG.md
└── CLAUDE.md · SRS.md · architecture.md · roadmap.md · decisions.md
```

## 4. Hooks

The hooks are registered in `hooks/hooks.json` in exec form, for example: `"command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/bin/cigar-hook", "post_tool_use"]`. Every handler is wrapped so that an exception exits 0 with no output and is logged (NFR-1).

| Event (matcher) | What Cigar does | Output |
|---|---|---|
| `SessionStart` (`startup\|resume`) | Registers the session and records the model if present. Checks the Python version. | `systemMessage` only if Python is too old |
| `SessionStart` (`clear\|compact`) | Finds the project's pending handoff (≤ 24 h old), renders it (≤ 8,000 chars) and marks it consumed | `additionalContext` with the handoff |
| `PostToolUse` (all tools) | Records the event, reads the transcript tail, updates signals and score, applies the nudge policy | Nothing on a healthy turn. On a nudge: `additionalContext`, `systemMessage` and `terminalSequence` |
| `PostToolUseFailure` (all tools) | Same as above, with `failed=1` | Same as above |
| `PostModelSwitch` | Records the new model for the session | none |
| `PreCompact` (`manual\|auto`) | Records a compaction event with its trigger and context size (FR-R5). Never blocks | none |
| `Stop` | If a handoff was saved this session and the developer hasn't reset yet, reminds them once | `systemMessage` |
| `SessionEnd` | Closes the session row | none |

Rules:
- An event that carries `agent_id` came from a subagent. It is stored with `is_subagent=1` and excluded from the main score (FR-D6).
- Text Cigar injects is written as **factual statements**, never as system-style commands. Claude Code's docs warn that command-style injected text can trip Claude's prompt-injection defenses. An example of the right style is in §7.
- `additionalContext` is capped at 10,000 characters by Claude Code. Cigar's own cap is 8,000 (FR-H5).

## 5. Transcript reading

- The hook input gives `transcript_path` (JSONL). Read backwards from the end in 64 KB blocks until the latest assistant message that has `usage` is found.
- **Context tokens** = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from that `usage`. This is the same formula as the status line's `used_percentage`.
- **Model ID** = `message.model` on the same entry. Fall back to the session's last known model.
- The transcript is written asynchronously and can lag the live session by a turn. That's acceptable; the reading is an approximation. If no usage is found, reuse the last known value for the session.
- Session 1 verifies the exact field names on the current Claude Code version and records them (D-014).

## 6. Signals and score (v0.1 heuristic)

**Window:** the last 20 main-agent events in this session.

| Signal | Rule | Weight |
|---|---|---|
| `failure` | The event failed (`PostToolUseFailure`, or a tool error in the response) | 1.0 |
| `repeat` | Same `tool` and same `args_hash` as an earlier event in the window | 0.8 |
| `reread` | A read tool on a path already read this session, with no edit to that path since | 0.5 |
| `undo` | An edit whose new text equals the old text of an earlier edit to the same path in the last 50 events | 1.0 |
| `check_fail` | A shell command matching test, build, lint or type-check patterns (configurable regex list) with a non-zero exit | 0.7 |

- `behavior` = (sum of the weights in the window) ÷ (number of events in the window), capped at 1.
- `baseline` = the model's median `behavior` on events below 40% of its knee, from the store. If there are fewer than 200 such events, use the default constant 0.08.
- `pressure` = context tokens ÷ knee.
- **The nudge fires when** context tokens ≥ the minimum floor (40k by default), **and** one of these holds:
  - (a) `pressure ≥ 1.0` **and** `behavior ≥ baseline + 0.10`
  - (b) `pressure ≥ 1.3` (well past the knee, whatever the behavior)
  - (c) `behavior ≥ 0.45` **and** `pressure ≥ 0.6` (clear distress before the knee)
- `fatigue` (for display) = `clamp(0.5·min(pressure,1.5)/1.5 + 0.5·behavior/0.45, 0, 1)`.
- **Cooldown:** 25 events between nudges, at most 3 nudges per session. Each repeat nudge is worded more strongly. A `take_break` resets the counter.

These constants live in `defaults.py` and can be overridden through config. They are starting values, and the learned knee (§9) is what makes them personal.

**Default knees** (`defaults.py`): a table keyed by model family, plus a generic fallback of `min(0.5 × window, 120k)`. The window size per model comes from the same table: 200k by default, or 1M for model IDs marked as extended-context. Session 1 picks the starting values, writes the reasoning in a decision, and cites any public long-context evaluations it relied on. Exact numbers matter less than the learned replacement.

## 7. Nudge and handoff text

**Nudge (`additionalContext`), first time:**
> Cigar session check: context is at 142k tokens; the knee for claude-sonnet-5 is ~120k. In the last 20 tool calls: 4 failed, 3 files re-read without edits, 1 edit undone. Sessions past this point usually degrade. The `take_break` tool (cigar MCP) saves a handoff so work can resume in a fresh context.

**`systemMessage` to the developer:**
> 🚬 Cigar: this session shows fatigue (142k tokens, 8 signals in the last 20 calls). Claude has been offered a break. Run /cigar:break to force one.

**After `take_break` (tool result):**
> Handoff saved to .cigar/handoffs/2026-10-24T0130-ab12.md. When the developer types /clear, it will be restored automatically into the fresh session.

**`Stop` reminder (once):** 🚬 Handoff ready. Type /clear to take the break (or /compact to keep a summary).

**Handoff markdown** (rendered from the `take_break` input):
```
# Cigar handoff · <project> · <iso time>
**Goal:** …
**Status:** …
## Done
## Decisions
## Files (path — note)
## Next steps (numbered, the first one is the immediate action)
## Open questions
## Gotchas
```

**Injection after `/clear`:** "This session continues earlier work. The handoff written before the context reset follows." followed by the rendered handoff.

## 8. Store (`~/.cigar/cigar.db`, SQLite, WAL mode)

```
sessions(id, project_hash, harness, model_first, model_last, started_at, ended_at, nudges, breaks)
events(id, session_id, ts, tool, args_hash, path, failed, exit_code, is_subagent,
       context_tokens, model, signals_json)
compactions(id, session_id, ts, trigger, context_tokens, model)
handoffs(id, project_hash, session_id, path, created_at, consumed_at)
meta(key, value)                      -- schema_version, cigar_version
```

- `project_hash` = the first 16 hex characters of the SHA-256 of the absolute project path. Raw project paths are never stored.
- The `path` column in `events` stays local (DR-2) and is never exported.
- Every connection sets `busy_timeout` = 2000 ms, because hooks can run concurrently.
- Migrations are numbered SQL files applied at startup.

## 9. Knee estimation (Session 2)

- **Per model:** events from main-agent sessions, grouped into 10k-token buckets.
- **Bucket rate** = the summed signal weight ÷ the number of events in the bucket.
- **A bucket counts** when it has ≥ 50 events from ≥ 3 sessions.
- **Fitting:**
  - `baseline` = the median rate of the qualifying buckets below the 40th percentile of tokens.
  - `knee` = the lowest bucket where the mean rate of it and the next two qualifying buckets is ≥ 1.5 × `baseline`, and the rate never drops back below `baseline` in the later buckets.
- **Confidence:**
  - low: fewer than 5 sessions or fewer than 6 qualifying buckets
  - medium: at least 5 sessions and 6 buckets
  - high: at least 15 sessions and 10 buckets
- Only medium or high confidence replaces the default (FR-L3). Compactions are shown on the chart but not used in the fit.

## 10. Report and share (Session 2)

- **Text report:** for each model, a bar row per bucket showing the rate, with the knee and the default knee marked, and the confidence label.
- **HTML report:** a single file at `~/.cigar/reports/<date>.html` with an inline SVG chart (no external assets), titled "Where my agent gets tired", with model tabs. It is designed to be screenshotted.
- **Share payload** (`schema_version: 1`):
  - `cigar_version`, `harness` (`"claude-code"`), `model`
  - `sessions`, `events`
  - `buckets: [{lo, hi, events, weight}]`
  - `knee`, `confidence`, `default_knee`
- **Share flow:** print the payload → ask for confirmation → open `https://github.com/MYoussef885/cigar-break/issues/new?template=curve.yml&...` with the payload in a code block. If the URL is longer than 7,500 characters, drop buckets with fewer events until it fits.
- **`scripts/ingest_curves.py`:** run by the maintainer. It uses `gh` to list issues labelled `curve-accepted`, validates each against the schema, and writes `data/curves/<model>/<issue>.json`.

## 11. MCP server

The server speaks stdio JSON-RPC 2.0 and handles `initialize`, `notifications/initialized`, `tools/list`, `tools/call` and `ping`. It uses the protocol version that Session 1 verifies (D-014).

| Tool | Input | Effect |
|---|---|---|
| `take_break` | goal, status, done[], decisions[], files[{path,note}], next_steps[], open_questions[], gotchas[], project? | Validates, renders, saves and marks pending. Returns the path and the next instruction |
| `resume` | project? | The latest handoff for the project (pending or most recent) |
| `status` | session_id? | Score, tokens, knee, recent signals, mode |
| `record_event` (S2) | session_id, tool, ok, context_tokens, model, path?, args? | Lets custom agent loops feed detection. Returns the score and whether a break is suggested |

- **Project resolution:** the `project` argument, otherwise `CLAUDE_PROJECT_DIR` (Claude Code sets it for stdio MCP servers), otherwise the working directory.
- **Tool descriptions are kept short** (NFR-6). The `take_break` description says when to use it: when Cigar reports fatigue, when the developer asks, or before a long new phase of work.

## 12. Config

`~/.cigar/config.toml`, overridden by environment variables:

| Key | Env | Default |
|---|---|---|
| `mode` | `CIGAR_MODE` | `suggest` |
| `min_tokens` | `CIGAR_MIN_TOKENS` | 40000 |
| `knee_tokens` (forces one knee for every model) | `CIGAR_KNEE_TOKENS` | unset |
| `cooldown_events` | | 25 |
| `max_nudges` | | 3 |
| `check_patterns` | | test, build, lint, type-check regex list |
| `home` | `CIGAR_HOME` | `~/.cigar` |

## 13. Testing

- **Unit:** signals, score, transcript tail reader (including a lagging transcript and a missing usage field), handoff render and truncation, store migrations, config precedence.
- **Replay:** synthetic transcript fixtures run through the hook logic, asserting the score over time and when nudges fire. A real transcript from the owner can go in `tests/fixtures/private/` (gitignored) for a local-only replay.
- **MCP conformance:** the official `mcp` SDK client connects to `cigar-mcp`, lists the tools and calls each one.
- **Fail-open:** corrupt the database, give an unreadable transcript, feed garbage on stdin. Each must exit 0 with no output, and each must be logged.
- **Performance:** a 5 MB synthetic transcript, 200 runs of the hook, p95 < 150 ms reported.
- **CI** (GitHub Actions): ruff and pytest on Ubuntu, macOS and Windows, Python 3.11 and 3.13.
