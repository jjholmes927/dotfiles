---
name: save-permissions
description: Save recurring approved OpenCode shell commands as narrowly scoped permission rules when asked to remember or save permissions.
---

Use commands and approvals visible in the current OpenCode conversation. Do not
scan Claude/Codex logs or assume OpenCode's internal database schema.

1. Read the global `opencode.json` and any `opencode.jsonc` override.
2. Identify recurring commands the user has approved and show the proposed
   command patterns. Use narrow patterns such as `gh pr view *`.
3. Add only missing approved patterns under `permission.bash`, with value
   `allow`. Preserve unrelated settings and existing deny/ask rules; matching
   rules are order-sensitive. Do not widen a rule that requires approval.
4. Back up the file before editing and report exactly which patterns changed.

Never add broad interpreter, destructive, privilege-escalation, secret-reading,
or publication patterns. Do not save compound shell strings containing pipes,
substitutions, or command separators as reusable approvals. If there is no
evidence of a prior approval, ask before persisting that candidate. OpenCode's
permission dialog also provides an Always option for approvals during a session.
