# r/ClaudeAI post (draft)

**Title:** I made a Claude Code plugin that notices when a long session starts slipping, saves a handoff, and restores it after /clear

**Flair:** Built with Claude / Productivity (whichever fits)

---

Long Claude Code sessions have a point where things go downhill: tool calls start failing, Claude re-reads files it already read, undoes edits it made ten minutes ago. I usually noticed twenty minutes too late, or I'd /clear too early and spend ten minutes re-explaining.

**Cigar** is an open-source plugin that watches for that decline and helps Claude take a "cigar break":

1. **Detect.** After each tool call it looks at the last 20 calls for failed calls, repeated identical calls, re-reads with no edit in between, undone edits and failed tests/builds/lint, and weighs them against how full the context is relative to the model's knee. Zero extra tokens: it only uses what the hooks and transcript already have.
2. **Nudge.** When the score crosses the threshold, Claude gets a short, factual note with the evidence ("context is at 142k; the knee for this model is ~120k; in the last 20 tool calls: 4 failed, 3 files re-read…") and you get a one-line message. Max three per session.
3. **Hand off.** Claude calls a `take_break` tool and writes a structured handoff: goal, status, done, decisions, files, next steps, gotchas. It's saved in your project's `.cigar/` folder (which git-ignores itself).
4. **Restore.** You type /clear; the handoff is injected into the fresh session, so Claude's first answer already knows the goal and the next step.

There's also an **opt-in auto mode** (terminal only so far) that does the /clear itself, but only once a handoff is actually saved. If Claude ignores the nudge, nothing gets reset.

**It learns your knee.** Every model starts with a default (e.g. ~100k for Sonnet, ~120k for Opus on a 200k window). Over a few weeks Cigar learns where *your* sessions start to slip, per model, and `/cigar:report` draws the curve. If you want, `cigar share` shows you the exact anonymous payload (model, counts per 10k-token bucket, the knee; no paths, code or prompts) and opens a prefilled GitHub issue, so we can build an open dataset of where agents get tired.

**Privacy:** everything stays local, no telemetry, no network calls. It stores hashes of tool arguments, never prompts or file contents.

Install:
```
/plugin marketplace add MYoussef885/cigar-break
/plugin install cigar@cigar-break
```
Needs Python 3.11+ somewhere on the machine (it finds it even if `python3` is older).

What's verified so far: the terminal CLI on macOS (suggest and auto). The VS Code panel works for suggest mode in my testing [owner: keep this line only if the VS Code checklist passed]. Linux/Windows pass the test suite in CI but I haven't run a live session there; reports welcome.

Repo: https://github.com/MYoussef885/cigar-break

Feedback I'd love: false nudges (when it nagged and you didn't think it should), and whether the default knees match your experience.
