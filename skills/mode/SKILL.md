---
name: mode
description: Show or change Cigar's mode (suggest, observe or auto).
argument-hint: "[suggest|observe|auto]"
disable-model-invocation: true
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cigar" mode "$ARGUMENTS"`

Show the output above to the developer exactly as printed, with no commentary.
