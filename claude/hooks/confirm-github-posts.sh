#!/usr/bin/env bash
input=$(cat)
cmd=$(jq -r '.tool_input.command // ""' <<<"$input")
mode=$(jq -r '.permission_mode // ""' <<<"$input")
posts='gh (pr|issue) comment|gh pr review|gh api [^;|&]*(comments|reviews)[^;|&]*(-f |-F |--field|--raw-field|-X POST|--method POST|--input)'
agent_comment='^[[:space:]]*gh-agent[[:space:]]+[^[:space:]]+[[:space:]]+pr[[:space:]]+comment([[:space:]]|$)'
other_gh='(^|[^[:alnum:]_-])gh[[:space:]]'
nl=$'\n'
unchained() {
  case $1 in
    *';'* | *'&'* | *'|'* | *'`'* | *'$('* | *'<'* | *'>'* | *"$nl"*) return 1 ;;
  esac
}
if [[ $cmd =~ $agent_comment ]] && ! [[ $cmd =~ $other_gh ]] && unchained "$cmd"; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Single gh-agent pr comment posts as the agent bot, not Joel - auto-allowed"}}'
elif echo "$cmd" | grep -qE "$posts"; then
  if [[ $cmd =~ ^[[:space:]]*gh[[:space:]]+pr[[:space:]]+comment[[:space:]] ]] && [ "$(grep -oE "$other_gh" <<<"$cmd" | wc -l)" -eq 1 ] && unchained "$cmd" && echo "$cmd" | grep -qE '\[e2e (un)?resolved\]'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"e2e pipeline finding comment - auto-allowed"}}'
  elif [ "$mode" = "bypassPermissions" ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"This posts to GitHub as Joel and bypass mode cannot confirm it - ask Joel in chat first, then have him post it or switch out of bypass mode"}}'
  else
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This posts to GitHub as Joel - confirm to send"}}'
  fi
elif [[ $cmd == *gh-agent* ]] && sed -E 's/gh-agent[[:space:]]+[^[:space:]]+/gh/g' <<<"$cmd" | grep -qE "$posts"; then
  if [ "$mode" = "bypassPermissions" ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"This posts to GitHub as the agent bot in a form only Joel can approve - only a single, unchained gh-agent <owner/repo> pr comment --body-file <file> is auto-allowed"}}'
  else
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This posts to GitHub as the agent bot - confirm to send"}}'
  fi
fi
exit 0
