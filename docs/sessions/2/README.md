# Session 2 evidence

Dates are 2026-10-26, on macOS 26.0.1 (Apple M4) with Claude Code 2.1.309. Scratch paths are shown as `<scratch>`, the repo as `<checkout>`.

| Gate item | Status | Evidence |
|---|---|---|
| Tests green on the CI matrix; estimator recovers the planted knee within ±10k | ✅ local, CI below | [tests.txt](tests.txt) (217 passed, 1 skipped, ruff clean, 2026-10-29); [estimator.txt](estimator.txt): 160/160 seeded runs within ±10k, spurious knees on flat data 1/30 (40 sessions) and 0/30 (120 sessions). CI: [run 40878511769](https://github.com/MYoussef885/cigar-break/actions/runs/40878511769) on `8ff9914`, all 7 jobs green (later commits change docs only). The run on `daea486` was cancelled by that push (`cancel-in-progress`). |
| No-handoff-no-clear test (D-026) | ✅ | `tests/test_auto_mod.py` runs the real `mods/auto.ts` under node: 80 tool calls and 3 nudges in auto mode never clear; a `take_break` that reported success without a saved handoff never clears; one saved handoff clears exactly once |
| Fresh install in a clean temp `HOME`, two commands | ⏳ GitHub run after the public step | [fresh-install-local.txt](fresh-install-local.txt): both commands, inventory, MCP health, hooks, and the only-old-`python3` case (one warning, no errors), from a local-path marketplace. `scripts/fresh_install_check.sh MYoussef885/cigar-break` repeats it from GitHub. |
| `/cigar:report` from simulated data, and real data if it exists; desktop screenshot | ✅ simulated (checklist step 3, from the screenshot); ⏳ real | [report-simulated.txt](report-simulated.txt), [report-simulated.html](report-simulated.html), [report-desktop.png](report-desktop.png) (1440 px). There is still no `~/.cigar/` on this machine (re-checked 2026-10-29), so there is no real data to report; the empty-store report is covered by `tests/test_report.py::test_empty_report`. |
| `cigar share --dry-run` prints a payload with no paths, project names or code | ✅ | [share-dry-run.txt](share-dry-run.txt); `tests/test_share.py::test_payload_contains_no_paths_projects_or_ids` feeds real hook events with paths, a named project folder and session IDs, and checks none of them appear in the payload or the issue URL |
| MCP server outside the plugin from a PyPI (or TestPyPI) install | ✅ wheel; ⏳ TestPyPI | [mcp-standalone.txt](mcp-standalone.txt): the built wheel in a clean venv, driven by the official MCP Python SDK 2.3.0 client. CI's `package` job repeats it on Ubuntu. Publishing is trusted publishing from [release.yml](../../../.github/workflows/release.yml) (D-038), waiting on owner stop 1. |
| Repo public, `v0.1.0` tagged, launch drafts | ⏳ stop 2; drafts ✅ | [docs/launch/](../../launch/) |
| VS Code panel checklist (D-026) | ⏳ owner | Below |
| Demo GIF | ⏳ postponed until after launch (owner, 2026-10-29) | [docs/demo-script.md](../../demo-script.md); the README no longer shows it |

D-027: every probe ran with a temp `HOME`; `scripts/config_guard.py` diffs before and after were clean each time (see the end of [fresh-install-local.txt](fresh-install-local.txt)).

## Owner checklist (about 10 minutes)

Do the steps in order; step 1 installs what steps 2 and 3 use.

**1. Fresh install from GitHub, two commands (2 min).** In a terminal, in any folder, start `claude` and type:
```
/plugin marketplace add MYoussef885/cigar-break
/plugin install cigar@cigar-break
```
Restart Claude Code, then type `/cigar:status`.
- [ ] Both commands succeed, and `/cigar:status` prints a `Cigar status` block.
- If the first command fails with an authentication error while the repo is still private, skip this step and do it right after the repo goes public.

**2. VS Code panel, `suggest` mode (4 min).** In a terminal:
```
mkdir -p ~/cigar-vscode/.claude && cd ~/cigar-vscode && git init -q
printf '{"env": {"CIGAR_KNEE_TOKENS": "20000", "CIGAR_MIN_TOKENS": "5000"}}\n' > .claude/settings.json
code .
```
Open the Claude Code panel and ask: *Create calc.py with add and mul, and test_calc.py with plain asserts; run it, then add div with a test.*
- [ ] The nudge is visible in the panel: a line starting `🚬 Cigar: this session shows fatigue`. (If none appears after about 15 tool calls, the project `env` didn't reach the hooks; add `knee_tokens = 20000` and `min_tokens = 5000` to `~/.cigar/config.toml` for this test and remove them afterwards, and tell me.)
- [ ] `/cigar:break` works: Claude saves a handoff and says to type `/clear`.
- [ ] After `/clear`, `🚬 Cigar: restored the handoff from .cigar/handoffs/…` appears, and asking *What were we doing, and what's next?* gets the goal and the next step.

**3. HTML report (1 min).** Done from the Session 2 evidence (2026-10-29).
- [x] `open ~/Documents/cigar-break/docs/sessions/2/report-simulated.html` shows "Where my agent gets tired" with two model tabs.
- [x] ~~In any Claude Code session, `/cigar:report` prints your real-data report~~ Not applicable yet: this machine has no `~/.cigar/`, so there is no real data. [report-desktop.png](report-desktop.png) shows the title and both model tabs.

**4. Demo GIF (3 min). Postponed until after launch.** Follow [docs/demo-script.md](../../demo-script.md) in a terminal and save the result as `docs/demo.gif`.
- [ ] `docs/demo.gif` exists. The README doesn't reference it yet; add it back to the README when it does.

Reply with what passed, or paste what differed. Afterwards: `rm -rf ~/cigar-vscode`.

## Owner stops (one action each)

1. **Trusted publishing (D-038), no tokens.** Add a *pending publisher* on test.pypi.org and on pypi.org (Account settings → Publishing → "Add a new pending publisher" → GitHub):

   | Field | test.pypi.org | pypi.org |
   |---|---|---|
   | PyPI Project Name | `cigar-break` | `cigar-break` |
   | Owner | `MYoussef885` | `MYoussef885` |
   | Repository name | `cigar-break` | `cigar-break` |
   | Workflow name | `release.yml` | `release.yml` |
   | Environment name | `testpypi` | `pypi` |

   Tell me when both are saved. I then run the workflow by hand (`gh workflow run release.yml`), which publishes 0.1.0 to TestPyPI, and verify a TestPyPI install with the MCP SDK client.
2. **Make the repo public.** Reply "go public" once step 2 above is done (so the README's VS Code claim is right; the demo GIF is postponed). I then run `gh repo edit MYoussef885/cigar-break --visibility public --accept-visibility-change-consequences`, push the `v0.1.0` tag (which publishes 0.1.0 to PyPI through `release.yml`), create the GitHub release from `docs/launch/release-notes.md`, and run the fresh install from GitHub.
