#!/usr/bin/env bash
input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)
[ -z "$tool" ] && exit 0

event=""
extra="{}"
if [ "$tool" = "Skill" ]; then
  skill=$(echo "$input" | jq -r '.tool_input.skill // empty')
  [ -z "$skill" ] && exit 0
  event="skill_invoked"
  extra=$(jq -n --arg s "$skill" '{skill: $s}')
elif [[ "$tool" == mcp__* ]]; then
  event="mcp_tool_invoked"
  server=$(echo "$tool" | awk -F'__' '{print $2}')
  extra=$(jq -n --arg t "$tool" --arg srv "$server" '{mcp_tool: $t, mcp_server: $srv}')
else
  exit 0
fi

key=$(security find-generic-password -s honeycomb-agent-traces -w 2>/dev/null)
[ -z "$key" ] && exit 0

host_alias=$(hostname -s)
case "$host_alias" in
  Joel-Holmes-Product-Engineering) host_alias="joel-work-mbp" ;;
esac

session=$(echo "$input" | jq -r '.session_id // "unknown"')
cwd=$(echo "$input" | jq -r '.cwd // "unknown"')
payload=$(jq -n --arg e "$event" --arg sid "$session" --arg c "$cwd" --arg h "$host_alias" --argjson x "$extra" \
  '{event: $e, session_id: $sid, cwd: $c, "host.name": $h} + $x')
curl -s -m 5 -X POST "https://api.eu1.honeycomb.io/1/events/workflow-ledger" \
  -H "X-Honeycomb-Team: ${key}" \
  -H "Content-Type: application/json" \
  -d "$payload" >/dev/null 2>&1 || true
exit 0
