# D-014 probe evidence (Claude Code CLI 2.1.288, macOS, 2026-10-24)

Raw hook stdin captured by a throwaway probe plugin (keys and truncated values; transcript and scratch paths elided).

## SessionStart (startup)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `hook_event_name`: "SessionStart"
- `source`: "startup"

## PostToolUse (Read)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUse"
- `tool_name`: "Read"
- `tool_input`: {"file_path": "<scratch>…
- `tool_response`: {"type": "text", "file": {"filePath": "<scratch>…
- `tool_use_id`: "toolu_011RWv1h2Z6iwTz5XsiBfj5M"
- `duration_ms`: 2

## PostToolUse (Edit)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUse"
- `tool_name`: "Edit"
- `tool_input`: {"file_path": "<scratch>…
- `tool_response`: {"filePath": "<scratch>/…
- `tool_use_id`: "toolu_01Xxin1ecohA9dfBnNE4K4nP"
- `duration_ms`: 5

## PostToolUseFailure (Bash)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUseFailure"
- `tool_name`: "Bash"
- `tool_input`: {"command": "sh -c 'echo failing; exit 3'", "description": "Run failing shell command"}
- `tool_use_id`: "toolu_01HVACFTqhDFeQEFEi7JHTX8"
- `error`: "Exit code 3\nfailing"
- `is_interrupt`: false
- `duration_ms`: 384

## PostToolUse (Write)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUse"
- `tool_name`: "Write"
- `tool_input`: {"file_path": "<scratch>…
- `tool_response`: {"type": "create", "filePath": "<scratch>…
- `tool_use_id`: "toolu_017Ge6mCXMZfEbeKTDrjqhnT"
- `duration_ms`: 6

## PostToolUseFailure (Read)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUseFailure"
- `tool_name`: "Read"
- `tool_input`: {"file_path": "/nonexistent/zzz.txt"}
- `tool_use_id`: "toolu_01Y2WP9xwWqyx5uiKL3DzRzq"
- `error`: "File does not exist. Note: your current working directory is <scratch>…
- `is_interrupt`: false
- `duration_ms`: 1

## PostToolUse (Bash) from a subagent
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `agent_id`: "a9fe9deb462768338"
- `agent_type`: "general-purpose"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUse"
- `tool_name`: "Bash"
- `tool_input`: {"command": "ls"}
- `tool_response`: {"stdout": "a.txt\nb.txt", "stderr": "", "interrupted": false, "isImage": false, "noOutputExpected": false}
- `tool_use_id`: "toolu_01CDEVq7xPbxZ3Z3KcWdkcse"
- `duration_ms`: 34

## PostToolUse (Agent)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "PostToolUse"
- `tool_name`: "Agent"
- `tool_input`: {"description": "Run ls and report", "prompt": "Run 'ls' in bash (in the current working directory) and report the outpu…
- `tool_response`: {"status": "completed", "prompt": "Run 'ls' in bash (in the current working directory) and report the output.", "agentId…
- `tool_use_id`: "toolu_01S3kktAmZs4cEzWnwV9Ejqd"
- `duration_ms`: 3006

## Stop
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `permission_mode`: "bypassPermissions"
- `effort`: {"level": "medium"}
- `hook_event_name`: "Stop"
- `stop_hook_active`: false
- `background_tasks`: []
- `session_crons`: []

## SessionEnd (other)
- `session_id`: "9a2b8601-2c57-426a-827f-c4da371c97cf"
- `prompt_id`: "d97ddac3-bd2b-405d-8290-25bf00e78542"
- `hook_event_name`: "SessionEnd"
- `reason`: "other"

## SessionStart (clear)
- `session_id`: "cfc0a845-738c-4721-b639-961701973d88"
- `hook_event_name`: "SessionStart"
- `source`: "clear"

## PreCompact (manual)
- `session_id`: "5c61f131-29b8-4ffd-9c1c-0649c1dd06c8"
- `prompt_id`: "1d8e5ad0-b54a-4809-9459-eba3117ff7f5"
- `hook_event_name`: "PreCompact"
- `trigger`: "manual"
- `custom_instructions`: null

## SessionStart (compact)
- `session_id`: "5c61f131-29b8-4ffd-9c1c-0649c1dd06c8"
- `prompt_id`: "1d8e5ad0-b54a-4809-9459-eba3117ff7f5"
- `hook_event_name`: "SessionStart"
- `source`: "compact"
- `model`: "claude-sonnet-5-5"

