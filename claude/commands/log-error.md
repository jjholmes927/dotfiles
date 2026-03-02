---
description: "Interview about a recent error to identify user mistakes and log prevention strategies. Use when the user says 'log error', 'what went wrong', or wants to analyze a mistake."
disable-model-invocation: true
argument-hint: [brief description of what went wrong]
---

# Log Error

Interview the user about an error that just occurred to identify what THEY did wrong and how to prevent it.

## Core Philosophy

Errors in agentic coding are almost always traceable to:
- **Bad Prompt** - Ambiguous, missing constraints, too verbose, wrong structure
- **Context Rot** - Didn't /clear, conversation too long, stale context
- **Bad Harnessing** - Wrong agent type, missing context for subagents, no guardrails

Focus primarily on user inputs as the controllable variable, but note genuine model-side failures when they occur.

## Instructions

**IMPORTANT: Steps 1-3 are INTERACTIVE. Ask questions and WAIT for user responses. Do NOT proceed to Step 4 until you have completed the interview and received answers.**

### Step 1: Identify What Went Wrong

If the user provided a description via `$ARGUMENTS`, use that as the starting point for identifying what went wrong.

Review the recent conversation and identify what failed:
- Hallucination (code that doesn't exist, wrong API, made-up feature)
- Wrong implementation (built something different than asked)
- Ignored instruction (explicit requirement was missed)
- Anti-pattern (violated project conventions)
- Bug introduced
- Loop/runaway behavior
- Context loss

### Step 2: Interview (Ask 5-8 Questions)

Ask SPECIFIC questions about what the user did, not generic ones. Examples:

**Prompt-focused:**
- "Your prompt was quite long. What were the 2-3 most critical requirements?"
- "What constraints were in your head but not in the prompt?"
- "Did you specify what NOT to do, or only what to do?"

**Context-focused:**
- "When did you last /clear or start fresh?"
- "Is there old debugging or abandoned approaches still in context?"

**Harness-focused:**
- "Did you verify subagents received the critical context?"
- "Did you validate the output before accepting it?"

### Step 3: Get the Triggering Prompt

Ask the user to confirm or paste the EXACT prompt that led to the failure. This is critical.

### Step 4: Create the Log

After the interview, create a log file at: `tmp/error-logs/error-YYYY-MM-DD-HHMM.md`

Use this template:

`````markdown
# Error: [Short Descriptive Name]

**Date:** [Date]
**Project/Context:** [What were you working on]

## What Happened
[2-3 sentences - what went wrong specifically]

## User Error Category

**Primary cause:** [Pick ONE]

### Prompt Errors
- [ ] Ambiguous instruction - Could be interpreted multiple ways
- [ ] Missing constraints - Didn't specify what NOT to do
- [ ] Too verbose - Buried key requirements in walls of text
- [ ] Reference vs requirements - Gave reference material, expected extracted requirements
- [ ] Implicit expectations - Had requirements in head, not in prompt
- [ ] No success criteria - Didn't define what "done" looks like

### Context Errors
- [ ] Context rot - Conversation too long, should have /cleared
- [ ] Stale context - Old information polluting new responses
- [ ] Missing context - Assumed Claude remembered something it didn't

### Harness Errors
- [ ] Subagent context loss - Critical info didn't reach subagents
- [ ] Wrong agent type - Used wrong specialized agent for task
- [ ] No validation - Accepted output without review
- [ ] Trusted without verification - Didn't check the work

## The Triggering Prompt
```
[Exact prompt - verbatim]
```

## What Was Wrong With This Prompt
[Be specific and critical. What should have been different?]

## Better Prompt
```
[Rewritten prompt that would have prevented this error]
```

## The Gap
- **Expected:** [What user expected]
- **Got:** [What actually happened]
- **Why:** [Connection to user error above]

## Prevention
1. [Specific action to take next time]
2. [Consider adding to CLAUDE.md?]

## Pattern Check
- **Seen before?** [Yes/No - if yes, this is a habit to break]
- Check `tmp/error-logs/` for past error logs to identify recurring patterns.

## One-Line Lesson
[Actionable takeaway - one sentence]
`````

### Step 5: Offer to Continue

After logging, ask if the user wants to:
1. Use double-escape to restore conversation (trim the debugging context)
2. Continue working on the fix
3. Add a prevention rule to CLAUDE.md
4. Run `/context-check` to verify current context health

## Important

- Be CRITICAL - the user is logging this to learn, not to feel good
- Focus 80% on user error, 20% on model behavior
- If the user can't identify their mistake, help them find it
- Be specific - vague logs are useless
