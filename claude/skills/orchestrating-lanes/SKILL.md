---
name: orchestrating-lanes
description: Use when the user asks to spin up lanes, orchestrate parallel ticket work, run new-agent, or work through Linear tickets across multiple agent sessions (e.g. "use the lanes", "orchestrate the todo column", "spin up new-agent on these tickets")
---

# Orchestrating Lanes

## Overview

Run parallel bodies of ticket work in separate background Claude sessions ("lanes") via the `new-agent` script (`~/.local/bin/new-agent`), with this session acting as orchestrator: assign tickets, watch for completion, refill free lanes. Lanes are real Fleet sessions, visible in fleet, and take plan approvals directly from the user.

**Never use the Agent tool (subagents) for lanes.** Subagents nest under the orchestrator session, don't appear in fleet, and funnel approvals through one session. Lanes must be spawned with `new-agent`.

## Ticket Scoping — CRITICAL

**Never sweep an entire Linear Todo column by default.** That is only safe on a solo project. On any shared team, the Todo column contains other people's work; auto-claiming it creates chaos.

Before assigning anything:
1. Ask (or confirm from the user's message) which tickets are in scope: explicit list, "my assigned tickets", or "whole Todo column".
2. Default filter when unspecified: tickets assigned to `me` or unassigned, in the named team, state Todo, ordered by priority (Urgent → High → Medium → Low).
3. Confirm the queue with the user before launching lanes, one short table: lane → ticket → priority, plus the queued remainder.

## Launch Recipe

```bash
new-agent <lane> "/e2e TICKET-ID"
new-agent <lane> [branch-name] --effort high|low --safe   # optional flags; default effort high, bypassPermissions
```

- Lanes are directories under `$ENG_ROOT` (currently `~/Engineering/side-projects`). Enumerate candidates with `ls "$ENG_ROOT"`; a lane is free when no session from `claude agents` is working in it. The user names which dirs are lanes — don't assume every dir is one.
- `new-agent <lane>` expects `$ENG_ROOT/<lane>` to be a git repo. **Pre-flight check before every launch:** `[ -d "$ENG_ROOT/<lane>/.git" ]`.
- **Nested-repo quirk:** some lane dirs hold the repo one level down (e.g. `gigme2/GigMe`). Launch those with `ENG_ROOT=$ENG_ROOT/<lane> new-agent <repo-dir> "..."`.
- Each launch creates a worktree and a background session named like `<repo>/<slug>`; the script's prompt footer tells the lane to name its branch `jjholmes927-...` and to run `fleet-status complete|awaiting` when done.

## Orchestration Loop

1. Build the prioritized queue (scoped per above).
2. Launch one lane per free lane dir, top of queue first.
3. Subscribe to each lane: `SendMessage {to: "<session-name>", notify_when_idle: true}` with no message. Never poll `ListAgents` or send "are you done?".
4. On an idle notice, check whether the lane is actually complete — it goes idle at plan-approval gates too. Idle notices carry the session name; map name → id via `claude agents`, then `claude logs <id>`. Reassign the next queued ticket only on real completion: the lane reported `fleet-status complete` AND the ticket is Done in Linear (which the lane sets only after its /e2e verification passed and the change is in production). An approval gate goes to the user; leave the lane alone.
5. Plan approvals belong to the user, in the lane's own session. The orchestrator never approves plans, edits lane worktrees, or duplicates lane work.

## Quick Reference

| Task | Command |
|---|---|
| Launch lane | `new-agent <lane> "/e2e NEV-123"` |
| Nested repo lane | `ENG_ROOT=$ENG_ROOT/<lane> new-agent <repo-dir> "/e2e NEV-123"` |
| List sessions | `claude agents` |
| Lane output | `claude logs <id>` |
| Stop lane | `claude stop <id>` |
| Watch lane | SendMessage with `notify_when_idle: true`, empty message |

## Common Mistakes

- **Spawning Agent-tool subagents as "lanes"** — invisible in fleet, approvals funnel wrongly. Use `new-agent`.
- **Auto-claiming a team's whole Todo column** — scope and confirm first.
- **Treating an idle notice as completion** — lanes idle at approval gates; verify `fleet-status complete` before refilling the lane.
- **"not a git repository" on launch** — nested-repo lane; repoint `ENG_ROOT`.
