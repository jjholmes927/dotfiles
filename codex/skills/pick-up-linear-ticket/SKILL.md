---
name: pick-up-linear-ticket
description: Fetch a Linear ticket, claim it, warm the context, and transition into implementation. Use when the user says pick up this ticket, start working on INT-156, grab ticket, claim ticket, work on COR-123, begin a Linear issue, or gives a Linear ticket URL or identifier such as INT-156 or COR-123, or explicitly says use pick-up-linear-ticket.
---

# Pick Up Linear Ticket

Fetch a Linear ticket, understand it, and prepare to implement it.

## Arguments

The user must provide a Linear ticket URL or identifier.

Extract the first identifier matching:

```text
[A-Z]{2,}-\d+
```

## Workflow

1. Confirm that a Linear MCP server is configured and available.
2. Fetch the ticket and capture:
   - title
   - description
   - status
   - priority
   - estimate
   - labels
   - project
   - relations
3. Fetch comments and enough project context to understand where the ticket fits.
4. Check for existing work:
   - `git branch -a | grep -i "<TICKET_ID>"`
   - `gh pr list --search "<TICKET_ID>" --state all --json number,title,state,headRefName,url`
5. Assign the ticket to the current user and move it to `In Progress` if needed.
6. Present a structured summary:
   - description
   - acceptance criteria
   - blockers
   - discussion
   - project context
7. Surface ambiguities or missing context in one message.
8. Once clarified, move into implementation.

## Important rules

- If any required Linear MCP call fails, stop and report the failure.
- Do not silently continue with partial ticket data.
- If the ticket is `Done` or `Cancelled`, warn before proceeding.
- If another person already has an active branch or PR, surface that clearly.

Tool names vary by MCP server. Use the configured Linear MCP functions that correspond to getting issues, comments, projects, initiatives, and the current user.
