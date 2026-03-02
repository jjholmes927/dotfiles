---
description: "Assess current context health and recommend action. Use when the user says 'context check', 'how's my context', or when responses seem to be degrading."
disable-model-invocation: true
---

# Context Check

Assess current context health and recommend action.

## Instructions

Evaluate the conversation and provide a structured assessment.

### Context Assessment

Analyze these four dimensions:

1. **Conversation length** - Estimate how much context has been used (short/medium/long/very long)
2. **Topic drift** - Has the conversation stayed focused or wandered across unrelated topics?
3. **Stale context** - Is there debugging history, abandoned approaches, or irrelevant exploration polluting context?
4. **Active threads** - How many distinct tasks/topics are currently "open"?

### Recommendation

Based on the assessment, recommend ONE of the five options below. Use the decision framework to choose:

| Situation | Recommendation |
|-----------|---------------|
| Short conversation, focused topic | **Continue** - Context is healthy, keep going |
| Medium-long conversation, still focused | **Compact** - Run `/compact` to summarize and free up space |
| Very long conversation, topic is complete | **Clear** - Run `/clear` and start a new task cleanly |
| Very long conversation, work still in progress | **Handoff** - Run `/handoff` to generate a summary, then start a fresh session with that context |
| Long conversation with stale debugging, abandoned approaches, or noise | **Restore** - Use double-escape (`Esc Esc`) to reset the conversation while preserving the codebase state. This discards the entire conversation history but keeps all file changes on disk, giving a clean context without losing work. |

### If Handoff or Clear Is Recommended

Provide a one-paragraph summary of the current state that could be copy-pasted to start a new session. Include what was accomplished, what remains, and any important decisions or context that would otherwise be lost.

### Output Format

Structure every response exactly like this:

```
## Context Health

| Dimension | Status |
|-----------|--------|
| Length | [short / medium / long / very long] |
| Focus | [focused / some drift / scattered] |
| Stale context | [none / some / significant] |
| Open threads | [count and brief description] |

## Recommendation: [Continue / Compact / Clear / Handoff / Restore]

[1-2 sentences explaining why this recommendation fits the current state.]

## Session Summary (if Handoff or Clear)

[One paragraph summarizing current state for a new session, if applicable.]
```

## When to Invoke

Run this command:
- After working for 30+ minutes in a single session
- After fixing a complex bug with multiple attempts
- Before starting a new subtask in a long conversation
- When responses seem to be degrading in quality or relevance
