---
name: save-permissions
description: Scan recent Codex shell activity, derive safe reusable command prefixes, and save them into Codex prefix rules. Use when the user says save permissions, save session permissions, add command approvals, remember these approvals, persist shell approvals, or explicitly says use save-permissions.
---

# Save Permissions

Translate recent safe shell usage into Codex prefix rules.

## Goal

Codex stores shell approvals in:

```text
~/.codex/rules/default.rules
```

This skill scans recent session logs for repeated safe commands and appends missing `prefix_rule(...)` entries.

## Sources to scan

Look in:
- `~/.codex/log/codex-tui.log`
- recent `~/.codex/sessions/**/*.jsonl`

Search for recorded `exec_command` calls and extract the command strings.

## Rules

- Never auto-add dangerous prefixes such as `rm`, `sudo`, `chmod`, `git reset`, `git clean`, or `git push`.
- Group commands into minimal safe prefixes.
- Prefer prefixes like `["gh", "pr", "view"]` over full one-off commands.
- If a command is too specific or risky, report it instead of saving it.

## Workflow

1. Parse recent shell commands from Codex logs and sessions.
2. Derive candidate prefixes.
3. Compare them against `~/.codex/rules/default.rules`.
4. Append only missing, safe entries in the form:

```text
prefix_rule(pattern=["gh", "pr", "view"], decision="allow")
```

5. Report:
   - rules added
   - dangerous commands skipped
   - commands that need manual review

Do not silently edit the rules file without showing the additions.
