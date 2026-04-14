---
name: review-pr
description: Review a pull request or branch diff across security, framework patterns, code quality, and product behavior. Use when the user asks to review a PR, review this branch, self-review before pushing, check for issues before merging, review code changes, review the diff, or explicitly says use review-pr.
---

# Review PR

Review a PR or branch diff with a code-review mindset.

## Arguments

Accept either:
- a PR number
- `--fast`
- nothing, in which case detect the PR from the current branch

If `--fast` is passed, print `Review skipped (--fast)` and stop.

## Workflow

1. Preflight:
   - verify `gh auth status`
   - determine PR number if not provided
   - determine PR author and current GitHub user
2. Fetch the diff once.
3. Read any available context docs from the repo, especially product or architecture guides.
4. Review the diff across four lenses:
   - security and data safety
   - framework and Rails conventions
   - code quality and regression risk
   - product or domain behavior
5. If subagents are available and the session explicitly allows them, parallelize those lenses. Otherwise review sequentially.
6. If the current user is the author, you may post the review to GitHub with `gh pr review` after presenting it. Otherwise show the review inline only.

## Output

Findings first, ordered by severity.

Use:

```markdown
## Findings

1. <severity> <issue> [file:line]
2. ...

## Open Questions

- ...

## Change Summary

- ...
```

If there are no findings, say so explicitly and mention any residual testing gaps.
