# Cigar

> Work in progress (v0.1, Session 1). Not ready for general use yet.

Cigar is a Claude Code plugin and MCP server that lets a coding agent take a "cigar break". It notices when a long session starts to slip, gets the agent to write a structured handoff, and restores that handoff after you reset the context with `/clear`.

## Try it from a local checkout

Requires Python 3.11 or newer somewhere on your machine (Cigar finds `python3.11`–`python3.14` even if `python3` is older).

```
claude --plugin-dir /path/to/cigar-break
```

Then: `/cigar:status`, `/cigar:break`, `/cigar:mode`.

## Privacy

Everything stays on your machine: `~/.cigar/` (store, config, logs) and `<project>/.cigar/` (handoffs, ignored by git). No telemetry, no network calls.

## License

MIT
