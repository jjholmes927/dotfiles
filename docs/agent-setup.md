# Agent setup and skill ownership

Dotfiles is the index and installation wiring for separately maintained workflow packages. The [operator workflow](operator-workflow.md#shared-lifecycle-contract) defines how they work together; [Kandev setup](kandev-setup.md) describes the current launcher. Edit a skill in its canonical repository, then release it and refresh its adapters.

Snapshot: 22 September 2026, updated after the Socratic Codex port. Versions below are observed installations, not claims about upstream latest releases. The Beam/personal inventory contains 29 entries: 12 skills and 17 commands. This document records ownership decisions, installed adapters and remaining gaps; Kandev routing is unchanged.

## Package map

| Package / owner | Canonical source and purpose | Observed revision | Installation and harness support |
|---|---|---|---|
| Beam / team | [wearebeam/beam-claude-skills][beam]: team and product workflows | 1.26.0, `467c8048983b48b908b2f57e10a1d22b741af75f` | Claude plugin; OpenCode imports skills and prefixes commands with `beam-`; Codex has the complete Socratic interview source adapter |
| Personal / Joel | [jjholmes927/jjholmes927-claude-skills][personal]: personal delivery and working methods | 2.17.0, local source `4b17559fb072c1891e8c56d0086b6fa3441252c7` | Claude plugin; OpenCode adapters; four complete Codex adapters, plus separate older ports |
| Superpowers / upstream | [obra/superpowers][superpowers], distributed by [obra/superpowers-marketplace][superpowers-marketplace]: planning, debugging, testing and review methods | 6.1.1, `d884ae04edebef577e82ff7c4e143debd0bbec99` | Claude plugin; OpenCode loads upstream `.opencode/plugins/superpowers.js`; no dedicated Codex installation observed |
| Claude official / upstream | [anthropics/claude-plugins-official][claude-official]: `claude-md-management`, `ruby-lsp`, `linear`, `frontend-design` | First two 1.0.0; latter two `c447c3207a42` | Claude plugins; OpenCode imports `revise-claude-md`, `claude-md-improver`, `frontend-design`; Claude hooks/LSP registration are not imported |
| Dotfiles / Joel | [This repository][dotfiles]: [Claude](../claude/README.md), [Codex](../codex/README.md), [OpenCode](../opencode/README.md), local helpers and compatibility rules | Record the checked-out Git revision when installing | Harness installers, shared [MCP definitions](../claude/mcp-servers.json); authentication and model selections stay machine-local |
| Kandev / application + local configuration | [Setup](kandev-setup.md), [configure.py](../kandev/configure.py), [config example](../kandev/kandev-fleet.example.json): intake, workspaces, profiles and task state | Current local settings/API are authoritative; the script still configures a Claude-specific watch profile | Kandev selects an installed harness; it does not itself supply all that harness's skills |
| Host-managed packages / upstream or account | Codex plugin catalog and system skills; Claude account-synced skills | Inspect the active session/catalog, not directory names alone | Managed through their host; separate from the 29 Beam/personal entries and these dotfiles installers |

### Where installed state lives

| Surface | Source / install record | How to inspect or refresh |
|---|---|---|
| Claude plugins | `~/.claude/plugins/installed_plugins.json`, `known_marketplaces.json`, enabled plugins in settings; sources under the recorded `installPath` | `claude plugin list`; update through the plugin CLI, never patch cache files |
| Codex shared workflows | `~/.codex/skills/{ship,verify,verify-ui,writing-pr-descriptions}`; `~/.codex/workflow-migration.json` records source paths and hashes | `python3 codex/sync-workflow.py`; uses the installed personal user plugin |
| Codex Beam interview | `~/.codex/skills/socratic-codebase-interview`; `~/.codex/beam-migration.json` records source/version/hash | `python3 codex/sync-workflow.py --package beam`; imports only this skill from the enabled Beam user plugin |
| Codex remaining personal skills | Symlinks from `~/.codex/skills/` into [codex/skills](../codex/skills) | [Codex bootstrap](../codex/README.md); these separate ports need reconciliation before replacement |
| OpenCode | `~/.config/opencode/{commands,skills}`, `migration.json`, configured upstream Superpowers plugin path | [Full install and doctor](../opencode/README.md), or `python3 opencode/install.py --workflow-only` for just the personal package |
| Kandev | `~/.config/kandev-fleet.json`, local Kandev settings/API and task records | [Kandev setup](kandev-setup.md); preview current settings before applying its mutating installer/configurer |
| Other host-managed sources | `~/.codex/plugins/cache/`, Codex system skills, `~/.claude/skills/synced/`; shared discovery directories such as `~/.agents/skills/` when present | Inspect the host's resolved catalog; a cached directory alone does not establish an enabled skill |

The personal 2.17.0 marketplace currently points to `~/.local/share/joel-workflow/releases/2.17.0-4b17559fb072`. This is a committed local release, not yet published upstream. Its `workflow-release.json` records the source commit and file hashes. Upstream personal updates are paused while this directory is the selected marketplace source. The [release procedure and rollback](../codex/README.md#shared-delivery-workflow) explain how to move back to published releases.

## Install, update and remove

Start from a deliberate dotfiles revision and the package identities above. Commands run from the dotfiles root unless stated otherwise. Model/MCP authentication is a separate per-machine prerequisite.

1. Install the required CLIs and [Claude configuration](../claude/README.md#setup-on-a-new-machine). Register the desired marketplace source, then install its user plugin. The marketplace IDs below are exact; only install the packages needed on this machine.

   | Marketplace source | Plugin ID |
   |---|---|
   | `https://github.com/wearebeam/beam-claude-skills.git` | `beam-claude-skills@beam-claude-skills` |
   | `jjholmes927/jjholmes927-claude-skills` | `joel-workflow@jjholmes927-claude-skills` |
   | `obra/superpowers-marketplace` | `superpowers@superpowers-marketplace` |
   | `anthropics/claude-plugins-official` | `<name>@claude-plugins-official`, using one of the four observed names above |

   Use `claude plugin marketplace add <source>` then `claude plugin install <plugin-id> --scope user`. During the unpublished parity release, use the [local snapshot installer](../codex/README.md#shared-delivery-workflow) for the personal package instead. A fresh machine cannot recover that local release from GitHub until its commit is published or supplied locally.
2. Run the chosen [Codex](../codex/README.md#setup-on-a-new-machine) and [OpenCode](../opencode/README.md#install-or-refresh) installers after their source packages exist. Codex's shared importer requires the parity resolver; an older personal release is rejected. Keep provider login and project access separate from skill installation.
3. For a published package update, run `claude plugin marketplace update <marketplace-name>` and `claude plugin update <plugin-id>`, then regenerate dependent adapters. Refresh the Codex interview with `python3 codex/sync-workflow.py --package beam` after Beam changes. `--workflow-only` refreshes the personal package only; use the full OpenCode installer after Beam, Superpowers or official plugin changes. Updating Claude alone does not refresh other harnesses. Restart sessions to reload catalogs.
4. Check plugin IDs/versions, each generated source path and hash, and OpenCode's `doctor.py`. Exercise affected workflow scenarios separately: discovery and source equality are not E2E proof. For an isolated adapter preview, use the target-directory examples in the harness READMEs.
5. To remove a package, first identify its callers in this map and the generated manifests. Uninstall it with `claude plugin uninstall <plugin-id> --scope user`. Remove only its identified generated adapters and native plugin reference, preserving unrelated configuration/authentication; OpenCode's installer does not prune old adapters. Retire a marketplace only after its remaining packages and callers are accounted for. Follow the harness backup instructions for rollback rather than deleting a whole skill directory tree.

## Ownership and overlapping names

The owner below is the chosen maintenance home. It does not imply original authorship or that every runtime already uses that source. Repository guides retain authority over project conventions, runtime setup and PR requirements; current user authorization remains the action boundary.

| Overlap | Ownership decision | Current state and reconciliation still needed |
|---|---|---|
| `ship`, `verify-ui` | Personal versions define Joel's delivery workflow; Beam versions remain explicit team variants | Shared personal adapters now serve Codex and unprefixed OpenCode commands; `/beam-ship` and `/beam-verify-ui` remain distinct. Use explicit plugin/variant selection in Claude. Do not merge their bodies silently |
| `brag-doc`, `pick-up-linear-ticket` | Personal is the default for Joel's workflow; Beam retains a separately named team entry | Codex has independent ports. Replace those with shared adapters after verifying dependencies and behaviour; retain team variants until their callers are audited |
| `review-pr` | Beam owns the existing team review; personal remains a pointer to it | The personal command requires Beam access. Codex's independent reviewer is not a complete implementation of that pointer. A personal-only reviewer must be explicitly extracted/adapted before relying on it without Beam |
| `skill-reviewer` | Personal owns the reusable review method for Joel's workflow; Beam keeps its team entry | Both source commands and the Codex port still differ. Reconcile their criteria before generating the Codex adapter; keep harness-specific authoring guidance in adapters |
| `newspaper` | Personal plugin is canonical | [Dotfiles command](../claude/commands/newspaper.md) is a legacy duplicate, pending caller audit/removal. OpenCode already prefers the personal command; Claude selection must be explicit |
| `context-check`, `handoff`, `log-error`, `second-brain` | Dotfiles owns the current local utilities; shared wording can later move to the personal package | Claude commands and Codex ports remain separate, with OpenCode importing them. No equivalence claim until compared |
| `save-permissions`, `style`, `simplify` | Harness-specific behaviour belongs in dotfiles adapters | Transcript formats, permission stores, style settings and available review tools differ. OpenCode's native versions deliberately override imported names |
| Superpowers methods | Upstream remains canonical | Reference upstream planning/debugging/review skills; any deliberate fork records the upstream revision and reason instead of becoming an anonymous copy |
| Fleet / `orchestrating-lanes` | Historical tooling, outside the portability work | Kandev replaces that orchestration; no fleet rewrite or removal is implied by this map |

No copies are deleted by this documentation change. A same-name entry is not sufficient evidence that the chosen source is loaded: inspect the adapter manifest or explicitly load the owning package.

## Complete Beam and personal inventory

All entries below are installed in Claude. OpenCode command spellings are shown explicitly; `+ skill` means a corresponding skill adapter is present. Codex **shared** means a complete source adapter with compatibility instructions (personal unless marked Beam); **separate** means an existing independent port with unproven parity; **missing** means no installed entry. These are availability observations, not complete workflow execution results.

Relative paths are resolved inside the linked package at its observed revision: a skill is `skills/<name>/SKILL.md`; a command is `commands/<name>.md`. The provenance column records the first addition visible in the relevant repository, not a claim of original invention. `J:<commit>` is an addition committed by Joel Holmes in the non-shallow personal history. `B?` means Beam's shallow local history cannot establish origin. `JS` is the GitHub-confirmed Socratic addition described below; `R` is the restored investigate source.

### Beam — 5 skills and 8 commands

| Kind / name | Purpose and portability dependencies | Codex | OpenCode | Provenance |
|---|---|---|---|---|
| Skill `cloudflare-tunnel-swap` | Repoint a local tunnel; bundled shell script, Cloudflare account/tunnel configuration and local port names | Missing | `/cloudflare-tunnel-swap` + skill | B? |
| Skill `debug-interpret-conversation` | Investigate one Interpret conversation; Beam records, product guides and diagnostic access | Missing | `/debug-interpret-conversation` + skill | B? |
| Skill `investigate-alert` | Triage incidents; Beam runbooks, Honeycomb/incident context and product ownership | Missing | `/investigate-alert` + skill | B? |
| Skill `sentry-triage` | Review production exceptions; Sentry access, project identifiers and triage policy | Missing | `/sentry-triage` + skill | B? |
| Skill `socratic-codebase-interview` | Test understanding against source, one question at a time; repository reading and host question tool | Shared (Beam) | `/socratic-codebase-interview` + skill | JS |
| Command `brag-doc` | Summarize contributions; GitHub identity, repositories and output destination | Separate personal port | `/beam-brag-doc` | B? |
| Command `commit-archaeology` | Trace change rationale; Git history, PRs and linked tickets | Missing | `/beam-commit-archaeology` | B? |
| Command `get-it-looking-nice` | Run format/lint/type checks; repository tooling | Missing | `/beam-get-it-looking-nice` | B? |
| Command `pick-up-linear-ticket` | Claim and contextualize work; Linear/project access and state conventions | Separate personal port | `/beam-pick-up-linear-ticket` | B? |
| Command `review-pr` | Team review; repository/domain guidance and supported review/delegation tools | Separate personal port | `/beam-review-pr` | B? |
| Command `ship` | Team PR workflow; Git/GitHub, repository checks and evidence tools | Personal shared variant | `/beam-ship` | B? |
| Command `skill-reviewer` | Review skill quality; current authoring guidance and host capabilities | Separate personal port | `/beam-skill-reviewer` | B? |
| Command `verify-ui` | Browser evidence; agent-browser, checkout/staging target and login | Personal shared variant | `/beam-verify-ui` | B? |

### Personal — 7 skills and 9 commands

| Kind / name | Purpose and portability dependencies | Codex | OpenCode | Provenance |
|---|---|---|---|---|
| Skill `codex-collab` | Additional opinion; bundled wrapper, authenticated Codex CLI, complete review brief | Missing | `/codex-collab` + skill | J:`d4d0362` |
| Skill `dev-workflow-iterate` | Workflow review; activity evidence and existing workflow map | Missing | `/dev-workflow-iterate` + skill | J:`ba0e1d5` |
| Skill `e2e` | Plan-to-PR coordination; Superpowers, Codex wrapper/auth, GitHub, ticket intake, ship and conditionally required plan-rendering capability | Missing | `/e2e` + skill | J:`12eacee` |
| Skill `guideline-refresher` | Refresh conventions; repository history, review evidence and guideline locations | Missing | `/guideline-refresher` + skill | J:`4d03319` |
| Skill `investigate` | Evidence-backed investigation without implementation; Linear and relevant data sources | Missing | `/investigate` + skill | R |
| Skill `orchestrating-lanes` | Legacy parallel dispatch; Fleet/new-agent dependencies | Missing | `/orchestrating-lanes` + skill | J:`919f073` |
| Skill `writing-pr-descriptions` | What/Why PR writing; project PR guide and publication context | Shared | `/writing-pr-descriptions` + skill | J:`f8bed02` |
| Command `brag-doc` | Contribution summary; GitHub activity and output destination | Separate | `/brag-doc` + skill | J:`947eb74` |
| Command `brief` | Daily actions/decisions brief; available personal information sources | Missing | `/brief` | J:`63c2e22` |
| Command `newspaper` | Rewrite a draft as headline/impact/detail; no sending implied | Missing | `/newspaper` | J:`459f1b2` |
| Command `pick-up-linear-ticket` | Claim/contextualize work; Linear, repository and plan workflow | Separate | `/pick-up-linear-ticket` + skill | J:`947eb74` |
| Command `review-pr` | Pointer to Beam review; Beam package and access required | Separate | `/review-pr` + skill | J:`947eb74` |
| Command `ship` | Verify/publish/CI feedback; GitHub, verify, PR writing, project tools | Shared | `/ship` + skill | J:`947eb74` |
| Command `skill-reviewer` | Skill-quality review; source and harness authoring guidance | Separate | `/skill-reviewer` + skill | J:`947eb74` |
| Command `verify-ui` | Browser proof; agent-browser, URL resolver, login and attachment policy | Shared | `/verify-ui` + skill | J:`947eb74` |
| Command `verify` | Behavioural evidence tied to code tree; relevant runtime/read-back tools and verify-ui when needed | Shared | `/verify` | J:`a2fa4a9` |

Codex additionally has the five dotfiles utilities listed in the ownership table, for 14 top-level custom skills including the Beam interview adapter. Other dotfiles entries include [release-check](../claude/commands/release-check.md), [style](../claude/commands/style.md) and eight `review-*-openai` / `review-*-gemini` commands under [claude/commands](../claude/commands). Those older review commands require a `code-reviewer` MCP absent from the shared MCP list; their presence is not a working alternate reviewer. OpenCode exposes release-check; Codex has no corresponding installed skill. Host-managed plugin/system skills are additional.

## Provenance and a future personal setup

**JS:** [Beam commit 467c804][socratic-addition] adds `skills/socratic-codebase-interview/SKILL.md`, authored by Joel Holmes. GitHub's commit file list confirmed the addition; the shallow local checkout alone would misleadingly attribute every Beam file to that commit. Original authorship of the other Beam entries remains unverified here. Package maintenance ownership stays with Beam regardless of who committed a file.

**R:** Personal commit `4b17559` restored `investigate` unchanged from the installed 2.16.0 cache while reconciling release contents. It is a restoration record; its original author/revision has not been established. Likewise, the personal commands added together in `947eb74` may incorporate earlier material; the record proves addition to this repository only.

| Candidate to carry into a personal setup | Current counterpart | Adaptation before relying on it independently |
|---|---|---|
| Socratic interview | Codex adapter from Beam; no personal-package fork | Refresh follows Beam source. A future independent personal copy records Beam revision/path and its own maintenance home |
| Commit archaeology and formatting checks | No dedicated personal entry | Keep the general method; parameterize repository/ticket access and supported project commands |
| Tunnel swap | No personal entry | Preserve the bundled script and configure personal account, tunnel and local targets |
| Team PR review | Personal pointer plus separate Codex reviewer | Choose a standalone review contract, replace Beam-only assumptions and verify behaviour before removing Beam access |
| Interpret/alert/Sentry investigation | Generic personal `investigate` covers process, not Beam diagnostics | Separate investigation method from product records, runbooks, telemetry projects and access |
| Ship, UI verification, ticket intake, brag docs, skill review | Personal variants already exist | Keep the selected personal source; audit remaining Beam dependencies and independent ports instead of copying again |

When a copy or extraction is actually made, add a record here with: original repository/path/revision and author evidence; destination repository/path/revision; upstream link; why it diverged; remaining dependencies; and maintenance policy (follow upstream or independent fork). Distinguish an adapter that still needs Beam source access from a standalone personal copy. Record unknown provenance explicitly; never infer that everything in a personal repository originated there.

## Maintenance and validation

Update this map with each package/source change, alongside the owning install manifest and affected workflow links. Keep generated caches/manifests machine-local; this readable map links their locations. Introduce a package manifest only when an installer or drift check will consume it.

The current release was checked for source/hash parity and focused decision scenarios. The starter evaluation suite lives in the [personal repository][personal] under `evals/`; the original baseline was 9 passed/1 failed, followed by 4 passing targeted cases after the parity fix. These runs do not establish full cross-harness E2E parity. [The later E2E evaluation ticket][e2e-ticket] covers real code outcomes, handoffs, recovery, interventions and cost/time.

Guides and evidence consulted: dotfiles installer code and harness READMEs; current plugin registries/manifests; generated adapter manifests; personal Git history; Beam's GitHub addition record; current Kandev workflow step settings; personal E2E/ship/verify sources and project runtime guidance. The [operator contract](operator-workflow.md#current-implementation-gaps) identifies the remaining runtime gaps.

[beam]: https://github.com/wearebeam/beam-claude-skills/tree/467c8048983b48b908b2f57e10a1d22b741af75f
[personal]: https://github.com/jjholmes927/jjholmes927-claude-skills
[superpowers]: https://github.com/obra/superpowers/tree/d884ae04edebef577e82ff7c4e143debd0bbec99
[superpowers-marketplace]: https://github.com/obra/superpowers-marketplace
[claude-official]: https://github.com/anthropics/claude-plugins-official
[dotfiles]: https://github.com/jjholmes927/dotfiles
[socratic-addition]: https://github.com/wearebeam/beam-claude-skills/commit/467c8048983b48b908b2f57e10a1d22b741af75f
[e2e-ticket]: https://app.todoist.com/app/task/6hXxx47R6x5JXFgG
