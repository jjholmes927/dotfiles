# E2E Fable → Sol Pipeline (`/e2e`)

**Date:** 2026-07-18
**Status:** Draft — awaiting approval

## Goal

One command that takes a Linear ticket or ad-hoc prompt through: Fable plan → single human plan gate → Sol 5.6 implementation → dual review (Sol self-review, Fable arbitration) → ship to PR with CI watch. Fable never writes production code; Sol never judges its own final output.

## Entry Point

New skill `skills/e2e/` in the **jjholmes927-claude-skills repo** (joel-workflow plugin, version bump to 2.1.0) so it syncs to the work setup through the marketplace already wired into settings.json. The skill bundles its helper script (`skills/e2e/scripts/e2e-codex.sh`) alongside SKILL.md.

- `/e2e INT-123` — invokes `joel-workflow:pick-up-linear-ticket` for ticket context, branch naming, and status moves.
- `/e2e "add rate limiting to X"` — ad-hoc; same pipeline, no Linear coupling.

## Pipeline Stages

### 1. Plan (Fable, interactive)
- Invoke `superpowers:brainstorming` (abbreviated for small tasks) then `superpowers:writing-plans`.
- Plan is written as discrete, independently-verifiable tasks with explicit file targets and test expectations — this is the contract handed to Sol.
- Fable grades each task's complexity and assigns Sol a reasoning effort per task (`low`/`medium`/`high`/`xhigh`): mechanical edits and boilerplate → low/medium, cross-cutting logic or tricky algorithms → high/xhigh. Recorded in the plan next to each task.
- **Gate (the only one):** user approves the plan. Nothing executes before approval.

### 2. Workspace
- `superpowers:using-git-worktrees` creates an isolated worktree on branch `jjholmes927-<slug>[-TICKET]`.
- All Sol invocations run with `cd` into the worktree.

### 3. Implement per task (Sol 5.6, headless)
- `codex exec --full-auto -c model_reasoning_effort=<task effort> "<task prompt>"` where the prompt contains: the plan task verbatim, relevant plan context, repo conventions (points at CLAUDE.md / AGENTS.md), and the instruction to run the project's tests before declaring done.
- Model comes from the codex config default (`gpt-5.6-sol`); effort comes from Fable's per-task grade assigned during planning. Fix-loop resumes inherit the task's effort; CI-fix resumes default to `high`.
- Session id is captured from output so later stages can `codex exec resume`.
- Failure policy: non-zero exit or no diff produced → retry once with the error appended; second failure surfaces to the user (pipeline pauses, does not silently skip).

### 4. Sol self-review
- The orchestrator makes a checkpoint commit in the worktree after each task, then runs `codex exec review --commit <sha>` so Sol reviews exactly that task's diff (not the accumulated branch).
- Sol fixes its own findings via `codex exec resume <session>`; fixes are amended into the task's checkpoint commit before Fable ever sees the diff.

### 5. Fable review + arbitration
- Dispatch a code-reviewer subagent on the task diff → structured findings (file, line, summary, severity).
- Fable arbitrates: drops false positives/nits, keeps confirmed defects.

### 6. Fix loop (max 2 iterations per task)
- Confirmed findings sent to `codex exec resume <session>` as a fix brief.
- Fable re-verifies each fix. After 2 loops, unresolved findings are carried forward as PR comments rather than blocking.

### 7. Final branch review (Fable)
- Whole-branch review against the approved plan: completeness (every plan task done), coherence across tasks, no plan drift.
- Same fix-loop rules apply once at branch level.

### 8. Ship (unattended — plan gate already passed)
- Delegates to the existing joel-workflow `/ship` command (format, commit any leftovers, push, PR with **What**/**Why**, CI watch, fix-fast loop); unresolved findings from the review loops are posted as PR comments.
- CI failure → failure log handed to `codex exec resume` to fix, push, re-watch (max 2 rounds, then surface).

## Roles

| Stage | Model | Mechanism |
|-------|-------|-----------|
| Plan, plan gate | Fable (live session) | superpowers brainstorm/writing-plans |
| Implement | Sol 5.6 | `codex exec --full-auto` in worktree |
| Self-review | Sol 5.6 | `codex exec review` |
| Arbitration + final review | Fable | code-reviewer subagent + live session |
| Fixes (all) | Sol 5.6 | `codex exec resume` |
| Ship orchestration | Fable | Bash (git/gh), per ship skill rules |

## Error Handling Summary

- Any stage failing twice → pause and surface to user with state (worktree path, session ids, last error). Never auto-abandon the worktree.
- Findings that survive fix loops → PR comments, not blockers.
- The plan gate is never bypassed; no re-planning without user involvement.

## Testing

- Dry-run mode (`/e2e --dry-run …`) stops after printing the codex commands it would run.
- First real validation: a deliberately small task in a sandbox repo (e.g. kernel-test) exercising the full path including a seeded bug for the review loop to catch.

## Resolved Decisions

1. Sol 5.6 model id is `gpt-5.6-sol` (verified via `codex exec -m gpt-5.6-sol`); now the default `model` in `~/.codex/config.toml`, so the pipeline omits `-m` and inherits the config default.
2. Worktree paths won't be in codex `projects.*.trust_level = "trusted"` — rely on `--full-auto` sandbox (workspace-write), which needs no trust entry.
3. Session-id capture: `codex exec --json` emits `{"type":"thread.started","thread_id":"<uuid>"}` as its first JSONL event (verified on codex-cli 0.144.5); the wrapper script parses that and `codex exec resume <thread_id>` accepts it.
4. Per-task review scope: orchestrator checkpoint-commits each task in the worktree and reviews with `--commit <sha>`, avoiding the `codex exec review` default (committed-only) silently reviewing nothing and avoiding cumulative-diff re-review.
5. Distribution: joel-workflow plugin skill (not a dotfiles command) so the work machine gets it via `claude plugin update`.
