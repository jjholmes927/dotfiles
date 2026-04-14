---
name: context-check
description: Assess Codex session context health and recommend whether to continue, summarize, hand off, or start a fresh session. Use when the user says context check, how is context looking, is context getting messy, should we start fresh, should we hand off, responses seem to be degrading, or explicitly says use context-check.
---

# Context Check

Assess current context health and recommend the next move.

## Assessment

Evaluate:
1. Conversation length
2. Topic drift
3. Stale context
4. Number of active threads

## Recommendation

Choose one:

| Situation | Recommendation |
|-----------|----------------|
| Short session, focused topic | Continue |
| Medium or long session, still focused | Summarize and continue |
| Very long session, task complete | Start fresh |
| Very long session, work still in progress | Handoff |
| Long session with lots of stale debugging or abandoned attempts | Fresh session with preserved filesystem state |

## Output format

Use this structure:

```markdown
## Context Health

| Dimension | Status |
|-----------|--------|
| Length | short / medium / long / very long |
| Focus | focused / some drift / scattered |
| Stale context | none / some / significant |
| Open threads | short count and description |

## Recommendation: <choice>

<1-2 sentences explaining why>

## Session Summary

<only include this section when recommending handoff or a fresh session>
```

If recommending a new session, include a short summary the user can paste into the new thread.
