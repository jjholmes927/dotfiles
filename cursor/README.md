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
Normal imports register/run `workflow-doctor`, which now checks Cursor's personal
and Beam manifests too. Run it after package updates; its refresh commands identify
which package needs regeneration. A Cursor installation without managed adapters
is skipped. Missing manifests with surviving managed skills warn.

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

## Validation and pilot

Checked on 23 September 2026 with Cursor CLI `2026.05.09-0afadcc`; its updater
reported that build current. The live CLI selected `~/.cursor/skills/e2e/` and
read its compatibility and full source during an E2E dry run. Personal source
2.20.3 and Beam 1.26.0 were installed with zero changes on repeat refresh.

Cursor ACP with `gpt-5.6-sol` passed controlled Kandev-shaped MCP question cases:
one unanswered/pending question ended the turn without grading or dependent work;
an answered question was graded, and an explicit end stopped the interview.
The local opt-in Kandev profile **Cursor → Sol workflow pilot** selects this model.
Use it for the next real task with `/e2e --execution direct --review codex` and an
explicit reviewer model. The existing Gemini profile and default workflows remain.

With `gemini-3.8-flash`, skill discovery passed but nested MCP question arguments
were malformed, including null option entries; the same fixture passed with Sol.
Treat that combination's question gate as unverified, not an approval to continue.
This is an observed model/runtime limitation, not a reason to weaken the gate.
These probes cover discovery and question handling through the ACP interface used
by Kandev. They do not establish the real Kandev UI round-trip, native subagents,
or a complete implementation/review/CI lifecycle; those need a real pilot task.
