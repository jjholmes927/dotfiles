# OpenCode workflow conventions

Use OpenCode's native tools when running imported Claude or Codex workflows.
These compatibility rules apply to every imported skill and command:

- `TodoWrite` means `todowrite`; `AskUserQuestion` means `question`.
- `Read`, `Write`, `Edit`, `Glob`, `Grep`, and `Bash` mean the equivalent native tools.
- `Skill` means `skill`. Resolve plugin-qualified names such as
  `superpowers:brainstorming` against the available skills by their final name.
- For `/command` dependencies, read the installed command Markdown and execute
  its workflow with the supplied arguments; slash commands are not shell programs.
- `ToolSearch` and `mcp__...` identifiers refer to capabilities. Find the matching
  configured MCP tool by function, inspect its schema, and use its actual name.
  Never invent a missing tool or silently skip a required integration.
- `Task` or `Agent` delegation means OpenCode's task tool with an available agent
  type (usually `general` or `explore`). Include the complete review brief.
  Do not pass Claude model aliases such as `opus` or `sonnet` as OpenCode models.
- `EnterPlanMode` and `ExitPlanMode` mean present the plan and obtain any approval
  required by that workflow. Do not call nonexistent tools.
- Claude-only UI features, Artifacts, Chrome tools, and automatic memory are not
  supplied by this migration. Use local Markdown/HTML artifacts or agent-browser
  when they meet the requested outcome; explicitly report any remaining gap.
- Imported frontmatter such as `allowed-tools` is not an OpenCode permission
  boundary. Respect OpenCode permissions and the user's current authorization.
- Claude transcripts/settings and Codex transcripts/rules are not OpenCode state.
  Never write to them to configure OpenCode. Use the native `style` and
  `save-permissions` workflows installed here instead.
- In cross-model workflows, Fable/Claude denotes the coordinating agent's role,
  not a promise about the selected model. Codex/Sol remains the external Codex CLI.
  Report the actual models when known; do not claim cross-model independence if
  both participants use the same model.

The installed `migration.json` lists command/skill sources and unavailable
integrations. Resolve relative references in imported workflows against their
original source directory, not the current repository.

For GitHub comments/reviews and Slack messages, obtain approval for the concrete
message unless this session already explicitly authorized sending it. Do not
infer permission to post a review merely from being the PR author.
