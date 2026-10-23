---
name: break
description: Write a Cigar handoff now, then show the /clear instruction.
disable-model-invocation: true
---
The developer asked for a Cigar break. Call the `take_break` tool (cigar MCP server) now with a complete handoff of this session: goal, status, done, decisions, files (path and a one-line note each), next_steps (the immediate action first), open_questions and gotchas. Write it so that a fresh session with no other context can continue the work.

When the tool succeeds, tell the developer what it says to type: /clear for a full fresh start, or /compact to keep a summary.
