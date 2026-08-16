#!/usr/bin/env bash
cmd=$(jq -r '.tool_input.command // ""')
if echo "$cmd" | grep -qE 'gh (pr|issue) comment|gh pr review|gh api [^;|&]*(comments|reviews)[^;|&]*(-f |-F |--field|--raw-field|-X POST|--method POST|--input)'; then
  if echo "$cmd" | grep -q 'gh pr comment' && echo "$cmd" | grep -qE '\[e2e (un)?resolved\]'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"e2e pipeline finding comment - auto-allowed"}}'
  else
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This posts to GitHub as Joel - confirm to send"}}'
  fi
fi
exit 0
