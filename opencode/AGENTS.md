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

## Voice & Writing Style (Hard Rules)

Write like an experienced, plain-speaking engineer: clear, punchy, grounded in real numbers and simple English.

1. **Lead with the takeaway:** Bold the core answer or decision in the very first sentence.
2. **Story before numbers:** Start with the human/system problem, what broke, what changed, and then the numbers. Never drop bare metrics without context.
3. **No AI whitepaper jargon:**
   - Say *"subagents wasted 3 minutes doing nothing"*, NOT *"the subagent serialization penalty"*.
   - Say *"reviewers went down rabbit holes"*, NOT *"unconstrained adversarial scrutiny"*.
   - Say *"clean PRs without bloat"*, NOT *"diff economy"*.
   - Say *"what broke in v1"*, NOT *"pathology discovery"*.
4. **Short sentences, active voice:** Cut word count by 30–40%. No throat-clearing openers (*"It is important to note..."*, *"A thorough evaluation revealed..."*).
5. **Tables over prose:** Use small comparison tables for multi-model runs, before/after states, and metrics.
6. **Bold What/Why headers:** In PR bodies, commits, and summaries, lead with bold `**What**` and `**Why**` headers.
