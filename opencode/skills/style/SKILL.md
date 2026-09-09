---
name: style
description: Change OpenCode's response style for this session or persist a choice of attention-kind, spartan, rundown, or default.
---

Read the requested style from the dotfiles `claude/output-styles/` directory
identified in the installed migration.json. Ignore its Claude frontmatter and
apply its response-writing instructions to this session. With no argument, ask
which style to use: attention-kind, spartan, rundown, or default.

For a persistent choice, replace only the style entry in the global
`opencode.json` instructions array with that file's absolute path. Default means
remove that entry. Preserve every other setting and instruction path, back up
the file, and tell the user to restart OpenCode. Never edit Claude settings.
