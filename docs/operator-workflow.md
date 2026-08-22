# The operator workflow

How development runs day to day: parallel agent streams in isolated worktrees, one fleet inbox, one human gate per stream. This documents the whole system from the operating model down to each script, so it survives machine moves and memory loss. Written 2026-08-19; mechanics were live-verified on Claude Code v2.1.235 that day. Revised 2026-08-21 for the merged `deck` window, `fleet-status`, and the `fleet` TUI.

Deep background lives in two artifacts (private, share from the page menu):
- **The Missing Control Plane** — the analysis that produced this design: https://claude.ai/code/artifact/47ee05f0-a679-4f27-bb67-6f7e17189bb2
- **The Operator's Day** — the flows, keystroke by keystroke: https://claude.ai/code/artifact/c9a87c0d-b768-41c7-a983-539105bde546

## 1. The operating model (high level)

Three nouns:

- **Lane** — a durable clone of a repo with a fixed identity: its own Postgres/ports/Redis block (magicnotes: `WORKTREE_OFFSET` in `.env.local`, lanes `mn1`–`mn5`), warm caches, and any physical singletons (mn1 owns the telephony tunnel + Twilio webhook). Lanes are hosts, not workplaces: their roots stay parked clean on the default branch.
- **Stream** — one unit of work (usually a ticket) running as a *background* Claude session inside a worktree under a lane. Streams are dispatched, run unattended, and ask for the human exactly once (the /e2e plan gate).
- **Fleet** — all streams, viewed and answered from one inbox: `claude agents`.

```
$ENG_ROOT/
├── mn1/                     lane · telephony singleton · root parked clean on main
│   └── .worktrees/
│       ├── jjholmes927-a-INT-100/   ← stream: bg claude, own DB/ports/env/memory
│       └── jjholmes927-b-INT-200/   ← stream: fully parallel with the one above
├── mn2/                     lane
│   └── .worktrees/…
└── mn3/ mn4/ mn5/           lanes

          every stream = one row in the fleet inbox
```

The day loop: `deck` → work the `s:blocked` queue with Space-peeks → `closure-sweep` → `new-agent` to start streams → attach only for deliberate deep work → `claude rm`, remove the worktree, memory line to close. Concurrency cap: 3–4 streams (quota is the binding constraint; background sessions bill like interactive ones and inherit effort settings).

```
tmux "interpret"                                        (deck builds this)
├── 1 deck  ┌───────────────────────────┬──────────────┐
│           │ fleet  all the rest       │ cheat        │ ← 56-col right column
│           │ claude agents             │ deck-cheat   │
│           │   --cwd $ENG_ROOT         ├──────────────┤
│           │ ← live here: the inbox    │ ops  56 × 14 │ ← bash · clone-status
│           └───────────────────────────┴──────────────┘
└── 2 pair  claude attach <id>                            ← the ONE deep-work session
```

That is the **wide** build (client ≥ 170 cols after the clamps); a narrower client — a laptop — gets the inbox full width with one 10-row shell strip under it and no cheat pane, and reads the sheet from the `prefix ?` popup instead.

The tmux session has two windows, not one per stream — the inbox, its reference card and the shell you launch from all live side by side in `deck`:

| Pane / window | Runs | Job |
|--------------|------|-----|
| `deck` · fleet pane (left, everything the right column doesn't take) | `claude agents --cwd $ENG_ROOT --dangerously-skip-permissions` | The inbox. Never closes — needs-input/completed notifications only fire while this view is open. Same rule as when it was a window; it is now a pane. `fleet-toggle` (or `prefix F`) swaps the pane to the `fleet` TUI and back so the two surfaces can be compared day to day; whichever one is open owns alerting — the native view's needs-input/completed notifications fire only while IT is open, and fleet's bell rings only while FLEET is open. The flag applies to sessions dispatched from the view (`@lane <prompt>`), which otherwise land in auto mode and block on the first permission prompt — `new-agent`'s flag does not reach them. |
| `deck` · cheat pane (right top, 56 cols) | `deck-cheat`, rendered once at deck-time | The command + fleet-key reference, clipped from the bottom to whatever the pane can hold. `prefix ?` pops up the full sheet from any window. |
| `deck` · ops pane (right bottom, 56 × 14) | bash, auto-runs `clone-status` | `new-agent`, `clone-status`, `gmp-all`, `claude rm`, git surgery. 14 rows is enough for a prompt and a short table; `prefix z` zooms it full-window for anything wide. |
| `pair` window | whatever you attach | The one session you steer live. Statusline renames/colours the tab. |

`deck` re-runs `tmux source-file ~/.tmux.conf` on **every** invocation, not just when it builds the session. On 2026-08-21 a dotfiles autosync pull landed after the tmux server had started, and `prefix ?` / `prefix P` stayed unbound in the running server until the config was re-sourced by hand.

A stream's life:

```
new-agent mn3 [branch] "/e2e INT-X"
     │  provision (env·DB·keys·memory)  →  dispatch claude --bg --effort high
     ▼
 [working] ──plan ready──▶ [blocked] ──bell · Space · press 1──▶ [working]
     │                        ▲                                     │ /e2e → /ship
     │   (attach with →,      └── every later question repeats ◀────┤
     │    detach with ← —                                           ▼
     │    session keeps running)                            [done] + PR #NNNN
     ▼                                                              │ fleet-status complete
 s:blocked shows it whenever it waits on you (idle-parked too — §4) ▼
                                merge  →  claude rm  →  git worktree remove + branch -D
```

`claude rm` reaps only the lazy worktree a background session made for itself; a worktree provisioned by `bin/create_worktree` (or by `new-agent`'s `git worktree add` fallback) has to be removed by hand.

## 2. Components and where they live

| Piece | Location | What it does |
|-------|----------|--------------|
| `deck [name]` | `bin/deck` | Creates-or-attaches the tmux session: one `deck` window (fleet pane left, cheat and ops panes in a 56-col right column, ops 14 rows deep and auto-running `clone-status`) plus an empty `pair` window. Sizes the session at creation with `-x`/`-y` — client geometry inside tmux, `tput` outside — because a detached `new-session` otherwise defaults to 80×24 and the splits come out unusable; nonsense or tiny values are clamped (width <120 → 200, height <35 → 60). The layout is picked from that same clamped width: ≥170 builds the wide deck above, anything narrower (a genuine 120–169 laptop client) builds a **full-width inbox over a single 10-row bottom shell strip** running `clone-status`, with no cheat pane — the `prefix ?` popup is the reference there, and a tiny probe that clamps to 200 still gets the wide build. Renders the sheet after both splits with `send-keys "clear; deck-cheat \| head -n $((paneheight-4))"`, clipping from the bottom (four lines held back for the shell prompt) so the command reference stays on screen. Re-sources `~/.tmux.conf` on every invocation, not just at creation. The inbox pane is built on whichever surface `DECK_INBOX` names (`fleet` → the `fleet` TUI, anything else or unset → the native `claude agents` view), so `export DECK_INBOX=fleet` in `~/.profile.d/local` is the permanent cutover switch while `prefix F` still live-swaps a running pane. |
| `new-agent <lane> [branch] [--effort low] "<prompt>"` | `bin/new-agent` | Provision + dispatch: fetches the repo's default branch, bases new branches on **fresh origin/<default>** (existing local/origin branches used as-is), provisions via the repo's `bin/create_worktree` when present (else plain `git worktree add` under `.worktrees/`), then dispatches `claude --bg` from inside the worktree. The fleet-inbox name is `<lane>/<first 4 slug words>` (capped 30 chars) when no branch is given, else the branch minus its prefix — short enough to read in the inbox and to pass to `pair`. **Branch is optional**: omit it and the worktree is created detached on `origin/<default>` (provisional branch instead when `bin/create_worktree` exists, since it requires one), with a note appended to the prompt telling the agent to name the branch `jjholmes927-<slug>[-TICKET]` per /e2e Stage 2 before its first commit. Effort defaults to `high`, never inherits the global setting; `--effort low` and `--effort=low` both parse. Dispatches with `--permission-mode bypassPermissions` (the `klaude` behaviour — a background agent that hits a permission prompt just blocks, so auto mode defeats the point); `--safe` drops back to auto mode and `--perm=<mode>` sets anything else. Aliases do not expand in scripts, so the flag is passed explicitly rather than by calling `klaude`. Cleans up its pre-created branch on failure. |
| `pair [name-or-id]` | `bin/pair` | Attaches a session in the **pair** window instead of in place: resolves a name substring or short id via `claude agents --json`, sends `claude attach <id>` to `:pair`, switches there. No argument picks the single background session. Refuses when the pair window is already running something, and sends `C-u` first — otherwise a half-typed line sitting in that pane concatenates with the attach command. Bound to `prefix P` as `command-prompt -p "pair:" "run-shell 'bash -lc \"pair \\\"%%\\\"\"'"` so it works from the inbox pane, which is a TUI with no shell; the inner `\"%%\"` keeps a multi-word prompt answer as one argument instead of letting the login shell word-split it, and the login shell is used for portability — the tmux server's PATH is inherited from whatever started the server and is not guaranteed to carry `~/.local/bin` on every machine. That path uses `run-shell`, so `pair` prints its candidate table to stdout — tmux swallows stderr. |
| `fleet` | `bin/fleet`, symlinked into `~/.local/bin` by `claude/install.sh` | The integrated streams+lanes inbox — one Python 3 stdlib file (curses), no dependencies. Top line is a **counts banner** (only non-empty buckets, `no streams` when there are none, plus `stale since HH:MM` when `claude agents --json --all` fails and the last table is held). Under it a **lanes strip**: configured `$LANES` always, other `$ENG_ROOT` repos only while they host a background stream, each cell `name ✓<worktrees>` / `name DIRTY·<n>` (bare `name ✓` / `name DIRTY` when the lane has no worktrees) / `name ?` when that lane's git calls fail. Rows are grouped attention-first — **BLOCKED → WORKING → COMPLETE → AWAITING → STOPPED** — empty groups collapse, starred rows sort first inside each group. **Old settled rows fold**: every STOPPED row and any COMPLETE/AWAITING row older than 48h (same `startedAt` the age column reads) is hidden by default, its group header gaining a dim ` · N hidden` (a fully folded group renders as just that header), starred rows and BLOCKED/WORKING rows never fold, `S` toggles the hidden rows in and out (footer gains `[S]show N` / `[S]hide`, and is a no-op when nothing would fold), and nothing is deleted — the counts banner, the bell and the buckets still see every row. Settled rows split on the `fleet-status` sidecar, and the fallback differs by CLI state: a `done` row is COMPLETE with a `complete` sidecar and AWAITING otherwise; a `stopped` row is COMPLETE only with a `complete` sidecar and STOPPED otherwise; a `failed` row is always STOPPED (a crash never renders as finished). A `blocked` row whose `status` is `idle` — what a session answered from any attach parks as — takes the `done` route instead of falling through to STOPPED. **Two lines per row**: id · name · age with a bold `PR #NNNN` badge (parsed from the sidecar note, no GitHub calls) on line 1, then a dim context line, dropped below 80 cols — live rows show the transcript tail, settled rows the sidecar note. Every row carries one leading column; on the selected row it holds a `▌` accent bar in that row's state colour down both lines and the name goes bold — no reverse-video band. Sessions re-poll every 3s, lanes every ~15s; a transition into BLOCKED or COMPLETE rings the bell. Keys: **`Enter` opens a bordered action menu** on the selected row — `1` pair in (hands the session to a free `pair` window as `pair` does, but when there is no pair window, it is busy, it *is* fleet's own pane, or there is no tmux at all, fleet steps aside and runs `claude attach` **in place** — the attach owns the terminal until you leave it, then fleet repaints with `back from <id>`) · `2` peek (`peek + answer` on a BLOCKED row) · `3` mark complete · `4` mark awaiting · `5` star (`unstar` when it is already starred) · `6` stop · `7` remove; digits fire an item, `Enter` inside the menu fires item 1, so `Enter Enter` is still the pair hand-off, and any other key closes it. Every item is also a direct key on the selected row, and the menu is what teaches them: `Space` peek — a BLOCKED row inside tmux gets the hidden-attach capture where `1`–`9` answers, and Enter hands off to `pair` when no numbered question is recognised; every other row gets a read-only transcript tail · `p` star (persisted one id per line in `~/.claude/fleet-stars`) · `c`/`a` **mark the row complete/awaiting by hand** — a one-line note prompt takes over the message row (Esc cancels with nothing written; an empty line falls back to `marked complete from fleet` / `marked awaiting from fleet`), then `fleet-status <verb> <note> --session <full session id>` writes the sidecar, so its format still has exactly one writer, and the row re-buckets in the same frame · `s` `claude stop` and `r` `claude rm`, both behind a `y/N` confirm, `r` following up with the exact `git worktree remove` + `branch -D` commands (real branch resolved from the worktree) when a provisioned worktree survived · `j`/`k` (or arrows) move · `n` **dispatch a new stream from inside fleet** — a lane prompt (first word must be a directory under `$ENG_ROOT`; extra words pass through to `new-agent`, so `mn3 --effort low` works) then a stream prompt, run via `new-agent` in the background so the UI never freezes, `dispatched <id> <name>` on the message line and the row appearing on the next sweep; Esc at either prompt cancels, one dispatch at a time · `R` force refresh including lanes · `q` quit. The footer stays short — `[enter]actions [space]peek [n]new [j/k]move [q]quit`. Runs in any pane or window; `deck` still builds its inbox pane on the native `claude agents` view, and `fleet-toggle` / `prefix F` swaps that pane between the two surfaces so they can be compared day to day — whichever one is open owns alerting, so the native view's needs-input/completed notifications fire only while IT is open and fleet's bell rings only while FLEET is open. |
| `fleet-toggle [fleet\|native]` | `bin/fleet-toggle` | Swaps the `deck` window's inbox pane — the top-left one, `pane_left` 0 with the smallest `pane_top`, which is the inbox in both the wide and the narrow layout (the narrow layout's bottom strip is leftmost too, and the status line sits at the top so the first row is `pane_top` 1, not 0) — between the native `claude agents` view and the `fleet` TUI, so the two can be run head to head across a day. Reads what is running from `pane_current_command` (`Python` → fleet, a shell → nothing, anything else → the native view), quits it (`q` for fleet, a **raw ESC byte** via `send-keys -H 1b` for the native view — the `Escape` key name goes through tmux's extended-key translation and does not reliably reach it), waits up to 3s × 2 tries for the pane to land in a shell, then launches the other surface. No argument picks whichever is not running (`fleet` from a bare shell); an explicit argument that matches what is already up is a no-op. If the old surface will not quit it says so and stops, rather than typing into a live TUI. Bound to `prefix F` as `run-shell 'bash -lc fleet-toggle'`: run-shell's own shell is POSIX `sh` with the tmux server's PATH, which is inherited from whatever launched the server and is not guaranteed to carry `~/.local/bin` on every machine, so the login shell is what reliably finds the script. Targets the session the key came from via `$TMUX_PANE`/`$TMUX`, not tmux's "current" session, which under `run-shell` resolves to whichever session is attached. |
| `fleet-status complete\|awaiting "<note>" [--session <id>] [--stop]` | `bin/fleet-status`, symlinked into `~/.local/bin` | The stream's own end-of-run signal, run by the agent as its last action. `fleet` is now its reader — the sidecar is what splits a CLI `done` or idle-`blocked` row into COMPLETE vs AWAITING and a `stopped` row into COMPLETE vs STOPPED, and the note is what the settled row's context line and PR badge come from. Writes one TSV line — `state<TAB>ISO-8601 UTC<TAB>note` — to `~/.claude/fleet-status/$CLAUDE_CODE_SESSION_ID`; last call wins, and tabs/newlines in the note are flattened to spaces so the file stays one line. `CLAUDE_CODE_SESSION_ID` is the variable agent shells actually set (legacy `CLAUDE_SESSION_ID` is honoured as a fallback, `--session` overrides both); `--stop` best-effort stops the session afterwards. The unit of completion is the **stream**, not the ticket or the PR — a ticket spans many streams and a PR can be ticketless — so Linear and GitHub stay authoritative and refs just ride along in the free-form note. `new-agent` appends a one-sentence instruction to every prompt it dispatches; having /e2e call it from its final stage is a pending change in the plugin repo. Sidecars are keyed by session uuid, so stale files are inert — no reaper needed. |
| `closure-sweep` | `bin/closure-sweep` | The aging detector with a human at the end: flags authored PRs that are CONFLICTING ≥1d, quiet ≥2d, or stale drafts ≥7d (repos from `CLOSURE_REPOS`), plus any blocked background stream. Run it every morning; every line gets a next action, a hand-off, or a park. |
| `clone-status` / `gmp-all` / `lane-sweep` | `bin/clone-status`, `bin/gmp-all`, `bin/lane-sweep` | Lane upkeep. `gmp-all`: clean lanes pull; a dirty/parked lane is swept — WIP moved onto its own branch in a worktree, root returned to the default branch. A live Claude session in a lane root always blocks its sweep (checked via `claude agents --json`). |
| Cheat sheet | `tmux/deck-cheatsheet.txt` + `tmux/deck-cheat` | The plain-text source and its ANSI colouriser (headers blue, commands green, destructive bits red, caveats amber). Both the cheat pane and the popup run `deck-cheat`, never `cat` — keep the `.txt` plain so it stays diffable and width-checkable. Hard-wrapped to 42 cols to sit inside the 56-col right column; keep it that way. The pane only ever shows as much of the sheet as fits, so the `prefix ?` popup — available from **any** window, `pair` included — is the only view of the whole thing. |
| Notification hook | `claude/hooks/tmux-alert.sh` + matchers in `claude/settings.json` | Rings the tmux tab red on `permission_prompt`, `idle_prompt`, `elicitation_dialog`, `agent_needs_input`, `agent_completed`. Falls back to a `terminalSequence` BEL when there is no pane tty (background/agent-view contexts). |
| Statusline sync | `claude/scripts/statusline.sh` | Renames/recolours the tmux tab for attached sessions. Bails out when `CLAUDE_JOB_DIR` is set so background sessions can't rename live windows. |
| magicnotes worktree hook | `magicnotes/post_worktree_setup.local` → symlinked into each lane's `bin/` | Sourced by `bin/create_worktree`: links the worktree's Claude project dir to the parent checkout's agent memory (full non-alphanumeric slug encoding; leaves a non-empty real memory dir untouched). |
| /e2e pipeline | `jjholmes927/jjholmes927-claude-skills` plugin (joel-workflow) | The ticket→PR pipeline streams run. Stage 2 is isolation-aware since 2.12.1: reuse a bg job's worktree → `bin/create_worktree` → generic skill. |
| tmux keys | `tmux/.tmux.conf` | `extended-keys on` + `xterm*:extkeys` so Shift+Enter works in agent view. Prefix2 `C-s` eats agent view's grouping key — use `C-s C-s`. |

## 3. Per-machine configuration

All helpers read these env vars, overridden in a gitignored `~/.profile.d/local`:

```bash
export ENG_ROOT="$HOME/code"          # default: ~/engineering
export LANES="myproject otherproject" # default: mn1 mn2 mn3 mn4 mn5
export DECK_INBOX=fleet               # deck's inbox pane: fleet TUI; unset/anything else = native claude agents
```

Default branches are resolved per repo from `origin/HEAD` (fallback `main`); run `git remote set-head origin -a` once in repos whose default is `master`.

Every helper is an **executable script in `bin/`**, symlinked into `~/.local/bin` by `claude/install.sh` — none of them is a shell function any more (converted 2026-08-22). Editing one takes effect on the next run, in every shell, pane and agent Bash tool at once: nothing needs re-sourcing and no new shell is needed, because the script is read fresh from disk each time. The env vars above are still shell state, so a change to `~/.profile.d/local` does still need a new shell. Each script is self-contained — the default-branch lookup and the live-session probe are duplicated rather than sourced from a shared lib, so a script never depends on anything but its own file and `PATH`.

## 4. Verified landmines (do not relearn these)

- **Answering a blocked background session: the agent-view peek panel (Space; numbered questions answer with a keypress) or any attached client — attaching re-renders the pending question** (verified 2.1.238, 2026-08-21). That makes a scripted path possible: `tmux new-window -d 'claude attach <id>'` → `capture-pane` to read the question → `send-keys 1 Enter` to answer → kill the window. Headless paths still dead-end: SendMessage reports success while held or lands unsubmitted in the input box; `claude -p --resume` is refused for live bg sessions (retested 2.1.238); `--fork-session` answers a copy while the original stays blocked.
- **Answering a blocked background session converts it into a prompt-parked one, permanently**: whether the answer comes from the agent-view peek panel, `fleet`'s hidden attach, or a live `claude attach`, the session lands back at an interactive prompt and reports `state == blocked` with `status == idle` from then on — after it finishes its work and after it writes its `fleet-status` line (verified 2026-08-21). A genuine gate reports `blocked` with no `status`. `fleet` buckets the idle-blocked rows by sidecar instead (COMPLETE / AWAITING); any script must do the same and never read `state == blocked` on its own as "waiting on a human".
- **Scripts must poll `state` (`working`/`blocked`/`done`/`stopped`) + `waitingFor`, never `status`** — and read a session's final text from its JSONL transcript (`~/.claude/projects/<slug>/<sessionId>.jsonl`, last assistant row). `claude logs` is raw ANSI scrollback. A blocked session flushes no assistant row, so the pending question exists only on screen.
- **Background sessions inherit the launcher's effort** — a one-word answer cost $0.73 at xhigh. Always dispatch with `--effort` (new-agent does).
- **bg worktree isolation is lazy (before first edit)** and `.worktreeinclude` must never list `.env.local`: the env var beats `lib/worktree_offset.rb`'s path resolution, so a copied file pins the worktree to its parent lane's DB/ports. Env values are written fresh by provisioning.
- **Two id namespaces**: CLI short ids (for `attach/logs/stop/rm`) ≠ ListAgents refs. The short id is literally the **first 8 characters of `sessionId`** — the full uuid and the session name are both rejected with `No job matching`, so any script must slice it (`pair` does). `claude kill` is an alias of `stop`. View-delete (Ctrl+X ×2) removes worktrees *including uncommitted changes*; `claude rm` refuses when there is uncommitted work.
- **`claude rm` does not reap a provisioned worktree** — it only removes the lazy isolation worktree a background session created for itself. Anything `bin/create_worktree` or `new-agent`'s `git worktree add` fallback laid down survives the rm and needs `git worktree remove <path>` + `git branch -D <branch>` by hand. Closing a stream is two steps, not one.
- **From a Claude agent shell, always run `env -u TMUX deck` / `env -u TMUX pair`** — the agent shell inherits `$TMUX` from the session the CLI was launched in, so `deck` takes its in-tmux branch and `switch-client` yanks the operator's client over to the deck session mid-keystroke. Happened once while building this; recovered by switching back.
- **Shell functions go stale in every shell that is already open** — it bit twice (a `deck` edit that only the editing shell saw; a `fleet-toggle` fix that `prefix F` kept missing because the tmux server's `run-shell` never had the function at all), which is why the helpers were converted to `bin/` scripts on 2026-08-22. A function also cannot be reached from a Claude agent's Bash tool or from tmux `run-shell`, both of which are non-interactive. If a helper ever moves back into `~/.profile.d`, all three failure modes come back together.
- **Comment lines below the heredoc closer in `~/.tmux.conf.local` run as shell commands** — oh-my-tmux probes the file with `cut -c3- ~/.tmux.conf.local | sh` (`.tmux.conf` line ~1323) to test for custom `#{var}` functions. The cut turns line 1 into `: << EOF`, so lines 2–411 are inert heredoc body and only the custom block below the `# EOF` closer at ~412 is executed as commands. The delimiter is unquoted though, so `$(…)` and backticks expand **everywhere** in the file, heredoc body included. This was harmless while the helpers were shell functions and became a **fork bomb** the moment they became scripts on `PATH`: the comment `# deck cheat sheet popup …` ran `deck cheat sheet popup …`, which built a session called `cheat`, re-sourced `~/.tmux.conf`, and re-triggered the probe (caught and fixed 2026-08-22, and it had stolen the attached client with `switch-client`). Never start a live-region comment with a word that is an executable on `PATH`, and keep backticks, semicolons, pipes and stray apostrophes out of them — one unbalanced apostrophe quotes away the whole rest of the file. Audit (silent + exit 0 when clean; the `/^[^[:space:]]/` guard skips oh-my-tmux's indented sample-function bodies, which are defined but never called):

  ```sh
  cut -c3- tmux/.tmux.conf.local | awk 'live && /^[^[:space:]]/ { print NR" "$1 } $0 == "EOF" { live = 1 }' | { PATH="$HOME/.local/bin:$PATH"; rc=0; while read -r n w; do p=$(command -v "$w" 2>/dev/null); case $p in /*) echo "line $n runs $p"; rc=1;; esac; done; exit $rc; }
  ```

  Pair it with `cut -c3- tmux/.tmux.conf.local | sh -n` for the quoting half. Both checks are `tests/shell_test.py::TmuxToolsSurvive` regressions now, so `python3 -m unittest tests.shell_test` catches either one.
- **The cheat pane renders the sheet once, at deck-time** (`send-keys`, clipped to the pane height), so edits to `deck-cheatsheet.txt` do not appear until the deck session is rebuilt. The `prefix ?` popup always reads the current file — check new sheet text there.
- **Agent teams stay OFF** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) — named subagents launch as teammates that never return results, stalling /e2e.
- **Non-pinned idle background sessions stop after ~1h**; sessions survive sleep and terminal close, not reboot. Pin overnight work (Ctrl+T).
- **The fleet verbs are hidden top-level commands** (`claude attach|logs|stop|rm|respawn|daemon`) absent from `claude --help`.

## 5. New / second machine bootstrap

1. `git -C <dotfiles> pull`, then run `claude/install.sh` (idempotent, backs up anything it would overwrite) and, if codex is used on this machine, the codex installer. `claude update` to ≥ 2.1.235 (agent view, `--bg`, cross-session messaging).
2. The same `claude/install.sh` run links the **ten fleet/deck tools** in `bin/` into `~/.local/bin` — `fleet`, `fleet-status`, `deck`, `pair`, `new-agent`, `clone-status`, `lane-sweep`, `gmp-all`, `closure-sweep`, `fleet-toggle` (the `claude-auto-resume` / `claude-tmux-resume` scripts in `bin/` are deliberately not linked) — creating the dir, `chmod +x`-ing each one, and backing up anything already there that points elsewhere. That single loop is the whole helper install: nothing lands in `~/.profile.d` any more, so `bash/install.sh` only has to cover shell settings. Never hand-link with `ln -sf`; it clobbers. Only check `~/.local/bin` is actually on `PATH`.
3. Create the machine-local override — gitignored, sourced automatically:
   ```bash
   cat > ~/.profile.d/local <<'EOF'
   export ENG_ROOT="$HOME/code"
   export LANES="myproject otherproject"
   export CLOSURE_REPOS="me/myproject me/otherproject"
   EOF
   ```
4. `gh auth login` (closure-sweep and PR flows need it). Claude and codex auth are per-machine too.
5. Per repo, once: `git remote set-head origin -a` (default-branch resolution), and ignore worktree dirs globally rather than per-repo:
   ```bash
   git config --global core.excludesfile ~/.gitignore
   printf '.worktrees/
.claude/
' >> ~/.gitignore
   ```
6. Repos without `bin/create_worktree` are fine — `new-agent` falls back to plain `git worktree add` (no DB provisioning, which simpler projects don't need). Lane repos WITH provisioning also get the memory hook: `ln -s <dotfiles>/magicnotes/post_worktree_setup.local <lane>/bin/`.
7. A tmux server that is already running picks up config changes from any `deck` call — it re-sources `~/.tmux.conf` every time. Outside deck, `tmux source-file ~/.tmux.conf` does the same by hand.
8. Expect two silent no-ops on a personal machine: the workflow-ledger hook exits quietly without the `honeycomb-agent-traces` keychain item, and Beam MCPs simply aren't configured. Agent memory is per-machine and per-project — nothing ports, nothing needs to.
9. Smoke test: `deck` (fleet pane runs the agent view, cheat pane renders on a wide client, ops pane or narrow bottom strip shows the lane table) → `new-agent <lane> test-smoke --effort low "reply OK and finish"` (and once without the branch arg, to check the detached path) → row appears, goes done → `cat ~/.claude/fleet-status/*` shows its line → peek it → `claude rm` it, then remove the worktree and delete the test branch.
