---
description: Use when the user says "pick up", "start working on", "grab ticket", "claim ticket", or provides a Linear ticket URL/identifier (e.g. INT-156, COR-123) and wants to begin implementation
---

# Pick Up Linear Ticket

Context-warming workflow: fetch a Linear ticket, claim it, understand it, resolve ambiguities, then transition into implementation.

## When NOT to Use

- Ticket is purely informational (reading a spec, reviewing someone else's work)
- Ticket is from a non-Linear project management tool
- The developer just wants to read the ticket without starting work

## Arguments

`$ARGUMENTS` — Required: Linear ticket URL or identifier.

### Parsing rules

- Full URL (e.g., `https://linear.app/beam/issue/INT-156/add-alert-banner`) → extract identifier (`INT-156`)
- Identifier (e.g., `INT-156`, `COR-123`) → use directly
- Multiple ticket IDs → pick up only the first one, suggest running the command again for others
- Empty → stop and ask the user for a ticket

Regex for identifier extraction: `[A-Z]{2,}-\d+`

## Error Handling

If any Linear MCP tool call fails at any point in this workflow, report the error to the user and stop. Do not silently skip failed steps or continue with partial data.

## Step 0: Load Linear MCP Tools

Before any Linear API calls, load the required tools:

```
ToolSearch(query="select:mcp__claude_ai_Linear__get_issue,mcp__claude_ai_Linear__save_issue,mcp__claude_ai_Linear__get_user,mcp__claude_ai_Linear__get_project,mcp__claude_ai_Linear__get_initiative,mcp__claude_ai_Linear__list_comments")
```

If Linear MCP is unavailable, stop and tell the user — this command requires it.

## Step 1: Fetch Ticket

```
mcp__claude_ai_Linear__get_issue(id: "<TICKET_ID>", includeRelations: true)
```

Capture:
- Title, description, status, priority, estimate
- Labels and project
- Relations (blocking, blocked by, related, duplicates)
- Assignee (current)
- Auto-generated branch name (if available)

If the ticket doesn't exist, stop and tell the user.

**Status check:** If the ticket is Done or Cancelled, warn the user and ask whether to proceed before continuing.

## Step 2: Fetch Relations and Parent Context

**Blocking/blocked-by tickets:** For each relation from Step 1, fetch the related ticket:
```
mcp__claude_ai_Linear__get_issue(id: "<RELATED_ID>")
```

**Project context** (if ticket belongs to a project):
```
mcp__claude_ai_Linear__get_project(query: "<PROJECT_NAME>", includeMilestones: true)
```

**Initiative context** (if project belongs to an initiative):
```
mcp__claude_ai_Linear__get_initiative(query: "<INITIATIVE_NAME>")
```

**Comments** (for discussion context):
```
mcp__claude_ai_Linear__list_comments(issueId: "<TICKET_ID>")
```

Run fetches in parallel where possible. For large epics/projects, fetch just enough context to understand where this ticket fits — don't load the entire project history.

## Step 3: Check for Existing Work

Check if someone already started work on this ticket **before claiming it**:

```bash
git branch -a | grep -i "<TICKET_ID>"
gh pr list --search "<TICKET_ID>" --state all --json number,title,state,headRefName,url
```

If existing work is found (branches, open/closed PRs), surface it prominently. If the ticket is assigned to someone else who has an open PR, ask before proceeding — they may still be working on it.

## Step 4: Claim the Ticket

**Assign to current user and move to In Progress** in a single call (if needed):

```
mcp__claude_ai_Linear__get_user(query: "me")
```

Check current assignee and status. If either needs updating:
```
mcp__claude_ai_Linear__save_issue(id: "<TICKET_ID>", assignee: "me", state: "In Progress")
```

Report what was updated (e.g., "Assigned to you and moved to In Progress").

**Note:** "In Progress" is the expected state name. If the save fails due to an invalid state, the team's workflow may use a different name — report the error so the developer can clarify.

## Step 5: Present Context and Gather Input

Present a structured summary, then ask about ambiguities and additional context in a **single message** to avoid multiple round-trips.

### Context Summary

```markdown
## <TICKET_ID>: <Title>

**Status:** <previous status> → In Progress
**Priority:** <priority>
**Project:** <project name> (if any)
**Estimate:** <estimate> (if any)
**Labels:** <labels>

### Description
<ticket description — render markdown as-is, or flag "No description provided" if empty>

### Acceptance Criteria
<extract from description if present, otherwise note "No explicit acceptance criteria found">

### Relations
- **Blocks:** <tickets this blocks>
- **Blocked by:** <tickets blocking this> ⚠️ (flag if blockers are not done)
- **Related:** <related tickets with brief context>

### Discussion
<summarize key points from comments, if any>

### Project Context
<brief context from project/initiative, if relevant>

### Existing Work
<branches, PRs, or "No existing work found">
```

### Questions and Additional Context

After the summary, in the same message:

1. **Surface specific ambiguities** identified from the ticket:
   - Missing acceptance criteria — what does "done" look like?
   - Unclear scope — what's included/excluded?
   - Technical unknowns — implementation approaches that need deciding?
   - Unresolved blockers — are blocking tickets actually blocking?
   - Missing context — references to things not explained?

   Don't ask generic questions — only ask about genuine gaps. If the ticket is clear and well-specified, say so.

2. **Ask for additional developer context:**
   > Is there any additional context I should know? (e.g., conversations not in the ticket, preferred approach, related in-progress work, things you've tried or ruled out)

Wait for their response before proceeding.

## Step 6: Create Branch

Ensure the working directory is clean first. If there are uncommitted changes, warn the developer and ask how to proceed (stash, commit, or abort).

```bash
git fetch origin main
git checkout main
git pull origin main
git checkout -b <PREFIX>-<descriptive-name>-<TICKET_ID>
```

**Branch name rules:**
- Use the developer's configured branch prefix (check CLAUDE.md for convention)
- Derive a short descriptive slug from the ticket title (lowercase, hyphenated, 3-5 words max)
- Append the ticket ID
- If Linear returned an auto-generated branch name, offer it as an alternative
- Example: `jjholmes927-add-alert-banner-INT-156`

Confirm the branch name with the developer before creating it.

## Step 7: Hand Off to Implementation

With context warmed up, transition into the normal implementation workflow:

> Context is loaded. Here's what we're working on:
>
> **Goal:** <one-sentence summary of what we need to achieve>
> **Key constraints:** <any blockers, technical constraints, or scope boundaries identified>
>
> Ready to start. Would you like to brainstorm the approach, or do you already have a plan in mind?

If a brainstorming skill is available, this is the natural entry point for it.

## Red Flags — STOP

- **Ticket is already Done/Cancelled** → warn the user, ask before proceeding
- **Ticket is assigned to someone else** → ask before reassigning, especially if they have an open PR
- **Blocking tickets are incomplete** → flag prominently, ask if we should proceed
- **Ticket has an open PR** → likely already in progress, confirm before creating new branch
- **No Linear MCP available** → cannot proceed, tell the user
- **Ticket has no description** → flag clearly, ask if the developer has context or if we should check with the ticket creator
- **Working directory is dirty** → warn before switching branches
- **"In Progress" state rejected** → report the error, ask the developer for the correct state name

## Checklist

Before handing off to implementation:

- [ ] Ticket fetched with full context (description, relations, comments)
- [ ] Existing branches/PRs checked (before claiming)
- [ ] Ticket assigned to current user and moved to In Progress
- [ ] Blocking tickets identified and flagged
- [ ] Acceptance criteria extracted or gap identified
- [ ] Ambiguities surfaced and developer context gathered
- [ ] Branch created with correct naming convention
- [ ] Context summary presented clearly
