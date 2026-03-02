---
description: "Review a Claude Code skill or command for quality. Use when the user says 'review this skill', 'check my skill', 'skill review', or asks about skill quality and best practices."
disable-model-invocation: true
argument-hint: [path/to/SKILL.md]
---

# Skill Reviewer

Review a Claude Code skill by dispatching two parallel subagents — one for structural quality against superpowers/Anthropic patterns, one for domain-specific accuracy.

**Core principle: A skill is only as good as its worst instruction. One ambiguous line can cause Claude to take a shortcut that undoes everything else.**

**When NOT to use:** Do not use this to review CLAUDE.md files, plugin configurations, or non-skill markdown files.

## Parameters

Parse from user input or context:
- **skill_path** (required) — Path to the SKILL.md file to review. If not provided, ask the user.
- **domain** (optional) — Brief description of the skill's domain (e.g., "Sentry error monitoring", "Capybara testing"). If not provided, infer from the skill content.

## Steps

### 1. Read the skill

Read the full SKILL.md at the given path. If there are companion files (references, scripts, examples), note them but focus the review on SKILL.md.

### 2. Dispatch two parallel subagents

Launch both simultaneously using the Agent tool with `subagent_type='general-purpose'`.

#### Subagent A: Structural review

Prompt (fill in `[SKILL_PATH]` and `[SKILL_CONTENT]`):

```
You are reviewing a Claude Code skill for quality. Compare it against
the best skill-writing patterns and produce prioritized, actionable feedback.

## Skill under review

Path: [SKILL_PATH]

Content:
---
[FULL SKILL.MD CONTENT]
---

## Review process

1. Read these reference skills to extract current patterns (read ALL of them):

   Superpowers skills (gold standard for structure and prompt engineering):
   - Glob for all SKILL.md files under the superpowers plugin cache:
     ~/.claude/plugins/cache/superpowers-marketplace/superpowers/*/skills/*/SKILL.md
   - Prioritise reading: systematic-debugging, verification-before-completion,
     writing-skills, brainstorming
   - If no superpowers skills are found at the cache path, search the web for the current Anthropic skill documentation at `https://code.claude.com/docs/en/skills` and use that as the reference standard.

   Official Anthropic guides:
   - ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator/SKILL.md
   - ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/skill-development/SKILL.md
   - If these files are not found, search the web for 'Anthropic Claude Code skill authoring best practices 2026' as a fallback.

   Also search the web for current Anthropic documentation on skill/command authoring.

2. Evaluate against these criteria:

   FRONTMATTER
   - Is it a skill (name + description in SKILL.md) or command (description only in .md)?
   - Description: triggering conditions with specific phrases, NOT a workflow summary
   - allowed-tools: listed if the skill uses MCP or restricted tools
   - Max 1024 chars for description

   STRUCTURE
   - Core principle / Iron Law statement near the top
   - When to Use / When NOT to Use sections (skills) or Parameters section (commands)
   - Clear step-by-step workflow
   - Red Flags — STOP section for critical guardrails (if the skill takes actions)
   - Common Rationalizations table (if the skill enforces discipline)
   - Error handling for tool failures

   PROMPT ENGINEERING
   - <EXTREMELY-IMPORTANT> tags for critical rules
   - Emphasis markers preventing Claude from skimming past guardrails
   - Decision trees for complex classification logic

   TOKEN EFFICIENCY
   - Body under 5,000 words (ideal: 1,500-2,000 for skills, flexible for commands)
   - Reference material in separate files if large
   - Progressive disclosure (metadata → body → references)

   TOOL USAGE (if applicable)
   - Correct tool names and parameter formats
   - ToolSearch step for deferred/MCP tools
   - Fallback guidance for failures

   SAFETY (if the skill takes actions)
   - Confirmation before destructive/irreversible actions
   - Undo guidance

   OUTPUT FORMAT (if the skill produces output)
   - Structured, actionable, includes links where appropriate

3. Return your review as:

   ### Priority 1: Critical (significantly impacts reliability)
   [numbered items with specific suggestions]

   ### Priority 2: Important (improves quality)
   [numbered items]

   ### Priority 3: Nice to have (polish)
   [numbered items]
```

#### Subagent B: Domain research

Prompt (fill in `[SKILL_NAME]`, `[SKILL_DOMAIN]`, and `[SKILL_CONTENT]`):

```
You are a domain expert reviewing whether a Claude Code skill's technical
content is accurate and follows best practices for its domain.

## Skill under review

Name: [SKILL_NAME]
Domain: [SKILL_DOMAIN]

Content:
---
[FULL SKILL.MD CONTENT]
---

## Review process

1. Search the web for current best practices in this domain:
   - Official documentation for tools/services the skill interacts with
   - Industry best practices for the workflow being automated
   - Common pitfalls and anti-patterns
   - Recent changes or updates (search with current year)

2. Read codebase files the skill references to verify:
   - File paths actually exist
   - Code patterns described match reality
   - Configuration details are accurate
   - Tool parameters and API details are correct

3. Evaluate:

   ACCURACY
   - Are technical details correct?
   - Are tool/API parameters accurate?
   - Are heuristics/rules sound?

   COMPLETENESS
   - Important domain best practices the skill misses?
   - Common pitfalls not addressed?
   - Newer/better approaches available?

   SAFETY IN CONTEXT
   - Could the skill's actions cause problems in this domain?
   - Are guardrails appropriate for the domain's risk level?
   - Is the automation level appropriate?

4. Return your review as:

   ### Domain accuracy issues
   [specific inaccuracies or outdated information]

   ### Missing best practices
   [domain practices the skill should incorporate]

   ### Domain-specific improvements
   [suggestions requiring domain knowledge]

   ### Verified as correct
   [what you confirmed is accurate]
```

### 3. Synthesise findings

If either subagent fails or returns empty results, report which review could not be completed and why. Proceed with the synthesis using whichever results are available.

After both subagents return, combine into a single review:

```markdown
## Skill Review: [skill-name]

### Overall assessment
[1-2 sentences: ready to use, needs minor fixes, or needs significant rework]

### Critical fixes (do before using)
[Combined P1 items from both subagents]

### Important improvements
[Combined P2 items]

### Polish
[Combined P3 items]

### Domain validation
[Summary of what was confirmed correct and what needs fixing]

### Recommended next steps
1. [specific action]
2. [specific action]
```

### 4. Apply fixes

Present the synthesized review. Ask the user which items, if any, they want fixed. Do NOT make any changes until the user confirms.

Apply confirmed fixes in priority order (Critical first).

After applying fixes, re-read the skill for a quick sanity check. Do not re-run the full review unless the user asks.

## Examples

```
/skill-reviewer .claude/skills/sentry-triage/SKILL.md
→ Reviews the sentry-triage skill with Sentry monitoring as the domain

/skill-reviewer ~/.claude/skills/browser-verification/SKILL.md
→ Reviews browser-verification with browser automation as the domain

/skill-reviewer
→ Prompts for which skill to review
```

## Tips

- For skills interacting with external services (Sentry, Linear, CI), the domain subagent is especially valuable — catches API changes and best practice evolution
- For pure-process skills (TDD, debugging), the structural review matters more
- If a skill is very short (< 200 words), the domain subagent may not be needed — skip it
- The structural subagent reads superpowers skills fresh each time to pick up pattern updates
