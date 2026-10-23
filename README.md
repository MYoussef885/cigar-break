# Cigar

> Work in progress: v0.1, Session 1 of 2. Not released yet.

Long agent sessions get worse as the context fills up: failed tool calls, loops, re-reads, undone edits. Cigar is a Claude Code plugin and MCP server that lets the agent take a "cigar break". It notices the decline from signals the session already produces, gets the agent to write a structured handoff, and restores that handoff after the context is reset, so work continues in a fresh context without losing the thread.

## Try it from a local checkout

```
claude --plugin-dir /path/to/cigar-break
```

- `/cigar:status`: fatigue score, context size, knee, recent signals and mode
- `/cigar:break`: have the agent write a handoff now, then type `/clear`
- `/cigar:mode [suggest|observe|auto]`: `suggest` (default) nudges, `observe` only records, `auto` clears the context by itself after a handoff is saved

To see it trigger quickly in a scratch project: `CIGAR_KNEE_TOKENS=20000 CIGAR_MIN_TOKENS=5000 claude --plugin-dir /path/to/cigar-break`.

Cigar needs Python 3.11 or newer somewhere on the machine. It finds `python3.11` to `python3.14` even when `python3` itself is older.

## Verified setups

Only these have been tested:

| Setup | Status |
|---|---|
| Claude Code CLI 2.1.288, terminal, macOS 26, Python 3.11 via uv (system `python3` 3.9) | Detection, nudges, handoff, restore after `/clear` and `/compact`, `suggest` and `auto` modes |
| Claude Code 2.1.309 binary, terminal, macOS | Auto-mode `/clear` from a plugin mod (spike only) |

Not tested yet: the VS Code extension's chat panel, Linux, Windows, and other MCP clients.

## Privacy

- Everything stays on your machine: `~/.cigar/` (store, config, logs) and `<project>/.cigar/` (handoffs, which git ignores through their own `.gitignore`).
- Cigar stores hashes of tool arguments, never the arguments themselves. It stores file paths only for re-read and undo detection, and they never leave the machine.
- It never stores prompts, assistant text or file contents. Handoffs are the exception: the agent writes them on purpose, into your project folder.
- No telemetry and no network calls.

## Development

```
uv sync --group dev
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run pytest tests/test_perf.py -s      # prints the hook p95
uv run python tests/fixtures/make_transcripts.py   # regenerate replay fixtures
```

## License

MIT
