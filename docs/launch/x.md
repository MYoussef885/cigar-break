# X / Twitter thread (draft)

Attach `docs/demo.gif` to post 1.

---

**1/**
Your coding agent gets worse as its context fills up: failed tool calls, re-reading files it already read, undoing its own edits.

I built Cigar, an open-source Claude Code plugin that notices, has the agent write a handoff, clears the context and picks up where it left off. 🚬

[demo.gif]

**2/**
It uses only signals the session already produces, so it costs zero extra tokens:
- failed calls
- repeated identical calls
- re-reads with no edit in between
- undone edits
- failed tests/builds/lint

…combined with how close the context is to the model's "knee".

**3/**
When the score crosses the line, Claude gets a short factual note with the evidence and a `take_break` tool. It writes a structured handoff (goal, status, decisions, files, next steps, gotchas). You type /clear and the handoff is restored into the fresh session.

**4/**
Auto mode (opt-in, terminal) does the /clear for you, but only after a handoff is saved. No handoff, no reset. Ever.

**5/**
The part I'm most curious about: Cigar learns where *your* sessions start to slip, per model. `/cigar:report` draws your curve.

If you opt in, `cigar share` shows you the exact anonymous payload and opens a prefilled GitHub issue. I'd love an open dataset of where agents get tired.

**6/**
Local-only, no telemetry, no dependencies beyond Python 3.11+.

Install in Claude Code:
/plugin marketplace add MYoussef885/cigar-break
/plugin install cigar@cigar-break

github.com/MYoussef885/cigar-break
