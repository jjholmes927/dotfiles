# Fleet TUI — design

2026-08-21. Grew from `2026-08-21-fleet-tui-seed.md`; supersedes it. The integrated streams+lanes inbox that eventually replaces the native `claude agents` view in the deck window's fleet pane.

## Goal

One terminal surface for the whole day loop: lane health at a glance, streams sorted by attention, real end-states instead of the ambiguous `done`, and gate answering without leaving the inbox. Kills the last reason the ops pane needed width.

## Shape

- `bin/fleet` — one Python 3 stdlib file (curses), symlinked into `~/.local/bin` like `fleet-status`. No dependencies.
- `tests/fleet_test.py` — unit tests for the pure core (state derivation, sidecar parsing, row/strip formatting), run with `python3 -m unittest`.
- Adoption path: run `fleet` in any pane/window while it earns trust; the native view keeps the deck fleet pane. Cutover later is a one-line change in `deck()` and is OUT of this spec's scope.

## Screen layout (locked with user, iterated 2026-08-21 evening)

```
  1 BLOCKED · 2 WORKING · 1 COMPLETE · 1 AWAITING          ← counts banner, 2-second read

  LANES  mn1 ✓2  mn2 ✓1  mn3 DIRTY·1  mn4 ✓  mn5 ✓
         second-brain ✓1                                   ← dynamic repos, only while active
  ── BLOCKED ──────────────────────────
  ★ 7feaaa4d mn3/phone-hub-routing   12m
      verify run.services.list permission?
  ── WORKING ──────────────────────────
    092b2a4b mn2/check-alert         41m
      > Finding ElevenLabs callers                         ← live activity line, always shown
  ── COMPLETE ─────────────────────────
    ad68d9fc gather-feedback         2h
      INT-842 done, PR #9403                               ← sidecar note; PR # parsed from it
  ── AWAITING / STOPPED groups follow, same shape ──

  [space]peek [1-9]answer [p]star [r]rm [q]quit            ← key footer
```

Decisions from the workstyle interview (usage is a mix of glance / batch visits / watching, depending on the day):
- **Counts banner** is the first line — readable in two seconds from across the window.
- **Lanes strip** second: configured `$LANES` always (branch ✓/DIRTY, worktree count); other `$ENG_ROOT` repos appear only while they host a stream. Streams in `$ENG_ROOT` itself show untagged.
- **State groups**, attention-first: BLOCKED → WORKING → COMPLETE → AWAITING → STOPPED. Empty groups collapse.
- **Every row is two lines**: id · name · age, then a dim context line — BLOCKED: the waiting reason; WORKING: live activity; COMPLETE/AWAITING: the sidecar note. Any `PR #NNNN` parsed from the note (no GitHub calls) renders as a bold badge on the row's **first** line, after the age — not inside the context line.
- **Stars**: `p` toggles a star on a stream; starred rows sort first inside their group and render ★. Persisted one session id per line in `~/.claude/fleet-stars`; stale ids are harmless and ignored.

## State names (aligned with existing vocabulary — user decision)

No invented terms. CLI states pass through; the `done` split is named by `fleet-status`'s own verbs:

| Bucket | Rule |
|--------|------|
| WORKING | CLI `state == working` |
| BLOCKED | CLI `state == blocked` AND `status != "idle"` (plan gates, questions, permission prompts) |
| COMPLETE | CLI `done`/`stopped` + sidecar `complete`, or CLI `blocked` + `status == "idle"` + sidecar `complete` (a session answered from inside fleet parks as `blocked`/`idle`) |
| AWAITING | CLI `done` + sidecar `awaiting`, or `done` with no sidecar (silent stop reads as "may want attention", never "finished"); also CLI `blocked` + `status == "idle"` with an `awaiting` sidecar or none at all — an idle-blocked row never falls through to STOPPED |
| STOPPED | CLI `stopped`/`failed` without a `complete` sidecar |

Sidecars are consulted only for ended sessions; a stale sidecar from a previous turn never recolors a `working`/`blocked` row. A session answered from inside fleet parks at an interactive prompt and reports `blocked`/`idle` forever (verified 2026-08-21), while a genuine gate reports `blocked` with no `status` — which is why idle-blocked rows are treated as ended and fall through to the sidecar rule. Bucketing reads the raw CLI status, kept as `cli_status`, because the display context line is overwritten with the transcript tail before the model is built.

## Data loop

- Every 3s: `claude agents --json --all`, filtered to `cwd` under `$ENG_ROOT`; one directory read of `~/.claude/fleet-status/` (single-line TSV per file: `state<TAB>ISO-UTC<TAB>note`).
- Every ~15s (staler is fine): per-lane git subprocess calls — `branch --show-current`, `status --porcelain | head`, `worktree list` — same queries `clone-status` makes.
- All subprocess work off the UI thread is unnecessary: calls are fast and the poll tick is the frame; a slow call just delays one repaint.

## Keys

| Key | Action |
|-----|--------|
| `j`/`k`, arrows | move selection |
| `p` | star/unstar the selected stream |
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
