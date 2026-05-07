# Ship

End-to-end workflow: format, branch, commit, push, PR, CI watch, fix failures, code review.

## Workflow

```
Preflight → Format → Stage → Branch (if on main) → Commit → Simplify → Push → Create PR → Watch CI
                                                                                               │
                                                                                       ┌───────┴───────┐
                                                                                       │               │
                                                                                    CI Green      CI Failed
                                                                                       │               │
                                                                                Bugbot Review    Fetch failures
                                                                                       │          Fix + push
                                                                                 Code Review     └──→ Watch CI
                                                                                       │
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

## Step 4: Simplify

Before pushing, run `/simplify` to review changed code for reuse opportunities, quality issues, and efficiency improvements. This uses three parallel review agents (code reuse, code quality, efficiency) to catch issues locally before they go remote.

Invoke the `simplify` skill, which will:
1. Identify all changes via `git diff`
2. Launch three parallel review agents
3. Fix any issues found

If simplify made changes, stage and create a new commit before proceeding:
```bash
git add <changed files>
git commit  # New commit with fixes from simplify
```

If no issues were found, proceed directly to push.

## Step 5: Push + Create PR

```bash
git push -u origin <branch-name>
```

If no PR exists yet, create one with `gh pr create`. Use a HEREDOC for the body.

### Writing the body

Keep it terse and outcome-focused. Aim for ~5–10 lines total. Long bullet inventories duplicate the diff and bury the actual story.

- **What** — 1–2 sentences describing the user-visible capability change in plain language. Don't list function names, constants, or "wired into X" — the diff covers that.
- **Why** — motivation in real-world terms. Include real numbers when you have them (latency, cost, error rate, sample sizes). Link the report/ticket/dashboard that justifies the work.
- **No "Fixes TICKET-ID" footer.** Linear auto-attaches via the ticket bracket in the PR title (e.g. `[INT-350]`). Linking the ticket inline in the Why section is fine if it adds context.
- For bug fixes, add a **Steps to Reproduce** section.

### Template

```bash
gh pr create --title "feat: Title here [TICKET-ID]" --body "$(cat <<'EOF'
**What**
One-or-two-sentence description of the capability change.

**Why**
Motivation in real-world terms — why this matters, what it unblocks, what it improves. Include numbers (latency, cost, etc.) when relevant. Link [TICKET-ID](https://linear.app/...) or supporting docs inline if useful.
EOF
)"
```

### Counter-example (too verbose — avoid)

Don't write a bullet for every code change like this:
```
**What**
- Add `Foo::Bar.baz(x:, y:)` that does X
- Wire it into `Some::Service#do_thing`
- Add `THING_CONSTANT` with the values from the report
- Update `Some::Service` to use the new constant
- Add 3 OTel span attributes: `foo.bar`, `foo.baz`, ...
```
This is just a worse version of the diff. The reviewer can see the diff. Tell them what *outcome* the changes produce.

## Step 6: Watch CI

Watch CI checks — GitHub needs a moment to register them, so retry on empty output:

```bash
gh pr checks <PR_NUMBER> --watch
```

If the first call returns immediately with no checks listed, wait 2 seconds and try once more.

This blocks until all checks complete.

### If CI is green → proceed to Step 7

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

## Step 7: Bugbot Review

Once CI is green, check if Cursor Bugbot has reviewed the PR:

```bash
gh pr checks <PR_NUMBER> | grep -i "bugbot\|cursor"
```

If Bugbot has completed, fetch its review comments:

```bash
gh api repos/{owner}/{repo}/pulls/<PR_NUMBER>/comments --jq '.[] | select(.user.login | test("cursor|bugbot"; "i")) | {path: .path, line: .line, body: .body}'
```

For each Bugbot comment:
1. Evaluate whether the suggestion is valid and worth fixing
2. If valid → fix locally, stage, commit (new commit), push
3. If not valid or too noisy → skip it

If Bugbot hasn't run yet, wait briefly (up to 60 seconds) and recheck. If it still hasn't appeared, proceed — don't block on it.

After applying any Bugbot fixes, watch CI again to confirm nothing broke before proceeding.

## Step 8: Code Review

Once CI is green and Bugbot is addressed, run the PR review:

```
/review-pr <PR_NUMBER>
```

This launches four parallel reviewers (security, Rails patterns, code quality, product domain)
and posts the combined review to the GitHub PR.

If `/review-pr` exits without emitting a `REVIEW_STATUS:` line (e.g. auth failure, no PR found, no diff), report the error to the user and stop — do not proceed to Done.

### If review returns REVIEW_STATUS: CRITICAL

Show findings inline and prompt:
```
Critical issues found. Fix now? (y/n)
```

**If yes:**
1. Address the findings locally
2. Stage and commit (new commit, NOT amend)
3. Push to existing PR
4. Watch CI again (return to Step 6, then Step 7 if Bugbot hasn't reviewed the new commit)
5. Re-run `/review-pr <PR_NUMBER>` after CI is green
6. Repeat up to 3 review-fix iterations total — if Critical findings persist after 3 rounds, stop and report to user. The Step 6 CI iteration counter resets for each new set of committed fixes.

**If no (skip fixes):**
Continue to Done.

### If review returns REVIEW_STATUS: OK

Do not prompt or block — the developer decides independently. The findings are already displayed inline by `/review-pr`.

### If review returns REVIEW_STATUS: CLEAN

Proceed directly to Done.

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
