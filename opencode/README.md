# OpenCode

Reuse the existing Claude workflows in OpenCode, with native tool adapters,
Attention-kind responses, shared MCP definitions, and tmux notifications.

## Install or refresh

```bash
bash opencode/install.sh
python3 opencode/doctor.py
```

Restart OpenCode after installation. Your provider credentials and selected
model remain machine-local. Try `/context-check`, `/handoff`, `/review-pr`,
`/verify-ui`, `/pick-up-linear-ticket INT-123`, or `/ship` in a project.

The installer requires Python 3. It uses the existing Claude plugin registry;
install the desired Claude plugins first on a new machine, then rerun it.
For joel-workflow, it prefers `~/Engineering/tools/jjholmes927-claude-skills`
when present and otherwise uses the installed plugin directory.

## What is installed

| Source | OpenCode destination |
| --- | --- |
| `opencode/AGENTS.md` | Global compatibility rules |
| `claude/CLAUDE.md` and Attention-kind style | Additional instruction files |
| Dotfiles commands and joel-workflow commands | Native slash-command adapters |
| Codex skills and enabled Claude plugin skills | Native skill adapters |
| Beam commands | `/beam-...` commands to avoid collisions with personal workflows |
| Superpowers' bundled OpenCode adapter | Native plugin, including skill discovery and bootstrap |
| `claude/mcp-servers.json` | OpenCode MCP entries |
| `opencode/plugins/notifications.js` | tmux bell on idle, permission, or question events |

Adapters read the original workflow when invoked. Full instructions, scripts,
and relative references stay together in their original source directory.
`${CLAUDE_PLUGIN_ROOT}` is mapped to that directory. This avoids duplicating
private Beam content into this dotfiles repository. Source directories must
remain available; rerun the installer after plugin updates or moving dotfiles.

Personal plugin commands take precedence over dotfiles command copies. The
native `style`, `save-permissions`, and `simplify` adapters take precedence over
imported versions. Matching commands also supply the corresponding skill so
`ship` does not accidentally invoke the older Codex implementation.

The generated `~/.config/opencode/migration.json` lists every imported source
and known limitation. `~/.claude/skills` and `~/.agents/skills` are also discovered
by OpenCode itself. Existing duplicate skill names there may produce warnings.

## MCP authentication

Model authentication is separate from MCP authentication:

```bash
opencode mcp auth linear-server
opencode mcp auth sentry
opencode mcp auth honeycomb
opencode mcp list
```

`gws` is configured disabled if the CLI or its MCP subcommand is unavailable.
After installing a compatible CLI and its local authentication, enable the
entry in OpenCode's global config. The installer preserves existing MCP
overrides, including disabled entries.

## Configuration and backups

The installer merges defaults into `~/.config/opencode/opencode.json`, preserving
existing settings, provider configuration, model choices, MCP overrides, and
permissions. `opencode.jsonc` is left intact and can override the JSON settings.
The default instructions and Superpowers adapter are added on first install;
the chosen response style is preserved on subsequent installs.

Changed destination files are backed up under
`~/.config/opencode/backups/<timestamp>/`. Reinstalling unchanged inputs creates
no new backups. Generated adapter files are installer-owned: edit their original
source, or create a separate OpenCode command/skill for personal overrides.
The installer does not remove old adapters; remove retired commands explicitly
after checking `migration.json` if a source plugin is uninstalled.

To inspect an isolated install without touching the live config:

```bash
bash opencode/install.sh --target /tmp/opencode-trial
```

To undo an installation, restore overwritten files from its backup directory
and remove only newly created paths listed by the migration report (commands,
skills, compatibility AGENTS.md, notifications plugin, and generated config).
Keep provider auth and unrelated OpenCode files. If OpenCode had no
`opencode.json` before this install, remove that generated file to revert to
the existing `opencode.jsonc`.

## Compatibility boundaries

- Workflow discovery is verified with `doctor.py`; it is not proof that every
  workflow has run successfully against a live project.
- `/style` changes OpenCode instructions. `/save-permissions` uses visible
  OpenCode approvals rather than parsing Claude/Codex transcripts.
- GitHub comment/review commands and `gh api` request permission. These native
  command patterns are not a full shell parser or an exact recreation of the
  Claude pre-tool hook; the global instructions also preserve message approval.
- Old `/review-*-openai` and `/review-*-gemini` commands still require their
  `code-reviewer` MCP and requested models. Use `/review-pr` for the configured
  agent's review, or configure that MCP before using those older commands.
- `/e2e` and `/codex-collab` retain their authenticated Codex CLI dependency.
  Fleet/orchestration commands retain their original external CLI dependencies.
  Begin with `/e2e --dry-run` when trying that pipeline in a project.
- Claude session history, automatic memory, statusline, OTel telemetry, plugin
  updater hooks, and fleet launchers are not migrated. OpenCode runs its own LSP
  support; the Claude ruby-lsp plugin is not loaded.
- Claude Artifacts/Chrome and Codex in-app connectors are not supplied by copying
  skills. Adapters use available equivalents or report a missing capability.

## Checks

For notification-plugin development, install the local development tools with
`pnpm --dir opencode install`, then run
`pnpm --dir opencode run format:fix` and `pnpm --dir opencode run lint:fix`
before committing. They are not needed to run the installer.

```bash
python3 -m unittest discover -s opencode -p 'test_*.py' -v
node --check opencode/plugins/notifications.js
bash -n opencode/install.sh
python3 opencode/doctor.py
```

Official references: [rules](https://opencode.ai/docs/rules/),
[skills](https://opencode.ai/docs/skills/),
[commands](https://opencode.ai/docs/commands/),
[MCP](https://opencode.ai/docs/mcp-servers/),
[plugins](https://opencode.ai/docs/plugins/).
