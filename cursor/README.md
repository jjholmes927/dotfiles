# Cursor CLI workflows

This adapter installs complete personal and Beam workflow sources as Cursor skills
under `~/.cursor/skills/`. The canonical repositories still own their content;
dotfiles owns installation and [Cursor tool mappings](compat.md).

## Install or refresh

Install and authenticate [Cursor CLI](https://cursor.com/docs/cli/overview), then
install/update the desired Claude user plugins as described in the
[package map](../docs/agent-setup.md#install-update-and-remove). From this checkout:

```bash
python3 cursor/install.py
python3 cursor/install.py --package beam --if-installed
```

The personal import requires joel-workflow 2.20.0 or newer and includes e2e,
ship, verify, verify-ui, investigate, codex-collab and writing-pr-descriptions.
The optional Beam import includes socratic-codebase-interview and review-pr.
Other package workflows remain outside this managed set. Source dependencies
are resolved from their recorded package roots with Cursor's tool mappings.

Imports reuse the Codex importer's file-writing/provenance engine with an explicit
Cursor compatibility document. They never copy Codex's generated instructions.
Each package has its own manifest (`workflow-migration.json`, `beam-migration.json`)
recording the selected source, source hashes, generated hashes and generator hashes.
Existing managed files/links are backed up under `~/.cursor/backups/`; original
symlink targets, unrelated skills, MCP configuration, login and model/permission
settings are preserved. Repeating an unchanged import writes no files.

For a preview without changing your live Cursor installation:

```bash
python3 cursor/install.py --target /tmp/cursor-workflow-preview
```

Use `--source /path/to/plugin` for an explicit source preview. To roll back,
restore only the managed files listed in the relevant backup and its manifest,
or reinstall the previously selected package version and regenerate adapters.
Start fresh sessions to reload the catalog.

## Cursor and Kandev

Cursor also discovers Claude/Codex skill directories. Check discovery and actual
source selection in the installed CLI; a skill name alone does not prove the
Cursor adapter was selected. Project-level skills may also override user skills.

Use Kandev's existing Cursor profile with the shared workflow's explicit execution
and review routes. Begin with direct implementation and the existing separate
Codex review route. Kandev supplies its task-specific MCP tools; standalone Cursor
uses its own MCP configuration. This installer does not change either configuration.
Keep model selection and authentication local. Native subagents require explicit
authorization; no workflow stage is complete merely because a turn ended.
