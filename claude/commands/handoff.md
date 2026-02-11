# Handoff

Create a handoff summary for continuing this work in a fresh session.

## Instructions

Generate a concise handoff document that captures:

### Current State
- What task/feature is being worked on
- Branch name and any relevant PR/issue links
- Current status (in progress, blocked, near completion)

### Key Decisions Made
- Architectural choices and why
- Trade-offs considered
- Anything that was tried and didn't work

### Files Modified
- List files changed in this session
- Note any files that need attention but weren't touched

### What's Left
- Remaining tasks in priority order
- Known issues or blockers
- Tests that need to be written/fixed

### Context to Preserve
- Important findings from exploration
- Gotchas discovered
- Relevant code patterns found

## Output

Write the handoff to a timestamped file: `tmp/handoffs/handoff-YYYY-MM-DD-HHMM.md`

Create the directory if it doesn't exist. Also output the summary to the conversation so the user can review it.

$ARGUMENTS - Optional notes about what to emphasize in the handoff
