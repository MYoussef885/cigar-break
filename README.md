# Cigar 🚬

**Your coding agent gets worse as its context fills up. Cigar notices, has it write a handoff, and restarts it fresh without losing the thread.**

Two hours into a long Claude Code session the agent starts failing tool calls, re-reading files it already read and undoing its own edits. By the time you notice, you've lost twenty minutes; if you reset too early, you lose your place. Cigar watches for those signs, which the session already produces, and offers the agent a *cigar break*: write a structured handoff, reset the context, pick up from the handoff in a fresh one.

In auto mode (opt-in, terminal), the whole break happens by itself. An illustrative session; the 🚬 lines are Cigar's own messages:

```
🚬 Cigar: this session shows fatigue (152k tokens, 9 signals in the last 20 calls).
   Claude has been offered a break; in auto mode the context resets once it saves a handoff.
⏺ cigar - take_break (MCP) … Handoff saved to .cigar/handoffs/2026-10-24T0130-ab12.md
🚬 Handoff ready. Cigar auto mode clears the context now; if it doesn't, type /clear.
🚬 Cigar auto mode cleared the context and restored the handoff from .cigar/handoffs/2026-10-24T0130-ab12.md.
> what's next?
⏺ We're adding retry logic to the upload client. Next: make test_retry_backoff pass …
```

## Install

In Claude Code:

```
/plugin marketplace add MYoussef885/cigar-break
/plugin install cigar@cigar-break
```

Or from a shell: `claude plugin marketplace add MYoussef885/cigar-break && claude plugin install cigar@cigar-break`.

**Requirements:** Python 3.11 or newer somewhere on the machine, and nothing else (no packages to install). Claude Code runs Cigar with whatever `python3` is on your PATH; if that is older (macOS ships 3.9), Cigar's launcher finds `python3.11` to `python3.14` on your PATH, in `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin` or uv's Python folder, and uses it. If there is none, Cigar shows one warning at session start, at most once a day, and otherwise stays out of the way. `uv python install 3.12` is the quickest fix.

## How it works

1. **Detect.** After every tool call, Cigar reads the context size from the tail of the session transcript and looks at the last 20 calls for five signals: failed calls, repeated identical calls, files re-read with no edit in between, edits that undo an earlier edit, and failed tests, builds or lint runs. It combines them with *context pressure* (context size ÷ the model's knee) into a fatigue score. It never nudges below 40k tokens, and never on fewer than 10 calls of evidence (unless the session is far past the knee).
2. **Nudge (`suggest`, the default).** When the score crosses the threshold, the agent gets a short factual note with the evidence, and you see one line (and a terminal notification). At most three nudges per session, 25 calls apart.
3. **Hand off.** The agent calls Cigar's `take_break` tool and writes a handoff: goal, status, what's done, decisions, files, next steps, open questions and gotchas. It's saved in your project's `.cigar/handoffs/`, which git ignores by itself (Cigar never touches your `.gitignore`).
4. **Reset and restore.** Type `/clear` (or `/compact`). Cigar injects the handoff into the fresh session, so the agent's first reply already knows the goal and the next step.
5. **Learn.** Every model starts with a default *knee*, the context size where sessions usually start to slip (for example 100k for Sonnet and 120k for Opus on a 200k window). As you work, Cigar learns where **your** sessions slip, per model, and uses that once it is confident. `/cigar:report` shows the curve.

Modes: `suggest` (default) nudges and waits for you; `observe` only records; `auto` resets by itself (below). Switch with `/cigar:mode`.

### Auto mode (opt-in, terminal)

`/cigar:mode auto` turns it on; it's off by default. In auto mode, once the agent has **saved a handoff for the current session**, Cigar clears the context itself at the end of that turn, restores the handoff, and tells you in one line which handoff it restored. If the agent ignores the nudge, auto mode behaves exactly like `suggest`: it nudges, waits, and never clears. It also never clears after an interrupted turn or for a subagent.

Auto mode uses a Claude Code plugin mod and is **verified in the terminal CLI only**. It is not claimed for the VS Code panel; use `suggest` there.

## Commands

| Command | What it does |
|---|---|
| `/cigar:status` | Fatigue score, context size, knee, recent signals and mode |
| `/cigar:break` | Have the agent write a handoff now; then type `/clear` |
| `/cigar:mode [suggest\|observe\|auto]` | Show or change the mode |
| `/cigar:report` | Your signal rate by context size, per model, with the learned knee; also writes an HTML page |
| `/cigar:share` | Show your anonymous curve; `/cigar:share confirm` opens it as a prefilled GitHub issue |

The same is available outside Claude Code as `cigar status`, `cigar report [--html|--open]`, `cigar share [--dry-run]` and `cigar mode` (`python3 <plugin>/bin/cigar …`, or `cigar` after `pip install cigar-break`).

## Privacy

- **Everything stays on your machine:** `~/.cigar/` (store, config, logs, reports) and `<project>/.cigar/` (handoffs).
- Cigar stores **hashes** of tool arguments, never the arguments. It keeps file paths only to spot re-reads and undos, locally.
- It never stores prompts, assistant text or file contents. Handoffs are the exception: the agent writes them on purpose, into your project folder.
- **No telemetry, no network calls.** The only thing that ever leaves the machine is a curve you choose to share, below, and even then Cigar only opens a prefilled GitHub issue in your browser; nothing is sent until you press Submit there.

## Sharing your curve (opt-in)

Where agents get tired is an open question, and every developer's sessions are a data point. `cigar share` (or `/cigar:share`) shows you the **exact** payload first: one model ID, its context window label (`200k` or `1m`), counts and signal weight per 10k-token bucket, the knee and its confidence, the number of sessions, and the Cigar version. No paths, project names, code, prompts or user identifiers; a strict allowlist check runs before anything is shown. If you confirm, it opens a prefilled issue on this repo. Accepted curves are published in [`data/curves/`](data/curves/README.md) for anyone to use. `cigar share --dry-run` just prints the payload.

Shared curves are published under [CC0-1.0](data/curves/LICENSE) (public domain), not the code's MIT license.

## Other agents

**Standalone MCP server.** `pip install cigar-break` installs `cigar-mcp`, a stdio MCP server with `take_break`, `resume`, `status` and `record_event`. Agents without Claude Code's hooks call `record_event` after each tool call to get detection, and `take_break`/`resume` for handoffs. Tested with the official MCP Python SDK client (`scripts/check_mcp_client.py`); other clients have not been tested yet.

**Custom Python agent loops** can skip MCP and use `cigar.track` directly:

```python
from cigar.track import Tracker

tracker = Tracker(session_id="run-42", model="gpt-5")  # one per agent session


def run_tool(name, args):
    try:
        result = TOOLS[name](**args)
        ok, code = True, 0
    except ToolFailed as exc:
        result, ok, code = str(exc), False, exc.exit_code
    check = tracker.record(
        name,
        ok,
        context_tokens=current_context_tokens(),
        kind={"read_file": "read", "edit_file": "edit", "shell": "shell"}.get(name, "other"),
        path=args.get("path"),
        args=args,  # hashed, never stored
        exit_code=code,
    )
    if check.break_suggested:
        result += "\n\n" + check.message  # factual note: context size, knee, evidence
    return result
```

## Verified setups

Only these have been tested:

| Setup | What was verified |
|---|---|
| Claude Code CLI 2.1.288, terminal, macOS 26, Python 3.11 via uv (system `python3` 3.9) | Detection, nudges, handoff, restore after `/clear` and `/compact`, `suggest` and `auto` modes (live sessions, Session 1) |
| Claude Code 2.1.309, terminal, macOS | Auto-mode `/clear` from the plugin mod; plugin install from a marketplace in two commands |
| `cigar-mcp` from a wheel, official MCP Python SDK 2.3.0 client, macOS and Ubuntu (CI) | All four MCP tools, outside the plugin |
| Unit, replay, fail-open and MCP tests on Ubuntu, macOS and Windows (CI) | Tests only, no live Claude Code session on Linux or Windows |

Not verified yet: the VS Code extension's chat panel, a live session on Linux or Windows, and other MCP clients.

## Prior art

Similar tools exist. foldcrumbs, novyx-hygiene and claude-mem save memory around compaction; Cairn and a "context rot detection" MCP server report health zones from token usage. Most of them use a fixed threshold. Cigar's difference is a per-model knee learned from *behavioral* signals in your own sessions, an evidence-backed nudge that leads into a structured handoff and restore, and an open dataset of shared curves. No code was taken from those projects.

## Configuration

`~/.cigar/config.toml`, overridden by environment variables:

| Key | Env | Default |
|---|---|---|
| `mode` | `CIGAR_MODE` | `suggest` |
| `min_tokens` | `CIGAR_MIN_TOKENS` | `40000` |
| `knee_tokens` (one knee for every model) | `CIGAR_KNEE_TOKENS` | learned or default per model |
| `context_window` (`200k` or `1m`) | `CIGAR_CONTEXT_WINDOW` | detected per session (past 200k means `1m`) |
| `cooldown_events`, `max_nudges` | | `25`, `3` |
| | `CIGAR_HOME` | `~/.cigar` |

To see Cigar trigger quickly in a scratch project: `CIGAR_KNEE_TOKENS=20000 CIGAR_MIN_TOKENS=5000 claude`.

## Development

```
uv sync --group dev
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run pytest tests/test_perf.py -s                    # prints the hook p95
claude --plugin-dir .                                  # load the plugin from this checkout
uv run python scripts/simulate.py --home /tmp/cigar-sim   # fake data with a known knee
CIGAR_HOME=/tmp/cigar-sim uv run cigar report --open
```

Design notes live in [`SRS.md`](SRS.md), [`architecture.md`](architecture.md) and [`decisions.md`](decisions.md). Changes: [`CHANGELOG.md`](CHANGELOG.md).

## License

Code: MIT. Shared curves in `data/curves/`: CC0-1.0.
