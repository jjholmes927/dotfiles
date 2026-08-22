# Fleet TUI — design

2026-08-21. Grew from `2026-08-21-fleet-tui-seed.md`; supersedes it. The integrated streams+lanes inbox that eventually replaces the native `claude agents` view in the deck window's fleet pane.

## Goal

One terminal surface for the whole day loop: lane health at a glance, streams sorted by attention, real end-states instead of the ambiguous `done`, and gate answering without leaving the inbox. Kills the last reason the ops pane needed width.

## Shape

- `bin/fleet` — one Python 3 stdlib file (curses), symlinked into `~/.local/bin` like `fleet-status`. No dependencies.
- `tests/fleet_test.py` — unit tests for the pure core (state derivation, sidecar parsing, row/strip formatting), run with `python3 -m unittest`.
- Adoption path: run `fleet` in any pane/window while it earns trust; the native view keeps the deck fleet pane. Cutover = `DECK_INBOX=fleet`, and is OUT of this spec's scope.

## Screen layout (locked with user, iterated 2026-08-21 evening)

```
  1 BLOCKED · 2 WORKING · 1 COMPLETE · 1 AWAITING          ← counts banner, 2-second read

  LANES  mn1 ✓2  mn2 ✓1  mn3 DIRTY·1  mn4 ✓  mn5 ✓
         second-brain ✓1                                   ← dynamic repos, only while active
  ── BLOCKED ──────────────────────────
  ★ 7feaaa4d mn3/phone-hub-routing   12m
      verify run.services.list permission?
  ── WORKING ──────────────────────────
  ● 092b2a4b mn2/check-alert         41m
      > Finding ElevenLabs callers                         ← live row: the transcript tail
  ── COMPLETE ─────────────────────────
  ● ad68d9fc gather-feedback         2h
      INT-842 done, PR #9403                               ← sidecar note; PR # parsed from it
  ── AWAITING / STOPPED groups follow, same shape ──

  [enter]actions [space]peek [n]new [j/k]move [q]quit
                                                           ← key footer, verbatim
```

Decisions from the workstyle interview (usage is a mix of glance / batch visits / watching, depending on the day):
- **Counts banner** is the first line — readable in two seconds from across the window.
- **Lanes strip** second: configured `$LANES` always (branch ✓/DIRTY, worktree count); other `$ENG_ROOT` repos appear only while they host a stream. Streams in `$ENG_ROOT` itself show untagged.
- **State groups**, attention-first: BLOCKED → WORKING → COMPLETE → AWAITING → STOPPED. Empty groups collapse.
- **Old settled rows fold** (display only): every STOPPED row, plus COMPLETE/AWAITING rows older than 48h by the same `startedAt` the age column reads, are hidden by default; their group header gains a dim ` · N hidden` and a fully folded group renders as just that header, with no rows and no spacers. BLOCKED/WORKING rows and starred rows never fold. Selection and scrolling skip the hidden rows — a selection that folds away moves to the nearest visible row — while the counts banner, the bell and bucketing keep seeing everything.
- **`S` shows them**: the footer gains ` [S]show N` with the live count while anything is hidden and reads ` [S]hide` while expanded; when nothing would fold there is no footer entry and `S` does nothing.
- **Every row is two lines**: id · name · age, then a dim context line (dropped below 80 cols) — live rows (BLOCKED/WORKING) show the transcript tail, falling back to the CLI activity string; settled rows (COMPLETE/AWAITING/STOPPED) show the sidecar note, falling back to that same tail. Any `PR #NNNN` parsed from the note (no GitHub calls) renders as a bold badge on the row's **first** line, after the age — not inside the context line.
- **Stars**: `p` toggles a star on a stream; starred rows sort first inside their group and render ★. Persisted one session id per line in `~/.claude/fleet-stars`; stale ids are harmless and ignored.

## State names (aligned with existing vocabulary — user decision)

No invented terms. CLI states pass through; the `done` split is named by `fleet-status`'s own verbs:

| Bucket | Rule |
|--------|------|
| WORKING | CLI `state == working` |
| BLOCKED | CLI `state == blocked` AND `status != "idle"` (plan gates, questions, permission prompts) |
| COMPLETE | CLI `done`/`stopped` + sidecar `complete`, or CLI `blocked` + `status == "idle"` + sidecar `complete` (a session answered from inside fleet parks as `blocked`/`idle`) |
| AWAITING | CLI `done` + sidecar `awaiting`, or `done` with no sidecar (silent stop reads as "may want attention", never "finished"); also CLI `blocked` + `status == "idle"` with an `awaiting` sidecar or none at all — an idle-blocked row never falls through to STOPPED |
| STOPPED | CLI `stopped` without a `complete` sidecar; CLI `failed` always (a crash never renders as finished) |

Sidecars are consulted only for ended sessions; a stale sidecar from a previous turn never recolors a `working`/`blocked` row. A session answered from inside fleet parks at an interactive prompt and reports `blocked`/`idle` forever (verified 2026-08-21), while a genuine gate reports `blocked` with no `status` — which is why idle-blocked rows are treated as ended and fall through to the sidecar rule. Bucketing reads the raw CLI `status`; the transcript tail rides alongside it in its own `context_text` field and drives only the display line, so the two never overwrite each other.

## Data loop

- Every 3s: `claude agents --json --all`, filtered to `cwd` under `$ENG_ROOT`; one directory read of `~/.claude/fleet-status/` (single-line TSV per file: `state<TAB>ISO-UTC<TAB>note`).
- Every ~15s (staler is fine): per-lane git subprocess calls — `branch --show-current`, `status --porcelain | head`, `worktree list` — same queries `clone-status` makes.
- All subprocess work off the UI thread is unnecessary: calls are fast and the poll tick is the frame; a slow call just delays one repaint.

## Keys

Every action lives in one dispatch table, reached either from the menu or from its own key on the selected row; the footer lists only the four keys the menu cannot teach, plus the `S` fold toggle while there is anything to fold.

| Key | Action |
|-----|--------|
| `j`/`k`, arrows | move selection |
| `Enter` | open the **action menu** on the selected row — a bordered overlay titled with the row, seven items in a fixed order: `1` pair in (falls back to attaching **in place** — `endwin`, foreground `claude attach`, repaint with `back from <id>` — whenever the pair window is missing, busy, fleet's own pane, or there is no tmux), `2` peek (`peek + answer` on a BLOCKED row), `3` mark complete, `4` mark awaiting, `5` star (`unstar` when starred), `6` stop, `7` remove. Digits `1`–`7` fire an item; `Enter` inside the menu fires item 1, so `Enter Enter` stays the pair hand-off; any other key closes it |
| `1` (menu) | hand the session to the pair window (send `claude attach <id>` to `:pair`, guarded like `pair()`, `C-u` first); when that window is unavailable — missing, busy, or the one fleet itself is running in — attach in place instead of refusing |
| `Space` | peek: BLOCKED → live question via hidden tmux attach + `capture-pane`, shown raw; other states → last assistant text from the session transcript (`~/.claude/projects/<slug>/<sessionId>.jsonl`), rendered as markdown in the overlay — `**bold**` bold, `` `code` `` cyan, fenced blocks dim and verbatim, `#`–`###` headers bold yellow, `-`/`*` bullets as `•`, `>` quotes dim behind `▏`, links keep the text and drop the url; markers are removed rather than shown, blank lines survive as paragraph spacing |
| `1`–`9` | while peeking a BLOCKED row: answer via `send-keys` into the hidden attach, then kill it and re-poll |
| `c` / `a` | mark the row complete/awaiting by hand: prompt for a one-line note on the message row (Esc cancels, nothing written; an empty line → `marked complete from fleet` / `marked awaiting from fleet`), then shell out to `fleet-status <verb> <note> --session <full session id>` — the sidecar keeps one writer — and re-model so the row moves in the same frame |
| `p` | star/unstar the selected stream |
| `n` | dispatch a new stream: lane prompt (first word validated as a dir under `$ENG_ROOT`, extra words pass through) then stream prompt, run via `new-agent` in a background process — outcome on the message line, one dispatch at a time, Esc cancels |
| `r` | `claude rm` with confirm; warns when the worktree is provisioned (`claude rm` won't reap it — offer the `git worktree remove` + `branch -D` commands) |
| `s` | `claude stop` with confirm |
| `S` | show/hide the folded rows — every STOPPED row and every COMPLETE/AWAITING row older than 48h, starred rows excepted; a no-op when nothing would fold |
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

- Run the suite: `python3 -m unittest tests.fleet_test` (from the dotfiles root).
- Unit: state derivation (all five buckets incl. stale-sidecar and no-sidecar cases), sidecar TSV parsing (tabs in note already flattened by writer; malformed lines), lane-strip and row formatting at narrow widths.
- Live smoke: run against the real fleet read-only; dispatch one low-effort throwaway that blocks on AskUserQuestion, answer it entirely from `fleet`, confirm it lands COMPLETE after running `fleet-status complete`; `claude rm` it from `fleet`.
- Safety rails for all live verification: `env -u TMUX` for anything that could `switch-client`; never touch `interpret`/`dotfiles` sessions beyond creating/killing the hidden attach window; never interact with real stream rows.
