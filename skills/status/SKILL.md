---
name: status
description: Show Cigar's fatigue score, context size, knee, recent signals and mode.
disable-model-invocation: true
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cigar" status`

Show the Cigar status above to the developer exactly as printed, in a code block, with no commentary.
