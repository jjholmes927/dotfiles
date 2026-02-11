---
description: Process second brain inbox or run second brain commands
---

# Second Brain

Your second brain vault is at: `~/Documents/repos/second-brain/`

## First: Load Full Instructions

Before doing anything, read the vault's CLAUDE.md for complete instructions:
```
~/Documents/repos/second-brain/CLAUDE.md
```

This contains:
- Persona (chief of staff for engineering lead with ADHD)
- All commands (process inbox, weekly review, prep for 1:1, etc.)
- Folder structure and templates
- Trust & safety rules
- ADHD-friendly patterns

## Quick Reference

**Vault location:** `~/Documents/repos/second-brain/`

**Key folders:**
- `00-inbox/` - Dump zone, process this
- `01-projects/` - Active work
- `02-people/` - Relationships & 1:1s
- `03-decisions/` - Decision records
- `04-learnings/` - What you've learned
- `05-reflections/` - Weekly reviews
- `06-ideas/` - Backlog, tech debt
- `raw/` - Processed source material (never edit)

**Core commands:**
- "process inbox" - Sort, file, synthesize inbox contents
- "weekly review" - Friday summary and reflection
- "what should I focus on" - Priority recommendations
- "prep for 1:1 with [person]" - Meeting prep
- "what's going on with [X]" - Project/topic status

## Critical Rules
- Always use absolute paths: `~/Documents/repos/second-brain/...`
- Never edit files in `raw/`
- For large docs (>500 lines): chunk and confirm coverage
- Move inbox items to `raw/` (never delete)

## Error Logging
Log errors to: `~/Documents/repos/second-brain/tmp/error-logs/`
Then categorize: project-specific → project, general → ~/.claude/CLAUDE.md
