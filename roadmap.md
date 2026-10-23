# Roadmap: Cigar v0.1

**Two sessions in total.** Each session is one Claude Code prompt and is done only when its gate is met. After each session, its report goes to Claude Chat for review, and Claude Chat unlocks the next session (or sends a short fix-up prompt first).

> The roadmap is a guide, not a prison. If a session reveals something that changes the plan, stop, report it, and let Claude Chat decide.

**Evidence rules for both sessions (D-011):**
- The plan is at most 15 lines, with only the questions that block. If nothing blocks, implement straight after the plan.
- Evidence is test output and short logs in `docs/sessions/N/`. Screenshots only where the gate asks for one.
- The report is at most one page.

| # | Session | Status |
|---|---|---|
| 1 | Core loop: detect, hand off, restore | Next |
| 2 | Learn, share, package, launch | |

---

## Session 1 · Core loop: detect, hand off, restore

**Setup**
- Run the D-014 checks first and record the findings before building on them.
- Scaffold the repo as in architecture §3:
  - `pyproject.toml` with no runtime dependencies; dev dependencies are `pytest`, `ruff` and `mcp`
  - the launchers in `bin/`
  - `plugin.json`, `hooks/hooks.json` and `.mcp.json`
  - MIT `LICENSE`, and a stub `README.md`
- `git init` with small `S1:` commits. If `gh` is authenticated, push to a **private** repo `MYoussef885/cigar-break`. It goes public in Session 2.

**Core**
- `config.py`, `store.py` (schema and migrations, WAL, busy timeout), `transcript.py` and `defaults.py` (starting knees, with the reasoning in a decision).
- `signals.py` and `score.py`, exactly as in architecture §6.
- `hook.py`: every event in architecture §4, fail-open, with timing logged.
- `handoff.py`: validate, render, truncate to 8,000 characters, save to `<project>/.cigar/handoffs/`, with the self-ignoring `.cigar/.gitignore`.
- `mcp_server.py` with `take_break`, `resume` and `status`.
- Skills `/cigar:status`, `/cigar:break` and `/cigar:mode`.
- CLI: `cigar status` and `cigar mode`.

**Auto-trigger spike (D-007)**
- Timeboxed to one focused attempt.
- **Question:** can a plugin mod start a reset without the developer? Try these in order, and record what each does:
  1. `$.prompt.submit` with `/clear`
  2. `$.prompt.submit` with `/compact`, with and without `asUser`
  3. any mods API method that the reference documents for this
- **If one works reliably:** ship `mods/` and allow `auto` mode, off by default. The flow is: the nudge triggers a `take_break` (the mod can draft the handoff from the live conversation with `$.model.fork` if the agent doesn't call the tool), then the reset fires, then the handoff is restored.
- **If none works:** keep `suggest` and `observe` only, and `/cigar:mode auto` explains why it's unavailable.
- Either way, write the findings into D-007.

**Gate**
- [ ] `ruff` and `pytest` are green: unit, replay, MCP conformance, fail-open and performance tests.
- [ ] The performance result is reported: hook p95 < 150 ms on a 5 MB transcript.
- [ ] Fail-open is proven: a corrupt DB, a bad transcript and garbage on stdin each exit 0 with no output, and are logged.
- [ ] End-to-end with `claude --plugin-dir` in a scratch project, following SRS §7 steps 1–5. Claude Code runs what it can in headless mode, and gives the owner a short checklist for the interactive `/clear` step. The step is marked pending until the owner confirms it.
- [ ] The D-007 spike result is recorded with evidence.
- [ ] D-014 findings are recorded.
- [ ] `docs/sessions/1/`: test output, the performance numbers, one sample handoff file, and a log excerpt of a nudge firing.

## Session 2 · Learn, share, package, launch

**Learn**
- `knee.py` as in architecture §9. Learned knees replace defaults at medium confidence or above.
- `report.py`: the text report and the self-contained HTML report.
- `/cigar:report` and `cigar report`.
- A **seed data generator** (`scripts/simulate.py`). It fakes several weeks of sessions with a known knee, so the estimator and report can be tested before real data exists. The estimator test asserts that it recovers the planted knee within ±10k tokens.

**Share**
- `share.py`, `cigar share` (with `--dry-run`) and `/cigar:share`.
- The GitHub issue form `.github/ISSUE_TEMPLATE/curve.yml`.
- `scripts/ingest_curves.py`, and the `data/curves/README.md` schema.

**Any agent**
- The `record_event` MCP tool, and `cigar.track` for custom Python agent loops (about 20 lines in the README).
- Publish `cigar-mcp` as an entry point.
- Test with at least one non-Claude MCP client available on the owner's machine, and document only what was tested (FR-M3).

**Package and launch**
- `.claude-plugin/marketplace.json`. Install must work as `/plugin marketplace add MYoussef885/cigar-break` followed by `/plugin install cigar@cigar-break`. Verify the exact syntax on the current version.
- PyPI: check that the name `cigar-break` is free (D-012), build with `uv build`, publish to TestPyPI, then to PyPI. Stop for the owner's PyPI token.
- A GitHub Actions CI matrix (architecture §13) and a tagged release `v0.1.0`.
- The README, launch-ready (FR-P3), including the privacy section.
- `docs/demo-script.md`: a 30-second demo for the owner to record.
- `docs/launch/`: drafts for X, Reddit (r/ClaudeAI) and Show HN.
- Make the repo **public**. Stop and confirm with the owner first.

**Gate**
- [ ] Tests green on the CI matrix. The estimator recovers the planted knee within ±10k tokens.
- [ ] A fresh install, in a clean temp `HOME` with the plugin pulled from GitHub, works in two commands. The transcript is saved as evidence.
- [ ] `/cigar:report` renders from simulated data, and from the owner's real data if it exists. The HTML is screenshotted at desktop width into `docs/sessions/2/`.
- [ ] `cigar share --dry-run` prints a payload, and a check confirms it contains no paths, project names or code.
- [ ] The MCP server works outside the plugin from a PyPI install (or TestPyPI if PyPI is still pending).
- [ ] The repo is public, `v0.1.0` is tagged, and the launch drafts are in `docs/launch/`.
- [ ] The owner records the demo GIF. Mark this as pending until confirmed.

## Later (not in v0.1)
- Teams of agents: a shared handoff store, staggered breaks, an orchestrator API.
- An OpenAI-compatible proxy, so detection and reset work for any agent.
- A public curves page or Hugging Face dataset, built from `data/curves/`.
- Optional quality probes judged by an LLM.
- A submission to Anthropic's plugin directory.

---

## Session report (required at the end of every session)

```
## Session N report
**Completed:** …
**Files changed:** …
**Decisions made:** … (also appended to decisions.md)
**Problems / deviations:** …
**Gate status:** ✅ / ❌ / ⏳ for each gate item, with evidence
**Questions for Claude Chat:** …
**Next steps:** … (do not start the next session)
```
