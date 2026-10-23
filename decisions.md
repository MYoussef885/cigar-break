# Decisions: Cigar

This log is append-only. Write one entry per decision that affects architecture, product or scope, with the newest at the bottom.

Format: **D-NNN · Title**, then Date · Status · Decision · Why · Consequences.

---

**D-001 · Name and identity.** 2026-10-23 · Accepted
- **Decision:**
  - The product is "Cigar" (a working name that may change after launch).
  - The repo is `MYoussef885/cigar-break`, the plugin name is `cigar` (commands `/cigar:*`), and the CLI is `cigar`.
  - MIT license.
- **Why:** the "take a cigar break" metaphor explains the idea instantly, which matters for an open-source launch.

**D-002 · Claude Code first, one agent first.** 2026-10-23 · Accepted (owner direction)
- **Decision:**
  - v0.1 targets a single developer running one coding agent in Claude Code.
  - The handoff tools also ship as a standalone MCP server, so any MCP agent can use them.
  - Teams of agents and an API proxy come later.
- **Why:** this is the fastest route to early users. Claude Code's hooks give Cigar free, rich signals and a reliable way to restore a handoff.

**D-003 · `suggest` is the default mode.** 2026-10-23 · Accepted
- **Decision:**
  - The modes are `suggest` (default), `observe` (log only) and `auto` (only if D-007 passes, and off by default).
- **Why:** a false break in the middle of a task costs more than a missed one. Trust has to come before autonomy.
- **Consequences:** v0.1's promise is "you'll never lose your place, and you'll know when to reset." Fully hands-free resets depend on D-007.

**D-004 · Python ≥ 3.11, standard library only at runtime.** 2026-10-23 · Accepted
- **Decision:** no runtime dependencies. 3.11 is the minimum because `tomllib` is in the standard library from 3.11, and 3.10 reaches end of life in October 2026.
- **Why:** hooks run on every tool call and must start fast. Installing should need nothing beyond the Python most developers already have.
- **Consequences:** the MCP server is hand-written (D-005). The `SessionStart` hook warns once if Python is missing or too old.

**D-005 · Hand-written stdio MCP server, checked against the official SDK.** 2026-10-23 · Accepted
- **Decision:**
  - JSON-RPC 2.0 over stdio, covering `initialize`, `tools/list`, `tools/call` and `ping`.
  - The official `mcp` SDK is a dev dependency, used in a conformance test.
- **Why:** this keeps D-004 and makes installation zero-step, while the conformance test protects compatibility with the spec.

**D-006 · All data local, no telemetry.** 2026-10-23 · Accepted
- **Decision:**
  - The global store and config live in `~/.cigar/` (overridable with `CIGAR_HOME`).
  - Handoffs live in `<project>/.cigar/handoffs/`. That folder ignores itself with its own `.gitignore`, so Cigar never edits the project's `.gitignore`.
  - Projects are identified by a hash of their path.
- **Why:** developers will only install a tool that watches their sessions if it plainly keeps everything on their machine.

**D-007 · Auto-trigger: hooks can't start a reset; test it with a mod.** 2026-10-23 · To verify in Session 1
- **Known:**
  - No Claude Code hook can start a compaction or `/clear`. `PreCompact` can only block one.
  - `SessionStart` with the `clear` or `compact` matcher *can* inject context, so restoring a handoff is reliable.
- **To test:** plugin mods can submit prompts with `$.prompt.submit`, read context usage with `$.session.usage()` and ask the model about the live conversation with `$.model.fork`. The spike tests whether a submitted `/clear` or `/compact` actually runs. See roadmap Session 1 for the steps.
- **Outcome (2026-10-24, Session 1): a plugin mod can start a reset. `auto` mode ships, off by default (D-021).** Evidence: `docs/sessions/1/d007-spike/`.
  1. `$.prompt.submit({ text: "/clear" })` and `"/compact"`, with and without `asUser`: refused by the host every time (4/4). The error says: "a text beginning with / would run a command as the user; run one with $.command.run({ command })".
  2. `$.command.run({ command: "clear" })` (documented in the mods API, step 3): a real `/clear` in 3/3 runs (twice on CLI 2.1.288, once on 2.1.309). Each run fired `SessionEnd(clear)` then `SessionStart(clear)` with a new session ID, and the context injected there reached the next reply.
  3. `$.command.run({ command: "compact" })` and `$.session.compact()`: a real compaction in 3/3 runs (`PreCompact(manual)` then `SessionStart(compact)`), with the injected context reaching the next reply.
  - Limits: tested in the terminal CLI only, never in the VS Code extension's chat panel. `$.command.run` rejects inside a hook the turn waits on, so the mod schedules it with `$.clock.after`.

**D-008 · Don't rely on `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`.** 2026-10-23 · Accepted
- **Decision:** Cigar doesn't set or depend on the auto-compact threshold variable.
- **Why:**
  - Public GitHub issues report that it can only lower the threshold, that it is ignored when set in `settings.json`, and that it sometimes doesn't fire.
  - It is also global, not per model, and can't change mid-session.

**D-009 · Free signals only in v0.1.** 2026-10-23 · Accepted
- **Decision:** detection uses only what hooks and the transcript already provide: failures, repeats, re-reads, undos, failed checks and context size. There are no LLM-judged probes.
- **Why:** zero extra token cost and no latency. Probes are listed under Later.

**D-010 · Distribution: the repo is its own plugin marketplace, plus PyPI.** 2026-10-23 · Accepted
- **Decision:**
  - Claude Code users add the GitHub repo as a marketplace and install from it.
  - Other agents install `cigar-break` from PyPI and run `cigar-mcp`.
  - A submission to Anthropic's plugin directory comes after launch.
- **Why:** a two-command install with no backend and no approval wait.

**D-011 · Short plans and lighter evidence from the start.** 2026-10-23 · Accepted (owner direction, carried over from Sanad D-031)
- **Decision:**
  - The plan is at most 15 lines. Ask only questions that block; otherwise implement straight after the plan.
  - Evidence is test output and logs, plus screenshots only where a gate asks.
  - The report is one page at most.
- **Why:** the owner wants two strong sessions to launch, not process overhead.

**D-012 · PyPI name.** 2026-10-23 · To verify in Session 2
- **Decision:** use `cigar-break` if it's free. Otherwise use `cigar-agent`, and record which.

**D-013 · Windows support level.** 2026-10-23 · Accepted
- **Decision:**
  - macOS and Linux are fully supported.
  - On Windows, the unit tests run in CI. If the hook launcher (`python3` in exec form) doesn't work there, document it as a known gap rather than blocking the launch.
- **Why:** this is the fastest route to launch. Most Claude Code power users are on macOS or Linux.

**D-014 · Facts to verify on the current Claude Code version before building.** 2026-10-23 · To verify in Session 1
Check each one on the owner's machine and record what is true:
1. The transcript JSONL layout: where `usage` and `model` sit on assistant entries, and how far the file lags.
2. Whether a failed Bash command fires `PostToolUse` or `PostToolUseFailure`, and where the exit code appears in the hook input.
3. The field names for Read, Edit and Write tool inputs (path, old and new strings), and whether `MultiEdit` still exists.
4. That `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_ROOT` reach the plugin's stdio MCP server, and how `.mcp.json` should reference the launcher.
5. How plugin skill names appear as commands (`/cigar:status`), and the skill frontmatter fields.
6. The current MCP protocol version string that Claude Code sends in `initialize`.
7. The Python version on the owner's machine, and whether `python3` resolves from hooks.
8. Whether `SessionStart` `additionalContext` after `/clear` reliably reaches the first reply.

**D-014 findings (2026-10-24, Session 1).** Checked on CLI 2.1.288 (the `claude` on PATH). The VS Code extension on this machine runs 2.1.309. Evidence: `docs/sessions/1/d014/`.
1. **Transcript.** Assistant entries have `type: "assistant"`, `message.model` and `message.usage.{input_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, plus `isSidechain`.
   - Subagents write to separate files (`<session>/subagents/agent-*.jsonl`).
   - At `PostToolUse` time the calling `tool_use` entry is already written. On a session's very first response the hook found no usage twice in a live run, so Cigar reuses the last known value.
   - The docs call this format internal and say it "changes between versions", so the reader is defensive.
   - Model IDs carry no `[1m]` marker, even in a 1M-context session (`claude-opus-5-5`).
2. **Failed Bash** fires `PostToolUseFailure` with `error: "Exit code 3\n<output>"` and `is_interrupt`. There is no exit-code field; Cigar parses `^Exit code N`. A successful Bash `tool_response` is `{stdout, stderr, interrupted, isImage, noOutputExpected}`, with no exit code (Cigar treats it as 0). A failed Read also fires `PostToolUseFailure`.
3. **Tool inputs.**
   - Read: `{file_path, offset?, limit?}`.
   - Edit: `{file_path, old_string, new_string, replace_all}`.
   - Write: `{file_path, content}`, whose `tool_response.originalFile` is hashed and never stored.
   - `MultiEdit` is gone from the 2.1.309 tool types; the parser still accepts it.
   - Subagent tool calls carry `agent_id` and `agent_type`. The Agent tool call itself does not.
4. **MCP server environment.** The plugin's stdio MCP server receives `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA`. It also gets `CLAUDE_CODE_SESSION_ID`, but the server process survives `/clear` (one PID served two sessions in the auto run), so that ID goes stale (D-023).
   - `.mcp.json`: `"command": "python3", "args": ["-I", "-S", "${CLAUDE_PLUGIN_ROOT}/bin/cigar-mcp"]`.
   - Tools appear as `mcp__plugin_cigar_cigar__<tool>` and are deferred (the agent loads them with ToolSearch).
5. **Skills.** `skills/<name>/SKILL.md` becomes `/cigar:<name>`. Frontmatter used: `name`, `description`, `argument-hint`, `allowed-tools`, `disable-model-invocation`.
   - Inline `` !`cmd` `` with `${CLAUDE_PLUGIN_ROOT}` and `"$ARGUMENTS"` works, even in `-p`.
   - **A non-zero exit aborts the skill and hides its output**, so the skill lines end with `2>&1 || true`.
6. **MCP protocol.** Claude Code first sends `server/discover` (protocol `2026-07-28`). On `-32601` it falls back to `initialize` with `protocolVersion: "2025-11-25"`. The official `mcp` SDK 2.3.0 negotiates `2025-11-25` the same way.
7. **Python.** `python3` on PATH, and in hooks, is `/usr/bin/python3` 3.9.6. Python 3.11.15 and 3.12.13 exist through uv (`~/.local/bin/python3.11`). This conflicts with D-004's assumption, so the launcher re-execs a newer Python (D-022).
8. **Restore after a reset.** `SessionStart` `additionalContext` reached the first reply after every `/clear` tested (1 typed, 3 mod-triggered, plus both end-to-end runs) and after every compaction (4/4).
   - `SessionStart` carries `model` on `startup` and `compact` in interactive sessions, but not on `clear` and not in a `-p` `startup`.
- **Also found:**
  - `PostModelSwitch` exists, with `from_model`, `to_model` and `context_tokens`.
  - `/model <x>` also saves `<x>` as the default model in `~/.claude/settings.json`.
  - `terminalSequence` is a top-level hook output field (OSC 0/1/2/9/99/777 or BEL, interactive sessions only).
  - Hook `timeout` is in seconds.
  - One `hooks/hooks.json` can hold both `hooks` and `modules`, and both load at runtime.

**D-015 · Opt-in sharing through GitHub issues, no backend.** 2026-10-23 · Accepted
- **Decision:**
  - `cigar share` shows the aggregate payload and asks for confirmation, then opens a prefilled issue from the `curve.yml` template.
  - The maintainer runs `scripts/ingest_curves.py` to validate accepted issues and commit them to `data/curves/`.
- **Why:** a shared benchmark dataset with no server, cost or secrets. Every submission is public and auditable.

**D-016 · Prior art and positioning.** 2026-10-23 · Accepted
- **Similar tools exist:**
  - foldcrumbs, novyx-hygiene and claude-mem save memory around compaction.
  - Cairn and a "context rot detection" MCP give health zones from token usage.
- **Most use a fixed threshold.** Cigar's difference is:
  1. a per-model knee learned from *behavioral* signals in the developer's own sessions
  2. an evidence-backed nudge that leads into a structured handoff and restore
  3. an open dataset of shared curves
- **Consequences:**
  - Don't copy code from those projects. If an idea is borrowed, check its license and credit it in the README.
  - The README states this difference in one honest paragraph.

**D-017 · Starting default knees.** 2026-10-24 · Accepted
- **Decision** (tokens of context, counted as in architecture §5):

  | Model family | 200k window | 1M window |
  |---|---|---|
  | Opus | 120k | 160k |
  | Sonnet | 100k | 140k |
  | Haiku | 70k | 70k |
  | Anything else | min(0.5 × window, 120k) | min(0.5 × window, 120k) |

  - A window counts as 1M when the model ID is marked (`[1m]`) or once more than 200k tokens are seen. Transcripts don't mark it (D-014).
- **Why:**
  - Public long-context evaluations agree that quality falls well before the advertised window, even on simple tasks:
    - RULER (Hsieh et al., 2024, arXiv:2404.06654): most models fall below its threshold before their claimed length.
    - NoLiMa (Modarressi et al., ICML 2025, arXiv:2502.05167): at 32k, 11 of 13 models drop below half their short-context score once literal matches are removed.
    - Chroma, "Context Rot" (Hong, Troynikov and Huber, July 2025): all 18 models tested, including Claude 4, became less reliable as input grew.
  - These are retrieval and reasoning benchmarks, not agentic coding. A coding session also carries 25–40k tokens of well-structured system prompt and tools (this machine: about 32–41k before the first tool call). So the knees sit well above the 32k benchmark cliffs, ranked by model strength.
  - Rule (b) (1.3 × knee) lands Opus at about 156k and Sonnet at about 130k, just before a 200k window's auto-compaction.
  - The exact numbers matter less than the learned replacement in Session 2.
- **Consequences:** the values live in `defaults.py`. `CIGAR_KNEE_TOKENS` overrides them for every model.

**D-018 · Signal details the architecture left open.** 2026-10-24 · Accepted
- **Decision:**
  - `reread` needs the same path *and* the same range (`offset`/`limit`) as an earlier read, with no edit in between. Paging through a big file is not a re-read.
  - A read is scored as `reread`, never also as `repeat`.
  - `is_interrupt: true` (the developer stopped the call) is not a `failure`.
  - The Bash exit code is parsed from `error` (D-014). A `description` field is ignored in `args_hash`.
  - Cigar's own MCP tool calls are recorded but never scored.
- **Why:** each choice removes a false positive seen or expected in normal work. Nudging on evidence that isn't there is the costliest mistake (CLAUDE.md "Trust is the product").

**D-019 · Store schema details.** 2026-10-24 · Accepted
- **Decision:** columns added to architecture §8:
  - `sessions`: `last_seen`, `source`, `context_tokens` (last known, for transcript lag), `main_events`, `last_nudge_seq`, `break_at`, `reminded`.
  - `events`: `kind`, `edit_old_hash`, `edit_new_hash` (hashes of edit text, never the text), `is_check`, `behavior`.
  - `handoffs.path` is relative to the project, so no absolute project path is stored.
  - Saving a new handoff supersedes any older pending one.
  - Migrations are numbered SQL files tracked by `PRAGMA user_version`, applied under `BEGIN IMMEDIATE`.
- **Why:** undo detection needs a stable fingerprint of edit text without storing it (DR-2). Cooldowns and the Stop reminder need per-session state.

**D-020 · Behavior rules need at least 10 events.** 2026-10-24 · Accepted
- **Decision:** rules (a) and (c) of architecture §6 fire only once the window holds at least 10 main-agent events. Rule (b), pressure alone, is unchanged.
- **Why:** the `distress` replay fixture nudged after 5 tool calls, on a 5-event average. A session resumed at high context, or Cigar installed mid-session, would nag on almost no evidence.

**D-021 · Auto mode design.** 2026-10-24 · Accepted (follows the D-007 outcome)
- **Decision:**
  - `auto` stays off by default (D-003); `/cigar:mode auto` or `CIGAR_MODE=auto` turns it on.
  - In auto mode, a successful `take_break` makes the hook write `~/.cigar/auto/<session>.json` (`state: ready`).
  - The mod (`mods/auto.ts`, registered under `modules` in `hooks/hooks.json`) acts on `turn.complete` for the main agent when the turn ended with an answer. It marks the file `fired` and runs `$.command.run({ command: "clear" })` one second later.
  - The handoff comes back through the same `SessionStart(clear)` hook as in suggest mode.
  - Auto mode never clears without a saved handoff, and never after an interrupted turn.
  - The nudge, the `take_break` reply and the Stop reminder say what auto mode does.
  - Not built: drafting a handoff with `$.model.fork` when the agent ignores the nudge. In the live run, the agent called `take_break` by itself, 7 s after an auto-mode nudge.
- **Why:** this is the smallest mechanism that keeps the only cross-process contract to one small file. By design (not yet tested), if mods are unavailable the marker is never consumed and Cigar behaves like `suggest`, with the Stop reminder saying to type `/clear`.
- **Consequences:** verified in the terminal CLI only. The README must not claim it works in the VS Code panel until it's tested there.

**D-022 · Launchers tolerate an old `python3`.** 2026-10-24 · Accepted
- **Decision:**
  - `bin/_launch.py` uses only Python 3.8 syntax.
  - Under a Python older than 3.11, it re-execs the first `python3.14` to `python3.11` it finds on PATH, in `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin` or uv's Python folder. The path is cached in `~/.cigar/python`.
  - With none found, a hook exits 0 silently, except `SessionStart`, which shows a one-line warning at most once a day.
  - Hooks run as `python3 -I -S` to skip site packages.
- **Why:** D-014 item 7: this machine's `python3` is 3.9.6, so `tomllib` and the rest of the 3.11 code would fail in every hook.
- **Consequences:** the re-exec adds about 50 ms here. Hook p95 is 76 ms through `/usr/bin/python3`, and 27 ms when `python3` is already 3.11.

**D-023 · How the MCP server, CLI and skills find the session.** 2026-10-24 · Accepted
- **Decision:** the session is the one passed in, otherwise the most recently active session (`last_seen`) for the project's hash.
- **Why:** `CLAUDE_CODE_SESSION_ID` in the MCP server's environment goes stale after `/clear`, because the server outlives it (D-014 item 4). `SessionStart` refreshes `last_seen`, so `/cigar:status` right after `/clear` shows the new session.
- **Consequences:** two sessions at once in the same project can be confused. That's acceptable for v0.1's single-developer, single-agent scope (D-002).

**D-024 · MCP protocol scope.** 2026-10-24 · Accepted
- **Decision:**
  - Answer `initialize` for `2025-11-25`, `2025-06-18`, `2025-03-26` and `2024-11-05`; any other requested version gets `2025-11-25`.
  - `server/discover` (the stateless `2026-07-28` flow) gets `-32601`, which Claude Code and the official SDK both handle by falling back.
- **Why:** this keeps the hand-written server small (D-005) while both real clients connect.

**D-025 · Skills are user-invoked only, and handoffs require next steps.** 2026-10-24 · Accepted
- **Decision:**
  - All three skills set `disable-model-invocation: true`, so they add nothing to the model's context (NFR-6). Inline shell lines end with `2>&1 || true` (D-014 item 5).
  - `take_break` requires `goal`, `status` and at least one `next_steps` entry.
  - A `files` entry written as one `"path — note"` string is split, since an agent did that in the end-to-end run.
- **Why:** the restored session must be able to state the next step (SRS §7 step 4).

