# Changelog

## 0.1.0 · 2026-10-26

First release.

- Detection: failures, repeats, re-reads, undos and failed checks over the last 20 tool calls, plus context pressure, combined into a fatigue score with evidence-backed nudges (at most three per session, 25 calls apart, never below 40k tokens).
- Handoffs: `take_break`, `resume` and `status` MCP tools; handoffs saved in `<project>/.cigar/handoffs/` and restored after `/clear` or `/compact`.
- Modes: `suggest` (default), `observe`, and opt-in `auto` (terminal), which clears the context only after a handoff is saved for the session.
- Learning: per-model knees from your own sessions, per context window (`200k` or `1m`, detected or set with `context_window`); learned knees replace the defaults at medium confidence or above.
- Report: `cigar report` and `/cigar:report`, as text and a self-contained HTML page.
- Sharing: opt-in `cigar share` and `/cigar:share`, an allowlisted aggregate payload opened as a prefilled GitHub issue; `scripts/ingest_curves.py` and `data/curves/`.
- Any agent: `record_event` MCP tool, `cigar.track` helper, `cigar-mcp` on PyPI as `cigar-break`.
- Fail-open hooks; standard library only; Python 3.11+ found even when `python3` is older.
