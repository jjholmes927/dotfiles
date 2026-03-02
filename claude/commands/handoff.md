---
description: "Create a handoff summary for continuing work in a fresh Claude Code session. Use when the user says 'handoff', 'create a handoff', or needs to continue work in a new session."
disable-model-invocation: true
allowed-tools: Read, Write, Bash
argument-hint: [emphasis notes]
---

# Handoff

Create a handoff summary for continuing this work in a fresh session.

If the user provided arguments, treat them as notes about what to emphasize in the handoff: $ARGUMENTS

## Gathering Information

Before generating the handoff, run these commands to collect the current state:

1. `git branch --show-current` — get the branch name
2. `git status` — find modified, staged, and untracked files
3. `git diff --stat` — see what changed and how much
4. `git log --oneline -10` — see recent commits for context

Then review the conversation history for decisions made, things that were tried, and any findings or gotchas discovered during the session.

## Instructions

Keep the handoff under 500 words. Prioritize actionable information over narrative.

Generate a concise handoff document using this template:

```markdown
# Handoff — [short task description]

**Branch:** `branch-name`
**Status:** [in progress / blocked / near completion]
**Date:** YYYY-MM-DD

## Current State
- What task/feature is being worked on
- Any relevant PR/issue links
- Current status summary

## Key Decisions Made
- Architectural choices and why
- Trade-offs considered
- Anything that was tried and didn't work

## Files Modified
- List files changed in this session
- Note any files that need attention but weren't touched

## What's Left
- Remaining tasks in priority order
- Known issues or blockers
- Tests that need to be written/fixed

## Context to Preserve
- Important findings from exploration
- Gotchas discovered
- Relevant code patterns found
```

## Output

Write the handoff to a timestamped file: `tmp/handoffs/handoff-YYYY-MM-DD-HHMM.md`

Create the directory if it doesn't exist. Also output the summary to the conversation so the user can review it.
