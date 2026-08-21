# Fleet TUI — design

2026-08-21. Grew from `2026-08-21-fleet-tui-seed.md`; supersedes it. The integrated streams+lanes inbox that eventually replaces the native `claude agents` view in the deck window's fleet pane.

## Goal

One terminal surface for the whole day loop: lane health at a glance, streams sorted by attention, real end-states instead of the ambiguous `done`, and gate answering without leaving the inbox. Kills the last reason the ops pane needed width.

## Shape

- `bin/fleet` — one Python 3 stdlib file (curses), symlinked into `~/.local/bin` like `fleet-status`. No dependencies.
- `tests/fleet_test.py` — unit tests for the pure core (state derivation, sidecar parsing, row/strip formatting), run with `python3 -m unittest`.
- Adoption path: run `fleet` in any pane/window while it earns trust; the native view keeps the deck fleet pane. Cutover later is a one-line change in `deck()` and is OUT of this spec's scope.

## Screen layout (locked with user)

```
LANES  mn1 main✓ 2wt · mn2 main✓ 1wt · mn3 DIRTY 1wt · mn4 ✓ · mn5 ✓
       second-brain main✓ 1wt                      ← dynamic repos, only while active
── BLOCKED ──────────────────────────────────────
▸ 7feaaa4d mn3/phone-hub-routing   12m
    verify run.services.list permission…
── WORKING ──────────────────────────────────────
  092b2a4b mn2/check-the-alert     41m
── COMPLETE ─────────────────────────────────────
  ad68d9fc gather-positive-feedb   2h   COMPLETE: playback pack + link
── AWAITING ─────────────────────────────────────
  3a99b95c investigate-sentiment   3h   awaiting: agenda sign-off
── STOPPED ──────────────────────────────────────
  c1d2e3f4 scribe-rate-limit       1d
```

- **Lanes strip**: configured `$LANES` always shown — root branch, ✓/DIRTY, worktree count (what `clone-status` reports). Any other git repo under `$ENG_ROOT` currently hosting a stream appears dynamically and drops off when quiet. Streams in `$ENG_ROOT` itself show untagged, no strip line.
- **State groups**, attention-first order: BLOCKED → WORKING → COMPLETE → AWAITING → STOPPED. Empty groups collapse.
- Rows: short id · name · age · one line of context (BLOCKED: the waiting reason; COMPLETE/AWAITING: the sidecar note).

## State names (aligned with existing vocabulary — user decision)

No invented terms. CLI states pass through; the `done` split is named by `fleet-status`'s own verbs:

| Bucket | Rule |
|--------|------|
| WORKING | CLI `state == working` |
| BLOCKED | CLI `state == blocked` (plan gates, questions, permission prompts) |
| COMPLETE | CLI `done`/`stopped` + sidecar `complete` |
| AWAITING | CLI `done` + sidecar `awaiting`, or `done` with no sidecar (silent stop reads as "may want attention", never "finished") |
| STOPPED | CLI `stopped`/`failed` without a `complete` sidecar |

Sidecars are consulted only for ended sessions; a stale sidecar from a previous turn never recolors a `working`/`blocked` row.

## Data loop

- Every 3s: `claude agents --json --all`, filtered to `cwd` under `$ENG_ROOT`; one directory read of `~/.claude/fleet-status/` (single-line TSV per file: `state<TAB>ISO-UTC<TAB>note`).
- Every ~15s (staler is fine): per-lane git subprocess calls — `branch --show-current`, `status --porcelain | head`, `worktree list` — same queries `clone-status` makes.
- All subprocess work off the UI thread is unnecessary: calls are fast and the poll tick is the frame; a slow call just delays one repaint.

## Keys

| Key | Action |
|-----|--------|
| `j`/`k`, arrows | move selection |
| `Space` | peek: BLOCKED → live question via hidden tmux attach + `capture-pane`; other states → last assistant text from the session transcript (`~/.claude/projects/<slug>/<sessionId>.jsonl`) |
| `1`–`9` | while peeking a BLOCKED row: answer via `send-keys` into the hidden attach, then kill it and re-poll |
| `Enter` | hand the session to the pair window (send `claude attach <id>` to `:pair`, guarded like `pair()`: refuse if pair is busy, `C-u` first) |
| `r` | `claude rm` with confirm; warns when the worktree is provisioned (`claude rm` won't reap it — offer the `git worktree remove` + `branch -D` commands) |
| `s` | `claude stop` with confirm |
| `R` | force refresh |
| `q` | quit |

## Gate answering mechanics (verified 2026-08-21, v2.1.238)

`tmux new-window -d 'claude attach <shortid>'` → wait → `capture-pane` renders the pending question (blocked sessions re-render it on attach) → show in an overlay → keypress `1–9` → `send-keys N Enter` → kill the hidden window → re-poll. Version-fragile by nature (keystroke injection into a TUI), so it lives in one isolated function; if capture shows no recognizable question, the overlay says so and offers Enter-to-pair instead. Requires a tmux server; outside tmux the peek degrades to transcript-tail read-only.

## Alerting

The native view only notifies while open, so `fleet` owns its own alerting when it is the open view: on any transition into BLOCKED or COMPLETE, write BEL (tmux `monitor-bell` flags the tab red via the existing alert styling). No transition history is persisted; a restart re-baselines silently.

## Degradation

- `claude agents --json` fails → keep last table, show "stale since HH:MM" banner.
- A lane's git call fails → that lane renders `?`, others unaffected.
- Sidecar file unparseable → treated as absent.
- Terminal too narrow (<80) → drop the context column, never wrap rows.

## Scope

**In:** everything above, plus pre-work Task 0 — `fleet-status` hardening (atomic `.tmp`+`mv` write, `--` terminator, `--session` missing-value guard, session-id path validation), `deck`'s `ch` guard (empty → sane default), and `claude/install.sh` wiring for both `~/.local/bin` symlinks (`fleet-status`, `fleet`).

**Out:** swapping the deck fleet pane to `fleet` (user's call after driving it); the `/e2e` skill's `fleet-status complete` call (plugin repo); any reaper for stale sidecar files.

## Testing

- Unit: state derivation (all five buckets incl. stale-sidecar and no-sidecar cases), sidecar TSV parsing (tabs in note already flattened by writer; malformed lines), lane-strip and row formatting at narrow widths.
- Live smoke: run against the real fleet read-only; dispatch one low-effort throwaway that blocks on AskUserQuestion, answer it entirely from `fleet`, confirm it lands COMPLETE after running `fleet-status complete`; `claude rm` it from `fleet`.
- Safety rails for all live verification: `env -u TMUX` for anything that could `switch-client`; never touch `interpret`/`dotfiles` sessions beyond creating/killing the hidden attach window; never interact with real stream rows.
