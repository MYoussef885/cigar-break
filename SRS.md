# SRS: Cigar (v0.1)

**Owner:** Mohamed Youssef (MYoussef885) · **Repo:** `cigar-break` · **Status:** v1.0, approved 2026-10-23

## 1. Purpose

Long agent sessions get worse as the context fills up. The agent forgets earlier decisions, repeats itself, loops on the same files and makes more mistakes. People notice too late, or reset too early and lose their place.

Cigar watches a coding agent's session for signs of decline. When it detects them, it gets the agent to write a structured handoff, resets the context (a "cigar break") and restores the handoff, so the agent picks up fresh without losing the thread. Over time it learns, for each model, the context size where *your* sessions start to degrade, and it lets you share that curve anonymously.

**v0.1 scope:** one developer, one coding agent, in Claude Code. The handoff tools also work as a standalone MCP server for any MCP-speaking agent. Multi-agent teams come later (§8).

## 2. Users and the main story

**Primary user:** a developer running long Claude Code sessions in VS Code or the terminal.

**Main story:**
1. The developer installs Cigar with two commands and forgets about it.
2. Two hours into a session, the agent starts failing tool calls and re-reading files it already read. The context is at 140k tokens.
3. Cigar tells the developer, and the agent, that the session shows fatigue, with the evidence.
4. The agent calls `take_break` and writes a handoff: the goal, what's done, decisions, files touched, next steps and gotchas.
5. The developer types `/clear`. The handoff is injected into the fresh context, and the agent continues where it left off.
6. After a few weeks, `/cigar:report` shows the developer their own quality-vs-context curve per model, with the learned knee point. They share it with one command if they want.

## 3. Concepts

| Term | Meaning |
|---|---|
| **Session** | One Claude Code conversation (`session_id`). A `/clear` starts a new one; compaction keeps the same one. |
| **Event** | One tool call by the main agent, with its outcome and the context size at that moment. |
| **Signal** | A bad pattern found in events: a failure, a loop, a re-read, an undo, a failed test or build. |
| **Fatigue score** | A 0–1 number combining recent signals with context pressure (§4.1, architecture §6). |
| **Knee** | The context size (tokens) where a model's signal rate clearly rises above its baseline. A default per model at first, learned from your data later. |
| **Break** | Write a handoff, reset the context, restore the handoff. |
| **Handoff** | A structured markdown note the agent writes about its own state (§4.2). |
| **Mode** | `suggest` (default): nudge and wait for the developer. `observe`: log only, no nudges. `auto`: reset without the developer, only if the Session 1 spike proves it possible (D-007). |

## 4. Functional requirements

### 4.1 Detection (FR-D) · Session 1

- **FR-D1** Record every main-agent tool call: tool name, a hash of its arguments, success or failure, the file path for file tools, the exit status for shell commands when available, the model, and the context size in tokens.
- **FR-D2** Read the context size and model ID from the session transcript, reading only its tail. Tolerate the transcript lagging a little behind the live session.
- **FR-D3** Detect these signals in a sliding window of recent events:
  - **Failure:** the tool call failed.
  - **Repeat:** the same tool with identical arguments, called again within the window.
  - **Re-read:** a file read again with no edit to it since the last read.
  - **Undo:** an edit that reverses a recent edit to the same file.
  - **Failed check:** a shell command that looks like a test, build, lint or type check, with a non-zero exit.
- **FR-D4** Combine the signals and context pressure (context tokens ÷ knee) into the fatigue score.
- **FR-D5** Never suggest a break below a minimum context floor (default 40k tokens). A hard problem early in a session is not fatigue, and a reset wouldn't help it.
- **FR-D6** Score the main agent only. Record subagent events separately and keep them out of the main score.
- **FR-D7** Track the model through model switches mid-session.

### 4.2 Handoff (FR-H) · Session 1

- **FR-H1** The MCP tool `take_break` accepts a structured handoff: `goal`, `status`, `done[]`, `decisions[]`, `files[]` (path + one-line note), `next_steps[]`, `open_questions[]`, `gotchas[]`.
- **FR-H2** Save the handoff as markdown in `<project>/.cigar/handoffs/`, named by time and session. Mark it as the project's pending handoff.
- **FR-H3** The folder `<project>/.cigar/` ignores itself in git (it holds its own `.gitignore` with `*`). Cigar never edits the project's own `.gitignore`.
- **FR-H4** `resume` returns the latest handoff for the project. `status` returns the current score, context size, knee, recent signals and the mode.
- **FR-H5** A rendered handoff for injection stays under 8,000 characters. A longer one is cut to its goal, status and next steps, followed by the file path to the full version.

### 4.3 Break and restore (FR-R) · Session 1

- **FR-R1** When the score crosses the threshold in `suggest` mode:
  - The agent gets a short, factual note with the evidence and the `take_break` tool name.
  - The developer sees a message and a terminal notification.
- **FR-R2** After a nudge, wait a cooldown (default 25 tool calls) before nudging again. Each repeat nudge is stronger. At most 3 nudges per session.
- **FR-R3** After `take_break` succeeds, tell the developer exactly what to type: `/clear` for a full fresh start (the default advice) or `/compact` to keep a summary.
- **FR-R4** On a session start caused by `/clear` or compaction, inject the pending handoff into the agent's context, then mark it consumed. A handoff older than 24 hours is not injected automatically; `resume` can still fetch it.
- **FR-R5** Record every compaction (automatic or manual) with its context size, as data for learning.
- **FR-R6 · `auto` mode, only if the D-007 spike passes:** the reset itself is triggered without the developer, and the mode is off by default.

### 4.4 Commands (FR-C)

- **FR-C1** `/cigar:status` shows the score, context size, knee, recent signals and mode. *(Session 1)*
- **FR-C2** `/cigar:break` makes the agent write a handoff now, then shows the developer the `/clear` instruction. *(Session 1)*
- **FR-C3** `/cigar:mode <suggest|observe|auto>` changes the mode. `auto` is refused unless it's supported. *(Session 1)*
- **FR-C4** `/cigar:report` shows the developer's curve per model. *(Session 2)*
- **FR-C5** `/cigar:share` runs the opt-in share flow. *(Session 2)*
- **FR-C6** A `cigar` CLI mirrors status, report and share outside Claude Code. *(Sessions 1 and 2)*

### 4.5 Learning (FR-L) · Session 2

- **FR-L1** For each model, group events into context buckets (10k tokens wide) and compute the signal rate per bucket.
- **FR-L2** Fit a knee once the data is sufficient (minimums in architecture §9). Label it with a confidence level: low, medium or high.
- **FR-L3** A learned knee with medium or high confidence replaces the default for that model.
- **FR-L4** The report shows:
  - in the terminal: a text chart of signal rate against context size, with the knee marked
  - as a file: a self-contained HTML page with the same chart, made to be screenshotted and shared

### 4.6 Sharing (FR-S) · Session 2

- **FR-S1** Sharing is opt-in only. Nothing is ever sent automatically. There is no telemetry.
- **FR-S2** `cigar share` builds a payload of aggregates only:
  - the model ID and harness
  - the counts per bucket
  - the knee and its confidence
  - the number of sessions
  - the Cigar version
- **FR-S3** Cigar shows the developer the exact payload and asks for confirmation. It then opens a prefilled GitHub issue on the repo, or prints the URL if no browser opens.
- **FR-S4** A maintainer script validates accepted submissions and adds them to `data/curves/`.

### 4.7 Any agent (FR-M)

- **FR-M1** The MCP server runs on its own (outside the plugin), installed from PyPI. *(Session 2)*
- **FR-M2** A `record_event` tool and a small Python helper let custom agent loops feed events in, so they get detection too. *(Session 2)*
- **FR-M3** The README only shows configurations for other agents that have actually been tested. *(Session 2)*

### 4.8 Packaging (FR-P) · Session 2

- **FR-P1** Install takes two commands from the GitHub repo: add the marketplace, then install the plugin.
- **FR-P2** Releases go to PyPI (name per D-012), with an MIT license and a CHANGELOG.
- **FR-P3** The README is ready to launch: the problem, a 30-second demo, install, how it works, privacy, how to share.

## 5. Data and privacy (DR)

- **DR-1** All data stays on the developer's machine: `~/.cigar/` (global store and config) and `<project>/.cigar/` (handoffs).
- **DR-2** Cigar stores argument hashes, never raw tool arguments, except for file paths, which it needs to detect re-reads and undos. Those stay local.
- **DR-3** It never stores prompts, assistant text or file contents. Handoffs are the exception: the agent writes them on purpose, and they stay in the project folder.
- **DR-4** Shared payloads contain no paths, project names, code, prompts or user identifiers (FR-S2).
- **DR-5** The only network access is a share the developer confirms (FR-S3).

## 6. Non-functional requirements (NFR)

- **NFR-1 · Never harm the session.** Every hook fails open: any error exits 0 silently and is logged to `~/.cigar/logs/`. A broken Cigar must never block a tool call or a prompt.
- **NFR-2 · Speed.** A tool-call hook takes p95 < 150 ms end to end, measured on a 5 MB transcript.
- **NFR-3 · No runtime dependencies.** Python ≥ 3.11 standard library only (D-004). Dev dependencies are fine.
- **NFR-4 · Platforms.** macOS and Linux are fully supported. Windows must at least pass the unit tests, and the hook launch on Windows is verified or documented as a known gap (D-013).
- **NFR-5 · Honest nudges.** The text Cigar injects states facts and evidence, not orders. A nudge always shows the signals behind it.
- **NFR-6 · Small context footprint.** Cigar adds little to every turn: short tool descriptions, short skill descriptions and no output on healthy turns.

## 7. End-to-end check (the Session 1 and 2 dogfood)

1. Install the plugin from a local folder into a scratch project. Set `CIGAR_KNEE_TOKENS=20000` and `CIGAR_MIN_TOKENS=5000` so the test triggers quickly.
2. Work until the score crosses the threshold. The developer and the agent each see the nudge, with its evidence.
3. The agent calls `take_break`. The handoff file exists and is under 8,000 characters as rendered.
4. Type `/clear`. The agent's first reply in the new session shows it has the handoff (it can state the goal and the next step).
5. `/cigar:status` shows a fresh score in the new session.
6. *(Session 2)* `/cigar:report` renders a curve from real data. `cigar share --dry-run` prints a clean payload.

## 8. Out of scope for v0.1 (Later)

- Teams of agents: a shared handoff store, an orchestrator, staggered breaks.
- An OpenAI-compatible proxy, so detection works for any agent without hooks.
- A public web page of shared curves, and a Hugging Face dataset.
- LLM-judged quality signals (they cost tokens; v0.1 uses only free signals).
- Automatic edits to CLAUDE.md or the project's memory.
