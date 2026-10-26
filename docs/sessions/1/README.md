# Session 1 evidence

All paths under the scratch folder are shown as `<scratch>`. Dates are 2026-10-24, on macOS with Claude Code CLI 2.1.288.

| Gate item | Evidence |
|---|---|
| ruff and pytest green (unit, replay, MCP conformance, fail-open, performance) | [tests.txt](tests.txt) |
| Hook p95 < 150 ms on a 5 MB transcript | [perf.txt](perf.txt): p95 76 ms through `/usr/bin/python3` 3.9 with the re-exec, 27 ms with `python3` 3.11 |
| Fail-open: corrupt DB, bad transcript, garbage stdin each exit 0 with no output, and are logged | `tests/test_failopen.py` in [tests.txt](tests.txt) (32 cases, all run through the real launcher) |
| End-to-end with `claude --plugin-dir`, SRS §7 steps 1–5 | [e2e-suggest.md](e2e-suggest.md) and [e2e-auto.md](e2e-auto.md) (driven in a PTY). The owner's interactive `/clear` check below was **confirmed ✅** in the Session 1 review (D-026). |
| D-007 spike recorded with evidence | [d007-spike/results.md](d007-spike/results.md), [d007-spike/register.ts](d007-spike/register.ts), and D-007 in `decisions.md` |
| D-014 findings recorded | D-014 in `decisions.md`; [d014/](d014/) (hook payloads, MCP handshake, MCP server env) |
| Test output, performance numbers, one sample handoff, a log excerpt of a nudge firing | [tests.txt](tests.txt), [perf.txt](perf.txt), [sample-handoff.md](sample-handoff.md), [nudge-log.txt](nudge-log.txt) |

## Owner checklist: the interactive `/clear` step (about 5 minutes)

Run this in any scratch git repo, in a terminal (not the VS Code chat panel, which is untested):

1. `CIGAR_KNEE_TOKENS=20000 CIGAR_MIN_TOKENS=5000 claude --plugin-dir ~/Documents/cigar-break`
2. Ask for something that takes a few tool calls, for example: *Create calc.py with add and mul, and test_calc.py with plain asserts; run it.*
   - [ ] A line starting `🚬 Cigar: this session shows fatigue (…k tokens, …)` appears.
   - [ ] (Optional) A desktop notification appears. This needs a terminal that supports OSC 9, such as iTerm2 or WezTerm; Apple Terminal ignores it.
3. Type `/cigar:break`.
   - [ ] Claude says the handoff was saved to `.cigar/handoffs/…md` and tells you to type `/clear`, and `🚬 Handoff ready…` appears.
4. Type `/clear`.
   - [ ] `🚬 Cigar: restored the handoff from .cigar/handoffs/…` appears.
5. Ask: *What were we working on, and what is the next step?*
   - [ ] The answer states the goal and the next step from the handoff.
6. Type `/cigar:status`.
   - [ ] It shows a new session ID, `not measured yet` or a low score, and `Pending handoff: none`.
7. Optional: auto mode. Type `/cigar:mode auto` and repeat steps 2–3 without typing `/clear`.
   - [ ] The context clears by itself at the end of the turn, and the restore line appears.
   - Then type `/cigar:mode suggest` to go back to the default.

Reply "Session 1 checklist confirmed", or paste what differed. Cigar's data from this check lives in `~/.cigar/` and in the scratch repo's `.cigar/`.
