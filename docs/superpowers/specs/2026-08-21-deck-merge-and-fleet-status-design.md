# Deck window merge + fleet-status sidecar — design

2026-08-21. Follows the operator workflow doc (`docs/operator-workflow.md`). Two changes ship now; the custom fleet-inbox TUI is explicitly parked for its own design session.

## Goal

1. Stop swapping between the fleet and ops windows: merge fleet view, ops shell, and cheat sheet into one tmux window.
2. Give background streams a machine-readable end-state ("complete" vs "awaiting a human") that nothing has to parse out of prose.

## Out of scope

- The custom inbox TUI (`fleet`) that would consume the sidecar files — parked, gets its own spec. Nothing here may block it: the sidecar format below is its input contract.
- The `/e2e` skill change that calls `fleet-status` as its final stage — lives in the `jjholmes927/jjholmes927-claude-skills` plugin repo, one line, done there.

## Component 1: deck() merged window

`deck` builds two windows instead of three:

```
tmux "interpret"
├── 0 deck                                    ← live here
│   ├── fleet pane (left, ~2/3 width): claude agents --cwd $ENG_ROOT
│   │                                  --dangerously-skip-permissions
│   └── right column (46 cols):
│       ├── cheat pane (top, remaining height): deck-cheat, clipped
│       │   from the bottom via head at pane height so the command
│       │   reference stays visible; prefix ? popup = full sheet
│       └── ops pane (bottom, 14 rows): bash, auto-runs clone-status
└── 1 pair                                    ← unchanged, one deep-work session
```

- `pair()` and `prefix P` unchanged (they target `:pair` only).
- Every `deck` invocation runs `tmux source-file ~/.tmux.conf` when a server is already up, so a dotfiles pull landing after server start can no longer leave bindings stale (root cause of the 2026-08-21 `prefix ?` bug).
- The fleet pane keeps the native agents view. When the custom TUI is ready and trusted, swapping it in is a one-line change in `deck()`.
- Existing sessions keep their old layout until killed and rebuilt; `deck` never restructures a live session.

## Component 2: fleet-status

Executable script at `bin/fleet-status`, symlinked into `~/.local/bin` (already on PATH) so agents' Bash tool can call it — a `.profile.d` function would not be visible there.

```
fleet-status complete "INT-842 done, PR #9403"
fleet-status awaiting "need staging creds"     [--stop]
```

- Writes `~/.claude/fleet-status/$CLAUDE_CODE_SESSION_ID` (dir created on demand; that is the var agent shells actually set — legacy `$CLAUDE_SESSION_ID` honoured as fallback), single line, tab-separated: `state<TAB>ISO-8601 timestamp<TAB>note`. Rewrites on repeat calls — last call wins.
- Errors clearly when neither session var is set (not inside a Claude session); `--session <id>` overrides for manual use.
- `--stop` additionally runs `claude stop` on the session's short id (first 8 chars) for fire-and-forget runs. Default leaves the session idle and peekable.
- The completion unit is the stream (session) — not the ticket, not the PR. A ticket can span many streams and a PR can be ticketless, so the note carries refs free-form and Linear/GitHub keep owning their own lifecycles.
- Stale files are harmless (session ids are UUIDs, never reused) — no reaper until something actually needs one.

## Component 3: new-agent fallback line

`new-agent` appends one sentence to every dispatched prompt (alongside the existing branch note):

> When your work is fully complete, or you are parked waiting on a human, record it: `fleet-status complete|awaiting "<one line, include ticket/PR refs>"`.

Streams running `/e2e` get the call from the skill's final stage instead; the fallback line covers ad-hoc dispatches and costs a single sentence.

## Component 4: docs

- `docs/operator-workflow.md`: layout diagram + window table (§1), component rows for the merged window and `fleet-status` (§2), bootstrap step for the `~/.local/bin` symlink (§5).
- `tmux/deck-cheatsheet.txt`: "FLEET (window 0)" → pane wording, add `fleet-status`, keep the 42-col hard wrap.

## Verification

1. Kill the tmux session, run `deck`: merged window renders (fleet pane live, cheat clipped not scrolled, ops 14 rows running clone-status), pair window present, `prefix ?` and `prefix P` work.
2. `fleet-status complete "test"` inside a session writes the file with correct content; `--session`/missing-id paths error as specified; `--stop` stops a throwaway background session.
3. `new-agent <lane> --effort low "reply OK"` dispatch shows the fallback line in the session's prompt.
