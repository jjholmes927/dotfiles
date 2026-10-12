#!/usr/bin/env bash
input=$(cat)
cmd=$(jq -r '.tool_input.command // ""' <<<"$input")
mode=$(jq -r '.permission_mode // ""' <<<"$input")
if echo "$cmd" | grep -qE 'gh (pr|issue) comment|gh pr review|gh api [^;|&]*(comments|reviews)[^;|&]*(-f |-F |--field|--raw-field|-X POST|--method POST|--input)'; then
  if echo "$cmd" | grep -q 'gh pr comment' && echo "$cmd" | grep -qE '\[e2e (un)?resolved\]'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"e2e pipeline finding comment - auto-allowed"}}'
  elif [ "$mode" = "bypassPermissions" ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"This posts to GitHub as Joel and bypass mode cannot confirm it - ask Joel in chat first, then have him post it or switch out of bypass mode"}}'
  else
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This posts to GitHub as Joel - confirm to send"}}'
  fi
fi
exit 0
