# Weekly flow review (routine prompt)

> **TL;DR** Every Monday, read last week's workflow ledger and GitHub activity, then put one short report and the review reminders in Todoist. Read-only everywhere except Todoist.

This file is the prompt for the scheduled routine. The personal routine uses Honeycomb environment `joel-personal` and the `jjholmes927` repositories. The work-laptop copy uses `beam-work` and the `wearebeam` repositories.

## Inputs

**Window:** the 7 days before the run, in Europe/London.

**Honeycomb**, team `agent-traces`, dataset `workflow-ledger`:

| Question | Query |
|---|---|
| Rules loaded | `event = rules_loaded`: COUNT by `principles`, `triggers`, `size`, `review` |
| Findings by stage | `event = finding`: COUNT by `stage`, `principle`, `severity` |
| A/B runs | `event = e2e_run`: COUNT by `arm`; `event = finding` where `arm` exists: COUNT by `arm`, `stage`; `event = e2e_done`: AVG `minutes` and AVG `tokens` by `arm` |
| Loop runs | `event = skill_invoked` and `skill` contains `making-changes`: COUNT_DISTINCT `session_id` |

**Adoption:** in dataset `claude-code`, COUNT_DISTINCT `session.id` where `tool_name` is `Edit`, `Write` or `MultiEdit`. Adoption is loop runs divided by that count. The target is 90% or more.

**Trigger misses vs rule misses:** for each `finding` whose stage is `ci`, `bot`, `human-review` or `production`, find the `rules_loaded` events with the same `repo` and `branch` (or the same `head` when the branch is the default branch). If none of them lists the finding's principle, it's a **trigger miss** (the rule never loaded). If one does, it's a **rule miss** (it loaded and still let the problem through). Findings with principle `other` or `tests` count separately.

**GitHub**, with `gh`, for PRs merged in the window:
- CI failure rounds per PR (failed check runs before the last green one).
- Commits pushed after the PR opened.
- Issues labelled `bug` that link a merged PR.
- Human review comments. Classify each against the good-code principles (numbered in the joel-workflow plugin's `skills/good-code/SKILL.md`) as principle, `tests`, `other` or `not a finding`.

## Output: Todoist only

1. **Task `Weekly flow report <date>`**, description at most 15 lines:
   - Adoption: loop runs / edit sessions = N%.
   - Findings by stage, earliest first (write, risk-review, e2e-review, ci, bot, human-review, production).
   - Top three principles by findings, each with trigger misses and rule misses.
   - Principles with no `rules_loaded` all week.
   - A/B: runs, findings, mean minutes and mean tokens per arm.
   - One suggested change to a trigger or rule, with the evidence behind it.
2. **Task `Rate 2 changes`**: links to two PRs merged in the window, picked at random, asking "Would I merge this as-is? 1–5".
3. **Task `Decide the e2e A/B winner`**, once: when each arm has 5 or more `e2e_run` events in total, or on or after 2026-12-26, whichever comes first. Check for an open task with that name before creating it.
4. **Task `Run the after benchmark`**, once: 14 days after the first `e2e_run` event with arm `B`. Check for an open task with that name before creating it.

## Rules

- Never change anything except creating Todoist tasks: no commits, comments, labels or Honeycomb boards.
- When a source can't be read, say so in the report, naming the source and the error, and still create the other tasks.
- Report numbers you queried, never estimates.
