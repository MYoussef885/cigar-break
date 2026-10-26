---
name: share
description: Share your anonymous Cigar curve. Shows the exact payload first; nothing is sent without confirm.
argument-hint: "[confirm]"
disable-model-invocation: true
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cigar" share --skill "$ARGUMENTS" 2>&1 || true`

Show the output above to the developer exactly as printed, in a code block, with no commentary.
