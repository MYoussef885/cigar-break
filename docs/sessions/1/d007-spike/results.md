# D-007 spike: which plugin mod calls start a reset

Each run: interactive `claude` in a PTY, probe plugin + spike mod loaded with --plugin-dir. After the first turn the mod tries one strategy;
a probe SessionStart hook injects `MANGO-42` on source clear/compact; the next prompt asks for the code word.

| strategy | build | hook events after the turn | reply to the code-word question |
|---|---|---|---|
| `command-clear` | CLI 2.1.288 | SessionEnd(clear) 0cc623f1 → SessionStart(clear) cfc0a845 | MANGO-42 |
| `command-clear` | CLI 2.1.288 (repeat) | SessionEnd(clear) 496c6532 → SessionStart(clear) 1d07e567 | MANGO-42 |
| `command-clear` | 2.1.309 (VS Code-bundled binary, run in a terminal) | SessionEnd(clear) d41b6f81 → SessionStart(clear) 24bc35b2 | MANGO-42 |
| `command-compact` | CLI 2.1.288 | PreCompact(manual) 5c61f131 → SessionStart(compact) 5c61f131 | MANGO-42 |
| `session-compact` | CLI 2.1.288 | PreCompact(manual) c25106e1 → SessionStart(compact) c25106e1 | MANGO-42 |
| `session-compact` | 2.1.309 (VS Code-bundled binary, run in a terminal) | PreCompact(manual) 3df2d05e → SessionStart(compact) 3df2d05e | MANGO-42 |
| `submit-clear-asuser` | CLI 2.1.288 | (no reset: refused by the host, see log) | NONE |
| `submit-clear` | CLI 2.1.288 | (no reset: refused by the host, see log) | NONE |
| `submit-compact-asuser` | CLI 2.1.288 | (no reset: refused by the host, see log) | NONE |
| `submit-compact` | CLI 2.1.288 | (no reset: refused by the host, see log) | NONE |

Mod log (spike.log):
```
=== submit-clear cli288
2026-10-23T21:24:10.152Z turn.complete main; strategy=submit-clear; session=edca0264-69ed-4fea-a947-0f407473c2ca
2026-10-23T21:24:14.161Z submit-clear rejected: HooksError: cigarspike: prompt.submit: submits a prompt to the model; a text beginning with / would run a command as the user; run one with $.command.run({ command }) (host check)
=== submit-clear-asuser cli288
2026-10-23T21:26:10.419Z turn.complete main; strategy=submit-clear-asuser; session=5bd863e7-ee82-442b-a113-da0261a573e8
2026-10-23T21:26:14.424Z submit-clear-asuser rejected: HooksError: cigarspike: prompt.submit: submits a prompt to the model; a text beginning with / would run a command as the user; run one with $.command.run({ command }) (host check)
=== submit-compact cli288
2026-10-23T21:28:12.416Z turn.complete main; strategy=submit-compact; session=06bdb3ef-70a2-41cc-881c-23a8d890c05b
2026-10-23T21:28:16.418Z submit-compact rejected: HooksError: cigarspike: prompt.submit: submits a prompt to the model; a text beginning with / would run a command as the user; run one with $.command.run({ command }) (host check)
=== submit-compact-asuser cli288
2026-10-23T21:30:17.908Z turn.complete main; strategy=submit-compact-asuser; session=0bc4ddb9-edff-483d-af6e-6030c37a498a
2026-10-23T21:30:21.916Z submit-compact-asuser rejected: HooksError: cigarspike: prompt.submit: submits a prompt to the model; a text beginning with / would run a command as the user; run one with $.command.run({ command }) (host check)
=== session-compact cli288
2026-10-23T21:32:16.482Z turn.complete main; strategy=session-compact; session=c25106e1-eb56-4b4a-978a-4fee2efddfb3
2026-10-23T21:32:28.722Z session-compact resolved: {"messages":[{"role":"user","text":"This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n\n<tools-used-before-summary>Read</tools-used-before-summary>\nSummary:\n1. Primary Request and Intent:\n   The; session now=c25106e1-eb56-4b4a-978a-4fee2efddfb3
ALLDONE
=== command-clear cli288
2026-10-23T21:34:58.502Z turn.complete main; strategy=command-clear; session=0cc623f1-fc8d-4d6d-b02c-758d7ae7ce8e
2026-10-23T21:35:03.174Z command-clear resolved: {"text":""}; session now=cfc0a845-738c-4721-b639-961701973d88
=== command-clear cli288b
2026-10-23T21:36:54.963Z turn.complete main; strategy=command-clear; session=496c6532-88d5-4b0e-a7cd-6e2ba93c78b1
2026-10-23T21:36:59.026Z command-clear resolved: {"text":""}; session now=1d07e567-4501-4e39-99e4-4fa41f3524b1
=== command-compact cli288
2026-10-23T21:38:57.163Z turn.complete main; strategy=command-compact; session=5c61f131-29b8-4ffd-9c1c-0649c1dd06c8
2026-10-23T21:39:06.119Z command-compact resolved: {}; session now=5c61f131-29b8-4ffd-9c1c-0649c1dd06c8
=== command-clear v309
2026-10-23T21:40:59.133Z turn.complete main; strategy=command-clear; session=d41b6f81-2d81-45da-b1e3-f4d5035c6018
2026-10-23T21:41:03.200Z command-clear resolved: {"text":""}; session now=24bc35b2-64b5-48c7-8d73-089439b0b7bc
=== session-compact v309
2026-10-23T21:43:00.706Z turn.complete main; strategy=session-compact; session=3df2d05e-66b6-4cd3-a3c7-d53d2b432d3f
2026-10-23T21:43:11.100Z session-compact resolved: {"messages":[{"role":"user","text":"This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n\n<tools-used-before-summary>Read</tools-used-before-summary>\nSummary:\n1. Primary Request and Intent:\n   The; session now=3df2d05e-66b6-4cd3-a3c7-d53d2b432d3f
ALLDONE2
```
