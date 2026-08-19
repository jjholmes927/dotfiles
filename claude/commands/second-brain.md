---
description: "Manage a personal second brain / knowledge vault. Use when the user says 'process inbox', 'weekly review', 'what should I focus on', 'prep for 1:1', or asks about their second brain, vault, or PKM system."
disable-model-invocation: true
argument-hint: [command or question]
---

# Second Brain

**User request:** $ARGUMENTS

**Vault location:** `~/engineering/second-brain/`

## Load Instructions

1. First verify `~/engineering/second-brain/` exists. If not, STOP and tell the user the vault path was not found.
2. Use the Read tool to read `~/engineering/second-brain/CLAUDE.md` and follow all instructions defined there.

## Critical Rules
- Always use absolute paths: `~/engineering/second-brain/...`
- Never edit files in `raw/`
- For large docs (>500 lines): chunk and confirm coverage
- Move inbox items to `raw/` (never delete)
