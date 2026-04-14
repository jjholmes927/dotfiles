---
name: log-error
description: Interview the user about a recent Codex or workflow mistake, identify what went wrong, and capture prevention strategies. Use when the user says log error, what went wrong, or wants to analyze a mistake.
---

# Log Error

Interview the user about a recent error to identify what went wrong and how to prevent it.

## Focus areas

Classify the mistake against these buckets:
- bad prompt
- context rot
- bad harnessing
- genuine model failure

## Workflow

1. Review the recent conversation and identify the visible failure mode.
2. Ask 5-8 specific questions about what the user asked for, what constraints were missing, and what signals were ignored.
3. Wait for answers before concluding.
4. Produce a short report with:
   - what happened
   - likely root cause
   - what the user could have done differently
   - what the agent could have handled better
   - a prevention checklist for next time

## Output format

```markdown
## Error Review

**What went wrong:** ...
**Primary cause:** ...

## User-side fixes
- ...

## Agent-side fixes
- ...

## Prevention checklist
- ...
```

Be direct. Do not soften the analysis into generic advice.
