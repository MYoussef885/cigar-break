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
- **Outcome:** *(Session 1 fills this in)*

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
