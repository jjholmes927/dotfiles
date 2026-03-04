# Ship

End-to-end workflow: format, commit, branch, PR, CI watch, fix failures, code review.

## Workflow

```
Format → Commit → Branch + Push → Create PR → Watch CI
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

## Step 1: Format

Check which files changed and run the appropriate formatters:

```bash
# Check file types in staged + unstaged changes
git diff --name-only HEAD

# Ruby files changed → run diffocop
diffocop -A

# JS/TS/CSS files changed → run pnpm formatters
pnpm run format:fix && pnpm run lint:fix
```

Only run formatters for file types that actually changed.

## Step 2: Commit

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

Format: `prefix: Imperative description`

**Rules:**
- NEVER add Co-Authored-By or Claude attribution
- Use imperative mood ("Add feature" not "Added feature")
- Keep subject line under 72 chars
- Add ticket reference in body if relevant (e.g., `INT-107`)

## Step 3: Branch + Push

If on `main`, create a new branch first:

```bash
# Branch naming convention
git checkout -b jjholmes927-<descriptive-name>-<TICKET-ID>

# Push with tracking
git push -u origin <branch-name>
```

If already on a feature branch, just push.

## Step 4: Create PR

Structure the PR description with **What** and **Why** headers:

```
**What**

- Bullet points describing changes

**Why**

- Context and reasoning

Fixes TICKET-ID
```

For bug fixes, add **Steps to Reproduce**.

Use `gh pr create` — do NOT use heredocs with single quotes inside the body (causes shell escaping issues). Use double-quoted strings or pass body directly.

## Step 5: Watch CI

```bash
gh pr checks <PR_NUMBER> --watch --fail-fast
```

This blocks until all checks complete or one fails.

### If CI is green → proceed to Step 6

### If CI fails → iterate

1. Fetch failures using the project's CI error fetcher:
   ```bash
   .claude/skills/fetching-ci-errors/fetch_ci_errors
   ```

2. Read the failing test files to understand what's expected

3. Fix the failures locally

4. Run the failing tests locally to verify:
   ```bash
   bundle exec rspec <failing_spec_files>
   ```

5. Format, commit (new commit, NOT amend), push

6. Watch CI again — repeat until green

**Max 3 CI fix iterations.** If still failing after 3 rounds, stop and report what's happening to the user.

## Step 6: Code Review

Once CI is green, dispatch a code review subagent:

```
Task tool with subagent_type: "superpowers:code-reviewer"

Prompt should include:
- What was implemented (summary of changes)
- The plan/requirements (ticket description or user's original request)
- BASE_SHA: the commit before your changes (e.g., origin/main)
- HEAD_SHA: current HEAD
- Brief description of the PR
```

Act on the review feedback:
- **Critical** → fix immediately, push, re-check CI
- **Important** → fix before marking PR ready
- **Minor** → note but don't block

## Arguments

$ARGUMENTS — Optional: commit message, ticket ID, or notes.

Examples:
- `/ship` — auto-detect everything
- `/ship INT-107` — include ticket reference
- `/ship feat: Add concurrency tracking` — use this exact commit message
