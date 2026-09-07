# Kandev fleet setup

**TL;DR.** Kandev is the control plane that picks READY Linear tickets up and runs `/e2e` on them in a lane worktree. Install is two commands on any machine: put the Linear key in the Keychain, run `kandev/install.sh`. Everything else is idempotent and driven by `~/.config/kandev-fleet.json`. Background and evidence: `docs/agent-control-plane-audit.md` §26a–26b.

## Install (new or existing machine)

```bash
security add-generic-password -a "$USER" -s linear-api-key -w '<linear personal API key>' -U
~/engineering/dotfiles/kandev/install.sh      # first run writes ~/.config/kandev-fleet.json from the example and stops
$EDITOR ~/.config/kandev-fleet.json            # lanes, Linear team, labels, prompts for THIS machine
~/engineering/dotfiles/kandev/install.sh      # installs/starts the launchd service and applies the config
```

Re-run `install.sh` (or just `python3 kandev/configure.py`) after editing the config or upgrading Kandev; it prints `CHANGED …` lines or `no changes`.

What `install.sh` does, in order: Homebrew install → `~/.kandev/config.yaml` bound to `127.0.0.1` (refuses to continue otherwise) → warms the npm cache for the pinned Claude ACP adapter → `kandev service install|restart` (launchd, headless, keepalive) → waits for the API → `configure.py`.

What `configure.py` ensures, all by lookup-then-create/patch: lane repositories with the setup and cleanup adapters; the Claude profile with auto-approve and `CLAUDE_CODE_EXECUTABLE` = the installed CLI; the Linear connection from the Keychain (tested); one issue watch per configured label.

## Operating model

- **READY = Linear state Todo + assigned to me + one work-type label.** `agent:implement` → `/e2e <ticket>`; `agent:investigate` → `/investigate <ticket>` (joel-workflow ≥ 2.16.0: claims In Progress, evidence-tagged findings comment, In Review). The label is the go switch; remove it to withdraw. Kandev never picks the same ticket twice per watch.
- **Lanes** are registered as repositories. Beam lanes (`mn1`…`mn5`) use the magicnotes adapters below; the personal GigMe lane uses `gigme/kandev_worktree_setup.sh` / `kandev_worktree_cleanup.sh`, thin wrappers over the repo's own `bin/create_worktree` (`WORKTREE_NAME=kandev-<task dir>` provisions in place: `DB_SUFFIX`, `PORT`, `master.key`, gems, node modules; GigMe PR #353) and `bin/remove_worktree --databases-only`; cleanup refuses any `DB_SUFFIX` not starting with `kandev_`. Beam lanes (`mn1`…`mn5`) each task gets its own worktree under `~/.kandev/tasks/…` with its own database and ports via `magicnotes/kandev_worktree_setup.sh` (unique `WORKTREE_OFFSET=kandev-<task dir>`). `kandev_worktree_cleanup.sh` drops those databases when Kandev reaps the worktree.
- **Human gate** = the `/e2e` plan question, posted through Kandev's own question tool; answer it in the task or on `/threads` at http://localhost:38429.
- **Completion**: `/ship` opens the PR, moves the ticket to In Review and records `fleet-status complete`; Linear's GitHub integration moves it to Done on merge.

## ADHD reading theme (plugin)

`kandev/plugins/adhd-theme` is a CSS-only Kandev plugin: agent messages and plans get a 72-character measure, 1.6 line height, bold in one accent colour so lead-ins pop, headings with a coloured left bar, blockquotes as callouts (green TL;DR; amber warning when the quote opens with an italic label), striped tables, and a 600px plan panel instead of 300px. Kandev requires every plugin to ship a managed binary, so `kandev/plugins/install-plugin.sh` builds a no-op `pluginsdk` server with Go against a shallow clone of the installed Kandev version (`~/engineering/kandev-src`), stages the package under `~/.kandev/plugins/<id>/<version>/`, syncs and enables it. `install.sh` runs it when `go` is installed (`brew install go`). Reload the UI after installing or after editing `ui/theme.css` (re-run the script; bump `version` in the manifest when the CSS changes so Kandev re-stages it).

Conventions the agent text has to follow for the colour to land (also in `~/.claude/CLAUDE.md`): one TL;DR blockquote first (`> **TL;DR** …`), warnings as a blockquote opening with `*Warning:*`, bold lead-ins, at most two emoji signposts per message with a text label. Gate (clarification) text renders only paragraphs, lists and inline bold: no headings, tables or blockquotes there; open with `**Decision needed:**`.

## Observer (optional)

`kandev/fleet-observer.sh` loops `fleet-observer.py` every minute. It appends one line per task to `~/.kandev/logs/fleet-observer.log` (states, pending question, last message, watch errors), **syncs Linear priority onto Kandev tasks** (Linear urgent/high → high, medium → medium, low → low, none → untouched) because watch-created tasks are always `medium`, and runs **quota-resume**: a session that stopped on a usage-limit / rate-limit error is logged `QUOTA-STALLED` with the reset time parsed from the error text (`resets 11pm`, `Resets in 4hr 19min`, `|<epoch>`, `Retry-After`; unparsable → retry every 30 min), and once the reset passes the observer sends Claude Code's own continue prompt into the session over the WebSocket (`kandev/ws-send.mjs`, needs `node`) and logs `QUOTA-CONTINUE`. Sessions Claude Code resumes by itself stay `RUNNING`, so the observer leaves them alone. State lives in `~/.kandev/logs/quota-resume.json`; stalled tasks still count toward `max_inflight`, so the watch does not over-pull while the limit is active. `install.sh` installs it as a second launchd agent, `com.jjholmes927.kandev-observer` (keepalive, runs at login), so it starts with the machine like Kandev itself. The Kandev desktop/web UI is only a viewer over the backend; it starts neither the backend service nor the observer. `install.sh` never restarts a running Kandev (that would drop pending plan-gate questions); set `KANDEV_RESTART=1` to force one.

## Quirks (verified 2026-09-04, Kandev v0.93.0)

| Quirk | Consequence |
|---|---|
| Linear label filter is any-of; no AND / NOT | one watch per work-type label; the label itself is the go switch |
| Kandev's label lookup lists team labels only; workspace-level labels (`agent:*`) are invisible to it | put `label_id` on the watch in the config (ids in the example), or create team-scoped labels |
| The ACP adapter bundles its own Claude Code (2.1.232 in adapter 0.70.0), where `fable` = Fable 5.0; explicit model ids are refused as "not advertised" | profile env `CLAUDE_CODE_EXECUTABLE=<installed claude>` makes sessions run your CLI; `fable[1m]` then resolves to 5.1 |
| Claude probe fails with npm `ETARGET` on a stale npm cache | `install.sh` warms the cache with `--prefer-online`; `kandev service restart` re-probes |
| The launchd service runs with a minimal PATH (nvm + brew + system: no rbenv shims, no `~/.local/bin`), so `bin/create_worktree` hit system Ruby 2.6 and the setup script failed non-fatally, leaving worktrees on the unsuffixed default database | `configure.py` writes the operator's full PATH onto the Worktree executor profile (agents and scripts inherit it); the setup adapter also inits rbenv itself. Re-run `configure.py` after changing PATH |
| Profile edits over HTTP need the `X-Kandev-Interim-Settings-Interlock` header | `configure.py` reads the token from the boot payload |
| No HTTP route to send a chat message; it is the `message.queue.add` WebSocket action | answer gates in the UI, or `answer_question_kandev` over the API while the question is live |
| Pending questions live in memory; a backend restart loses them (the session itself resumes via ACP `session/load`) | after a restart, resume with a chat message rather than the question API |
| While Codex works in the background the session shows `WAITING_FOR_INPUT` and resumes by itself | never read that state alone as "needs human"; look for a pending question |
| Task list is `GET /api/v1/workspaces/<ws>/tasks`; `/api/v1/tasks?workspace_id=` is a 404 | |
| `POST /api/v1/tasks` silently ignores top-level `repository_id` / `base_branch`; an unbound worktree task then runs the agent in whatever checkout it finds (the lane itself) | bind with `"repositories": [{"repository_id": …, "base_branch": …}]` plus `workflow_id`, `workflow_step_id`, `agent_profile_id`, `executor_profile_id`, `start_agent`; `DELETE /api/v1/tasks/<id>` is the only stop |
| The `/ws` API has no client auth and defaults to `0.0.0.0` | keep `server.host: 127.0.0.1`; no Tailscale/mobile exposure |
| `linear.team` in the fleet config is the team **key** (`INT`, `NEV`), not the team name; the name makes every state/label lookup return empty ("state Todo not found") | |
| joel-workflow < 2.15.0 recognised a Kandev worktree only via `CLAUDE_JOB_DIR`; older personal setups put that variable on the Worktree executor, which would also make `/e2e` trust an unbound lane checkout as isolated | update the plugin to ≥ 2.15.0 (`/e2e` detects the worktree from git) and re-run `configure.py`, which strips `CLAUDE_JOB_DIR` from the profile |
| `POST /api/v1/clarification/<pending_id>/respond` wants `{"answers":[{"question_id":…,"selected_options":["<option_id>"]}]}`; `option_ids` is accepted but recorded as an empty answer, and the agent then stops and waits | resume with a chat message: WS `message.queue.add {session_id, task_id, content}` then `message.queue.send_now {session_id, scope:"all"}` |
| Kandev dedupes tickets only against its own watches | stop any hand-started stream on the same ticket (`claude stop <id>`) before labelling it |
| Kandev's own provider-error routing (dynamic profiles: reset-date waiting, candidate fallback) only recognises Claude stderr matching `rate.?limit`, `anthropic_quota_exceeded`, `credit balance`, `subscription`; Claude's "You've hit your usage limit" message is unclassified and stops for manual recovery | the observer's quota-resume covers it; a Codex fallback candidate needs the rule gap fixed upstream (`routingerr/rules.go`) first |
