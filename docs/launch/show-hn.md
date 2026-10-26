# Show HN (draft)

**Title:** Show HN: Cigar – detect when a coding agent's context is rotting and hand off to a fresh one

**URL:** https://github.com/MYoussef885/cigar-break

**Text:**

Long coding-agent sessions degrade as the context fills: more failed tool calls, re-reading the same files, undoing earlier edits. Benchmarks like RULER, NoLiMa and Chroma's "Context Rot" report show quality falling well before the advertised window, but in practice you notice it late, or you reset early and lose your place.

Cigar is a Claude Code plugin (plus a standalone MCP server) that:

- scores each session from free signals the hooks already provide (failures, repeated calls, re-reads without edits, undone edits, failed checks) against context pressure. No LLM-judged probes and no extra tokens;
- when the score crosses a threshold, gives the agent a short factual note with the evidence and a `take_break` tool, which writes a structured handoff (goal, status, decisions, files, next steps, gotchas);
- restores that handoff into the fresh context after /clear (or does the /clear itself in an opt-in auto mode, only once a handoff is saved);
- learns, per model, the context size where *your* sessions start to slip, from your own data, and can share that curve as an anonymous aggregate if you opt in. I'd like to build an open dataset of these curves.

Implementation notes: Python standard library only (hooks run on every tool call, p95 under 150 ms on a 5 MB transcript); a hand-written stdio MCP server checked against the official SDK; everything fails open (any error exits 0 silently and is logged), because a session-health tool that can break your session is worse than nothing. All data stays local; sharing opens a prefilled GitHub issue that you submit yourself, so there's no backend at all.

Prior art: foldcrumbs, novyx-hygiene and claude-mem save memory around compaction; Cairn and a context-rot MCP server show health zones from token usage. Most use a fixed token threshold; Cigar's bet is behavioral signals plus a per-developer learned knee.

Verified: Claude Code terminal CLI on macOS. CI runs the test suite on Linux, macOS and Windows. The standalone MCP server is tested with the official Python SDK client; I'd love reports from other clients.

Happy to answer questions about the scoring, the knee estimator, or what auto-clearing a Claude Code session from a plugin involves.
