---
name: ship
description: "Run an end-to-end ship workflow for a branch: format, commit, push, open or update a PR, watch CI, and self-review. Use when the user says ship it, open a PR, push this branch, get this ready to merge, take this through CI, finish this branch, or explicitly says use ship."
---

# Ship

End-to-end workflow: format, branch, commit, push, PR, CI watch, and review.

## Workflow

1. Preflight
   - verify git repo
   - verify there are changes to commit
   - verify `gh auth status`
2. Detect changed file types and run only the needed formatters.
3. Stage specific files.
4. If on `main`, create a branch first.
5. Commit with a concise imperative message.
6. Run a local review pass against the diff before pushing.
7. Push the branch.
8. If no PR exists, create one with `What` and `Why` sections.
9. Watch CI and surface failures.
10. If CI fails, fetch the failures, fix them, push again, and continue watching.

## Formatting rules

- Ruby: `diffocop -A` if available, otherwise `bundle exec rubocop -A`
- JS, TS, CSS: `pnpm run format:fix && pnpm run lint:fix`

## PR body format

```markdown
**What**

- ...

**Why**

- ...
```

For bug fixes, add `Steps to Reproduce`.

Never add AI attribution to the commit message or PR description.
