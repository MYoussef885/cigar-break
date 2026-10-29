# Cigar v0.1.0

The first release. Cigar notices when a long Claude Code session starts to slip, has the agent write a structured handoff, and restores it after the context is reset.

**Install** (Claude Code):
```
/plugin marketplace add MYoussef885/cigar-break
/plugin install cigar@cigar-break
```
Standalone MCP server for other agents: `pip install cigar-break`, then run `cigar-mcp`.

**What's in it**
- Detection from free signals (failed calls, repeats, re-reads, undone edits, failed checks) and context pressure; evidence-backed nudges, at most three per session.
- `take_break`, `resume`, `status` and `record_event` MCP tools; handoffs saved in `<project>/.cigar/handoffs/` and restored after `/clear` or `/compact`.
- Modes: `suggest` (default), `observe`, and opt-in `auto`, which clears the context itself only after a handoff is saved (terminal only).
- Per-model knees learned from your own sessions; `/cigar:report` (text and HTML).
- Opt-in, allowlisted curve sharing through a prefilled GitHub issue: `cigar share`.
- `cigar.track` for custom Python agent loops.

**Verified setups:** see the README. Requires Python 3.11+ (found even when `python3` is older). Code: MIT. Shared curves in `data/curves/`: CC0-1.0.
