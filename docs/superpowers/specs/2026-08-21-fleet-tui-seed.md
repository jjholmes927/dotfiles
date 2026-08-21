# Fleet TUI — requirements seed (design session pending)

Parked 2026-08-21 after the deck merge shipped. Not a spec — a holding pen for everything the eventual design session must account for, gathered from live use. Add to it; don't build from it.

## Requirements gathered so far

- **One integrated surface**: streams AND lanes. Lanes are already the grouping dimension; fold `clone-status` into the same table (lane header row: branch, clean/dirty, worktree count) so the 56-col ops pane never has to render a wide table again. Ops goes back to being a launcher shell.
- **Real end-states**: read `~/.claude/fleet-status/<sessionId>` sidecars → WORK / GATE / DONE / PARKED / STOPPED buckets, fixing the native view's `done`-means-two-things problem.
- **Short ids visible** per row (`--json` `id` field is already the short form; prefix matching works on the CLI).
- **Answer gates from the inbox**: hidden `tmux new-window -d 'claude attach <id>'` → `capture-pane` shows the question → `send-keys 1 Enter` → kill window. Verified live 2026-08-21 on v2.1.238. Version-fragile (keystroke injection) — keep isolated so the read-only table never breaks with it.
- **Bell + tmux window flag** on transitions into GATE/DONE (the native view only notifies while open; the wrapper must own alerting when it replaces the view).
- **Cleanup surfaced**: `claude rm` reaps only lazy bg worktrees; provisioned worktrees/branches need `git worktree remove` + `branch -D` — the TUI should show orphaned worktrees per lane and offer the reap.

## Pre-work queued before the TUI (from the 2026-08-21 final review)

- `fleet-status` hardening batch: `--` terminator, `--session` missing-value guard, session-id path validation, atomic write (`.tmp` + `mv` — the TUI is the reader that makes this matter).
- `deck`: guard empty `ch`; reconsider the 120-col width floor.
- Wire the `~/.local/bin/fleet-status` symlink into `claude/install.sh`.
- `/e2e` skill calls `fleet-status complete` from its final stage (plugin repo).

## Known constraints

- Subagent shells carry their own `CLAUDE_CODE_SESSION_ID` — a stream must run `fleet-status` itself (the new-agent note already says so) or the sidecar keys to a session the fleet never lists.
- Any `deck`/`pair`/tmux invocation from an agent shell needs `env -u TMUX`.
- Sizing: estimate was ~a day for table + bell + answering; lane integration adds the `clone-status` data source (already a function in `bash/.profile.d/lanes`).
