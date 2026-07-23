# Global Claude Code Instructions

These rules apply to ALL Claude Code sessions across all projects.

## Communication Style (ADHD — hard rules)

I have ADHD. Walls of text stall me. These are verifiable rules, not preferences:

1. **Default replies ≤8 lines.** Expand only when I ask.
2. **Lead with the answer/outcome** in the first line, bolded.
3. **Bold-front the key word** of every bullet so a skim works.
4. **One thing at a time**: orient in one line → one topic → short menu of next steps. Never batch unrelated questions — use option menus for decisions.
5. **Long content never goes in chat**: put reports/designs in the ticket, a doc, or an artifact and give me a 3–5 line summary + link.
6. **Visual over prose**: small tables, ✅/⚠️/❌ signposts, diffs, diagrams.
7. **Color via signposts**: 🔴 blocker / 🟡 caution / 🟢 good, and one ```diff block per reply as a red/green "traffic light" summary of key takeaways. (Real colored prose is impossible in the terminal — ANSI/HTML are stripped; use Artifacts when full color matters.)

## Implementation Plan Reviews (hard rule)

Whenever presenting an implementation plan for my review/approval (any plan gate, including /e2e Stage 1):

1. **Always render the plan as an Artifact** — never a wall of chat text.
2. **Visual-first core info**: the problem as a diagram/picture, a behavior table (what changes vs what's guarded), task cards with effort badges, guardrails/ripple effects, audit trail, explicit approve bar at top and bottom.
3. **Raw plan tab**: the artifact must include a tab switcher with a "Raw plan" tab showing the full markdown plan verbatim, alongside the visual overview tab.
4. **Chat stays 3–5 lines**: summary + artifact link + the ask.

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

## Slack MCP Usage

- `slack_read_channel` returns **newest-first** with cursor pagination. Never conclude a channel is quiet/dormant without a no-cursor call showing the actual newest messages.
- When sweeping a time window, follow cursors until pages run out or the `oldest` boundary is reached, then report the earliest/latest timestamps actually covered.
- When delegating Slack sweeps to subagents, include explicit pagination instructions and require a coverage report (earliest/latest ts seen); spot-check any "channel went quiet" claim with a direct read.

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

**NEVER write code comments unless I explicitly ask for them.** This is a hard rule, not a preference. Default to zero comments. Code should be self-descriptive through naming and structure.

This applies to all comments: explanatory `//` / `#` lines, block comments, class/method doc comments, "what this does" annotations, and rationale/"why" notes. Do not add them proactively — not even for non-obvious workarounds or edge cases. If something genuinely needs explaining, surface it in your chat response or the PR description instead, and let me decide whether it belongs in the code.

The only exceptions are comments that are not prose you are choosing to add:
- A comment I explicitly request, or one I ask you to keep/restore.
- Comments already present in code you're editing (don't strip those unless asked).
- Machine-required directives that aren't optional (e.g. `# frozen_string_literal: true`, `# rubocop:disable ...`, `eslint-disable`, codegen markers, shebangs).

When in doubt, leave the comment out.

## PR Descriptions

Whenever writing or editing a PR description, invoke the **`writing-pr-descriptions`** skill (joel-workflow plugin) — it owns the full rules. The essentials, in case the skill is unavailable:

- **What** / **Why** as bold headers — nothing else.
- **Each section: max 3 bullets or 2–3 short sentences.** One idea per sentence or bullet — never a dense mega-sentence to dodge the cap.
- **Outcome, not inventory** — no function-name listings; the diff covers that.
- **No "Fixes TICKET-ID" footer** — ticket goes in the title bracket (e.g. `[INT-350]`).
- Stacked PRs: one line pointing at the PR that carries the big picture; never retell the story per layer.

## Commands and Skills

When creating new slash commands or skills, prefer placing them in the global dotfiles (`~/.claude/commands/`, `~/.claude/skills/`) unless they are truly project-specific. This makes them available across all projects automatically.

- **Project-agnostic tools** (verify-ui, brag-doc, etc.) → `~/.claude/commands/`
- **Project-specific workflows** (brainstorm, write-plan, etc.) → `.claude/commands/` in the repo

## Working Style

- When uncertain about scope, ask one clarifying question rather than assuming
- For multi-step tasks, use TodoWrite to track progress
- Commit frequently with clear messages
- When processing multiple files, summarize what was done at the end
# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
