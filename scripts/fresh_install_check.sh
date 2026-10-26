#!/usr/bin/env bash
# Fresh install check (roadmap S2 gate, D-027): install Cigar into a clean temp HOME
# with the two documented commands, then exercise the installed copy.
#
#   scripts/fresh_install_check.sh MYoussef885/cigar-break   # from GitHub (repo must be public)
#   scripts/fresh_install_check.sh /path/to/cigar-break      # from a local checkout
#
# Nothing touches the real ~/.claude or ~/.cigar: HOME points at a temp folder and
# every CLAUDE_* variable is dropped. Model calls need a login, which a temp HOME
# doesn't have, so this checks install, inventory, MCP health and the hooks; the
# owner's checklist covers a live session.
set -euo pipefail

SOURCE="${1:?usage: $0 <owner/repo | local path>}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/project"
git -C "$TMP/project" init -q
CLAUDE_BIN="$(command -v claude)"
run() {  # a clean environment: temp HOME, no CLAUDE_* variables
  env -i PATH="$PATH" HOME="$TMP/home" USER="${USER:-user}" TERM=dumb LANG=en_US.UTF-8 "$@"
}

echo "== claude $("$CLAUDE_BIN" --version) · HOME=<temp> · source $SOURCE"
cd "$TMP/project"
echo "\$ claude plugin marketplace add $SOURCE"
run "$CLAUDE_BIN" plugin marketplace add "$SOURCE"
echo "\$ claude plugin install cigar@cigar-break"
run "$CLAUDE_BIN" plugin install cigar@cigar-break
echo "\$ claude plugin details cigar"
run "$CLAUDE_BIN" plugin details cigar | sed -n '1,12p'
echo "\$ claude mcp list"
run "$CLAUDE_BIN" mcp list | sed "s|$TMP|<temp>|g; s|$HOME|~|g"

ROOT="$(run python3 -c 'import json,os
d = json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))
print(d["plugins"]["cigar@cigar-break"][0]["installPath"])')"
echo "== installed at ${ROOT/#$TMP/<temp>}"

hook() {  # hook <PATH> <event> <json>
  printf '%s' "$3" | env -i PATH="$1" HOME="$TMP/home" python3 -I -S "$ROOT/bin/cigar-hook" "$2"
  echo " [exit $?]"
}
START='{"session_id":"fresh-1","source":"startup","cwd":"'"$TMP/project"'"}'
TOOL='{"session_id":"fresh-1","cwd":"'"$TMP/project"'","tool_name":"Bash","tool_input":{"command":"ls"},"tool_response":{}}'

echo "== hooks with the normal PATH (python3 is $(python3 --version 2>&1); a 3.11+ is findable)"
hook "$PATH" session_start "$START"
hook "$PATH" post_tool_use "$TOOL"
grep -h "hook " "$TMP/home/.cigar/logs/"*.log | sed 's/^.*pid=[0-9]* //'

echo "== hooks when only an old python3 is on PATH (PATH=/usr/bin:/bin, $(/usr/bin/python3 --version 2>&1))"
rm -rf "$TMP/home/.cigar"
hook /usr/bin:/bin session_start "$START"
hook /usr/bin:/bin session_start "$START"
hook /usr/bin:/bin post_tool_use "$TOOL"
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | env -i PATH=/usr/bin:/bin HOME="$TMP/home" python3 -I -S "$ROOT/bin/cigar-mcp"
echo " [mcp exit $?]"
echo "== done"
