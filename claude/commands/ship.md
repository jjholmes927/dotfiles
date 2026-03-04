# Ship

End-to-end workflow: format, branch, commit, push, PR, CI watch, fix failures, code review.

## Workflow

```
Preflight → Format → Stage → Branch (if on main) → Commit → Push → Create PR → Watch CI
                                                                                    │
                                                                            ┌───────┴───────┐
                                                                            │               │
                                                                         CI Green      CI Failed
                                                                            │               │
                                                                      Code Review    Fetch failures
                                                                            │          Fix + push
                                                                            │          └──→ Watch CI
                                                                          Done
```

## Step 0: Preflight

Before anything, verify prerequisites:

```bash
git rev-parse --git-dir        # We're in a git repo
git status --porcelain         # There are changes to commit
gh auth status                 # GitHub CLI is authenticated
```

If there are no changes to commit, stop and tell the user.

Check for an existing PR on the current branch:
```bash
gh pr view --json number 2>/dev/null
```
If a PR already exists, skip PR creation later (Step 5) — just push and watch CI.

## Step 1: Format

Detect changed file types and run appropriate formatters:

```bash
# Tracked changes + untracked files
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

Only run formatters for file types that actually changed:
- Ruby files (`.rb`) → `diffocop -A` (if available, else `bundle exec rubocop -A`)
- JS/TS/CSS files → `pnpm run format:fix && pnpm run lint:fix`

## Step 2: Stage + Branch

Stage all changes (formatting + implementation):
```bash
git add <specific files>   # Prefer specific files over git add -A
```

If on `main`, create a branch **before** committing:
```bash
git checkout -b jjholmes927-<descriptive-name>-<TICKET-ID>
```

## Step 3: Commit

Use conventional commit prefixes:

| Prefix | Use |
|--------|-----|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring |
| `chore:` | Deps, config, misc |
| `perf:` | Performance |
| `test:` | Tests only |
| `ci:` | CI changes |
| `docs:` | Documentation |
| `style:` | Formatting only |
| `build:` | Build system, deps |
| `ops:` | Infrastructure, deployment |
| `revert:` | Reverts a previous commit |

Format: `prefix: Imperative description`

**Rules:**
- NEVER add Co-Authored-By or Claude attribution
- Use imperative mood ("Add feature" not "Added feature")
- Keep subject line concise
- Add ticket reference in body if relevant (e.g., `INT-107`)
- Use a HEREDOC for the commit message to preserve formatting

## Step 4: Push + Create PR

```bash
git push -u origin <branch-name>
```

If no PR exists yet, create one with `gh pr create`. Use a HEREDOC for the body:

```bash
gh pr create --title "feat: Title here" --body "$(cat <<'EOF'
**What**

- Bullet points describing changes

**Why**

- Context and reasoning

Fixes TICKET-ID
EOF
)"
```

For bug fixes, add a **Steps to Reproduce** section.

## Step 5: Watch CI

Wait a few seconds after PR creation for checks to register, then watch:

```bash
sleep 5
gh pr checks <PR_NUMBER> --watch
```

This blocks until all checks complete.

### If CI is green → proceed to Step 6

### If CI fails → iterate

1. Fetch failures:
   - If `.claude/skills/fetching-ci-errors/fetch_ci_errors` exists, use it (handles RSpec failures)
   - For non-RSpec failures (ESLint, TypeScript, Prettier), check `gh pr checks` output directly
   - Fall back to `gh run view --log-failed` if the fetcher isn't available

2. Read the failing test files to understand what's expected

3. Fix the failures locally and run them to verify

4. Stage, commit (new commit, NOT amend), push

5. Watch CI again — repeat until green

**Max 3 CI fix iterations.** If still failing after 3 rounds, stop and report to the user.

## Step 6: Code Review

Once CI is green, dispatch a code review subagent:

```
Agent tool with subagent_type: "superpowers:code-reviewer"

Prompt should include:
- What was implemented (summary of changes)
- The plan/requirements (ticket description or user's original request)
- BASE_SHA: the commit before your changes (e.g., origin/main)
- HEAD_SHA: current HEAD
- Brief description of the PR
```

If the superpowers:code-reviewer subagent is not available, self-review:
- Run `git diff origin/main...HEAD` to see all changes
- Check for correctness, edge cases, and adherence to project conventions
- Report findings to user

Act on review feedback:
- **Critical** → fix immediately, push, re-check CI
- **Important** → fix before marking PR ready
- **Minor** → note but don't block

## Red Flags — STOP

- About to push to `main` directly → create a branch first
- About to force-push → ask user for confirmation
- No changes detected → do not create empty commits
- PR already exists → push to existing PR, don't create a new one
- 3+ CI fix iterations with no progress → stop and report

## Arguments

$ARGUMENTS — Optional: commit message, ticket ID, or notes.

### Parsing rules
- Matches a conventional commit prefix (`feat:`, `fix:`, etc.) → use as exact commit message
- Matches a ticket pattern (e.g., `INT-107`, `COR-456`) → include as ticket reference
- Empty → auto-detect commit type from the diff
- Anything else → treat as context for generating the commit message

Examples:
- `/ship` — auto-detect everything
- `/ship INT-107` — include ticket reference
- `/ship feat: Add concurrency tracking` — use this exact commit message
