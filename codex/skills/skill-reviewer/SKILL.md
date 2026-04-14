---
name: skill-reviewer
description: Review a Codex skill or ported command for structural quality and domain accuracy. Use when the user says review this skill, check my skill, skill review, is this skill any good, improve this skill, or asks about skill quality and best practices, or explicitly says use skill-reviewer.
---

# Skill Reviewer

Review a skill for quality.

## Scope

Use this for:
- Codex skills
- ported Claude commands being converted into Codex skills

Do not use it for unrelated markdown docs.

## Workflow

1. Read the target `SKILL.md`.
2. Note companion scripts, references, or assets when present.
3. Compare the skill against current Codex skill patterns:
   - concise metadata
   - clear triggering description
   - when to use and when not to use
   - safe workflow
   - good token discipline
4. Review domain accuracy:
   - check local references first
   - if web search is available, prefer official docs
5. If subagents are available and explicitly allowed, one may focus on structure while another focuses on domain accuracy. Otherwise do both reviews sequentially.

## Output

Return:

```markdown
### Priority 1: Critical
1. ...

### Priority 2: Important
1. ...

### Priority 3: Nice to have
1. ...
```

Prefer specific, actionable feedback over generic praise.
