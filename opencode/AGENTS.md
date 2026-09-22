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
  type (usually `general` or `explore`), only when the session authorizes delegation.
  Otherwise apply optional review lenses sequentially; a required independent
  review needs an authorized separate-context route. Include the complete brief.
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
- E2E's profile selects direct, native or Codex implementation and the review
  route. Use native delegation only when supported and authorized. Children get
  bounded briefs, never recursive E2E orchestration. Record requested and observed
  models separately; two harnesses using the same model are not model diversity.
- In Kandev, use its plan and question tools. Pending/timeout questions are hard
  waiting barriers: end the turn without dependent work until answers arrive.
- Only signal Kandev step completion when the step's actual evidence criteria
  are met, never because a turn ended or the task appears in a Review column.

The installed `migration.json` lists command/skill sources and unavailable
integrations. Resolve relative references in imported workflows against their
original source directory, not the current repository.

For GitHub comments/reviews and Slack messages, obtain approval for the concrete
message unless this session already explicitly authorized sending it. Do not
infer permission to post a review merely from being the PR author.
