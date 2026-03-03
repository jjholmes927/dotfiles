# Global Claude Code Instructions

These rules apply to ALL Claude Code sessions across all projects.

## Large Document Handling

When processing files that are too large to read in one pass:
1. **Flag immediately**: "This doc is [X] tokens, exceeds the [Y] limit"
2. **Ask user**: "Should I chunk it or would you prefer to split it first?"
3. **If chunking**: Read in sections, explicitly list what was/wasn't captured
4. **Never silently skip content** - always report what was missed
5. **After processing**: Confirm "I captured sections A, B, C - did I miss anything important?"

## Error Learning Categories

When logging errors or learning from mistakes:

| Error Type | Where to Log |
|------------|--------------|
| Project-specific (test patterns, codebase quirks) | That project's CLAUDE.md |
| General Claude Code usage (prompting, context) | This file (~/.claude/CLAUDE.md) |
| Personal learnings about AI workflows | Second brain (if using one) |

## Git Branch Naming

When creating branches, always prefix with: `jjholmes927-`

Example: `jjholmes927-feature-name-DOC-123`

## Pre-Commit Formatting

Before committing, always run the appropriate formatters/linters:

| Changed Files | Run Before Commit |
|---------------|-------------------|
| JavaScript/TypeScript (`.js`, `.ts`, `.tsx`, `.jsx`) | `pnpm run format:fix && pnpm run lint:fix` |
| Ruby (`.rb`) | `diffocop -A` |

## Git Commits & PRs

- **NEVER** add `Co-Authored-By: Claude` or any Claude attribution to commit messages or PR descriptions
- Use concise, imperative mood messages

## Code Comments

Code should be self-descriptive and readable without comments. Only add comments that provide context for **why** the code exists, not **what** it does.

**Bad comments** (don't write these):
```typescript
// Audio should play when autoplay is enabled AND not muted
const shouldPlayAudio = autoplayEnabled && !isMuted
```

**Good comments** (capture hidden knowledge):
```typescript
} catch {
  // localStorage may be unavailable in private browsing mode
}
```

```ruby
# Why do we check recording_sources.empty?
# Recordings are lenient: eligible if at least one has a valid transcript.
# Silent or short recordings may produce empty transcripts (e.g. extra context recordings).
# Previously we checked recording_sources.all? have a transcript, but different transcription
# services handle silent recordings differently - some have no transcript, which meant adding
# silent recordings to working reports would break them.
```

Good comments capture:
- Business logic or domain context that would otherwise be lost
- Non-obvious reasons why code exists (workarounds, edge cases)
- External constraints or dependencies not evident from the code

## PR Descriptions

Always structure PR descriptions with **What** and **Why** as bold headers:

```markdown
**What**

- Bullet points describing the changes made

**Why**

- Explanation of the reason/context for these changes

Fixes LINEAR-123
```

For bug fixes, add a **Steps to Reproduce** section:

```markdown
**What**

- Description of the fix

**Why**

- Why this bug occurred / what was wrong

**Steps to Reproduce**

1. Step one
2. Step two
3. Observe the issue

Fixes LINEAR-123
```

Include the Linear ticket reference in the PR title or description body.

## Commands and Skills

When creating new slash commands or skills, prefer placing them in the global dotfiles (`~/.claude/commands/`, `~/.claude/skills/`) unless they are truly project-specific. This makes them available across all projects automatically.

- **Project-agnostic tools** (verify-ui, brag-doc, etc.) → `~/.claude/commands/`
- **Project-specific workflows** (brainstorm, write-plan, etc.) → `.claude/commands/` in the repo

## Working Style

- When uncertain about scope, ask one clarifying question rather than assuming
- For multi-step tasks, use TodoWrite to track progress
- Commit frequently with clear messages
- When processing multiple files, summarize what was done at the end
