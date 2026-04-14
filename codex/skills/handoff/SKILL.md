---
name: handoff
description: Create a concise handoff summary for continuing work in a fresh Codex session. Use when the user says handoff, create a handoff, or wants a summary to continue later.
---

# Handoff

Create a concise handoff for a fresh session.

If the user provided arguments, treat them as notes about what to emphasize.

## Gather information

Run:
1. `git branch --show-current`
2. `git status`
3. `git diff --stat`
4. `git log --oneline -10`

Then review the current conversation for:
- decisions made
- attempts that failed
- relevant findings and gotchas

## Instructions

Keep the handoff under 500 words.

Write it to:

```text
tmp/handoffs/handoff-YYYY-MM-DD-HHMM.md
```

Create the directory if needed.

## Template

```markdown
# Handoff — [short task description]

**Branch:** `branch-name`
**Status:** [in progress / blocked / near completion]
**Date:** YYYY-MM-DD

## Current State
- What is being worked on
- Relevant PR or issue links
- Current status summary

## Key Decisions Made
- Architectural choices and why
- Trade-offs considered
- Things tried that did not work

## Files Modified
- Files changed in this session
- Files that still need attention

## What's Left
- Remaining tasks in priority order
- Known issues or blockers
- Tests still needed

## Context to Preserve
- Important findings
- Gotchas
- Relevant code patterns
```

Also output the summary in the conversation after writing the file.
