# Global Codex Instructions

These rules apply to all Codex sessions across all projects.

## Large document handling

When a file or document is too large to read safely in one pass:
1. Flag it immediately and state that it exceeds practical context limits.
2. Ask whether to chunk it or whether the user wants to narrow scope first.
3. If chunking, be explicit about what was and was not captured.
4. Never silently skip sections.
5. After processing, confirm coverage and ask whether anything important was missed.

## Error learning categories

When logging errors or learnings:

| Error type | Where to log |
|------------|--------------|
| Project-specific conventions or testing learnings | That project's `AGENTS.md` or repo guide |
| General Codex usage learnings | This file |
| Personal workflow learnings | Second brain or personal notes |

## Git branch naming

When creating branches, always prefix with `jjholmes927-`.

Example: `jjholmes927-feature-name-DOC-123`

## Pre-commit formatting

Before committing, run the appropriate formatters and linters:

| Changed files | Run before commit |
|---------------|-------------------|
| JavaScript or TypeScript | `pnpm run format:fix && pnpm run lint:fix` |
| Ruby | `diffocop -A` |

## Git commits and PRs

- Never add Codex, OpenAI, or AI attribution to commits or PR descriptions.
- Use concise, imperative commit messages.

## Code comments

Code should be readable without comments. Only add comments that capture hidden context, not comments that restate what the code already says.

Good comments explain:
- business logic that is easy to lose
- non-obvious reasons for a workaround
- external constraints not visible in the code

## PR descriptions

Structure PR descriptions with `What` and `Why` sections.

For bug fixes, add `Steps to Reproduce`.

Include the Linear ticket reference in the PR title or body when relevant.

## Skills

When creating new reusable Codex workflows, prefer global skills in `~/.codex/skills` unless they are truly project-specific.

- Project-agnostic workflows belong in global Codex skills.
- Project-specific workflows belong in repo-local skills or repo docs.

## Working style

- When scope is unclear, ask one clarifying question instead of guessing.
- For multi-step tasks, keep an explicit plan.
- Commit frequently with clear messages.
- When touching multiple files, summarize what changed at the end.
