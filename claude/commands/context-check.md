# Context Check

Assess current context health and recommend action.

## Instructions

Evaluate the conversation and provide:

### Context Assessment
1. **Conversation length** - Estimate how much context has been used (short/medium/long/very long)
2. **Topic drift** - Has the conversation stayed focused or wandered?
3. **Stale context** - Is there debugging history, abandoned approaches, or irrelevant exploration polluting context?
4. **Active threads** - How many distinct tasks/topics are currently "open"?

### Recommendation

Based on assessment, recommend ONE of:
- **Continue** - Context is healthy, keep going
- **Compact** - Run `/compact` to summarize and continue
- **Handoff** - Context is full, run `/handoff` then start fresh session
- **Clear** - Topic is complete, `/clear` and start new task
- **Restore** - Suggest using double-escape to restore conversation only (keep code, trim context)

### If Handoff/Clear Recommended

Provide a one-paragraph summary of current state that could be copy-pasted to start a new session.

## Usage

Run `/context-check` when:
- You've been working for 30+ minutes
- After fixing a complex bug
- Before starting a new subtask
- When responses seem to be degrading
