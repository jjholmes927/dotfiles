#!/usr/bin/env bash
cmd=$(jq -r '.tool_input.command // ""')
if echo "$cmd" | grep -qE 'gh (pr|issue) comment|gh pr review|gh api [^;|&]*(comments|reviews)[^;|&]*(-f |-F |--field|--raw-field|-X POST|--method POST|--input)'; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This posts to GitHub as Joel - confirm to send"}}'
fi
exit 0
