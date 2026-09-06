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

- **READY = Linear state Todo + assigned to me + one work-type label.** `agent:implement` → `/e2e <ticket>`; `agent:investigate` → findings comment, no code. The label is the go switch; remove it to withdraw. Kandev never picks the same ticket twice per watch.
- **Lanes** are registered as repositories. Beam lanes (`mn1`…`mn5`) use the magicnotes adapters below; the personal GigMe lane uses `gigme/kandev_worktree_setup.sh` / `kandev_worktree_cleanup.sh`, which write `DB_SUFFIX=kandev_<task dir>` and `PORT` into the worktree `.env` (dotenv-rails, GigMe PR #353), copy `config/master.key` from the lane, and run `bin/setup --skip-server`; cleanup drops only `gigme_*_kandev_<task dir>` databases. Beam lanes (`mn1`…`mn5`) each task gets its own worktree under `~/.kandev/tasks/…` with its own database and ports via `magicnotes/kandev_worktree_setup.sh` (unique `WORKTREE_OFFSET=kandev-<task dir>`). `kandev_worktree_cleanup.sh` drops those databases when Kandev reaps the worktree.
- **Human gate** = the `/e2e` plan question, posted through Kandev's own question tool; answer it in the task or on `/threads` at http://localhost:38429.
- **Completion**: `/ship` opens the PR, moves the ticket to In Review and records `fleet-status complete`; Linear's GitHub integration moves it to Done on merge.

## Observer (optional)

`kandev/fleet-observer.sh` polls every minute, appends one line per task to `~/.kandev/logs/fleet-observer.log` (states, pending question, last message, watch errors) and **syncs Linear priority onto Kandev tasks** (Linear urgent/high → high, medium → medium, low → low, none → untouched) because watch-created tasks are always `medium`. `install.sh` installs it as a second launchd agent, `com.jjholmes927.kandev-observer` (keepalive, runs at login), so it starts with the machine like Kandev itself. The Kandev desktop/web UI is only a viewer over the backend; it starts neither the backend service nor the observer. `install.sh` never restarts a running Kandev (that would drop pending plan-gate questions); set `KANDEV_RESTART=1` to force one.

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
| `/e2e` treats a session as "already isolated" only when `CLAUDE_JOB_DIR` is set; a repo without `bin/create_worktree` otherwise gets a nested worktree on the shared database | `configure.py` sets `CLAUDE_JOB_DIR=~/.kandev/tasks` on the Worktree executor profile |
| `POST /api/v1/clarification/<pending_id>/respond` wants `{"answers":[{"question_id":…,"selected_options":["<option_id>"]}]}`; `option_ids` is accepted but recorded as an empty answer, and the agent then stops and waits | resume with a chat message: WS `message.queue.add {session_id, task_id, content}` then `message.queue.send_now {session_id, scope:"all"}` |
| Kandev dedupes tickets only against its own watches | stop any hand-started stream on the same ticket (`claude stop <id>`) before labelling it |
