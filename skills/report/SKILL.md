---
name: report
description: Show where your agent gets tired (signal rate by context size, per model).
disable-model-invocation: true
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cigar" report --html 2>&1 || true`

Show the Cigar report above to the developer exactly as printed, in a code block, with no commentary. Then give the HTML report path on its own line.
