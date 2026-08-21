# The operator workflow

How development runs day to day: parallel agent streams in isolated worktrees, one fleet inbox, one human gate per stream. This documents the whole system from the operating model down to each script, so it survives machine moves and memory loss. Written 2026-08-19; mechanics were live-verified on Claude Code v2.1.235 that day. Revised 2026-08-21 for the merged `deck` window and `fleet-status`.

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

The tmux session has two windows, not one per stream — the inbox, its reference card and the shell you launch from all live side by side in `deck`:

| Pane / window | Runs | Job |
|--------------|------|-----|
| `deck` · fleet pane (left, everything the right column doesn't take) | `claude agents --cwd $ENG_ROOT --dangerously-skip-permissions` | The inbox. Never closes — needs-input/completed notifications only fire while this view is open. Same rule as when it was a window; it is now a pane. The flag applies to sessions dispatched from the view (`@lane <prompt>`), which otherwise land in auto mode and block on the first permission prompt — `new-agent`'s flag does not reach them. |
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
 s:blocked shows it whenever it waits on you                        ▼
                                merge  →  claude rm  →  git worktree remove + branch -D
```

`claude rm` reaps only the lazy worktree a background session made for itself; a worktree provisioned by `bin/create_worktree` (or by `new-agent`'s `git worktree add` fallback) has to be removed by hand.

## 2. Components and where they live

| Piece | Location | What it does |
|-------|----------|--------------|
| `deck [name]` | `bash/.profile.d/deck` | Creates-or-attaches the tmux session: one `deck` window (fleet pane left, cheat and ops panes in a 56-col right column, ops 14 rows deep and auto-running `clone-status`) plus an empty `pair` window. Sizes the session at creation with `-x`/`-y` — client geometry inside tmux, `tput` outside — because a detached `new-session` otherwise defaults to 80×24 and the splits come out unusable; nonsense or tiny values are clamped (width <120 → 200, height <35 → 60). Renders the sheet after both splits with `send-keys "clear; deck-cheat \| head -n $((paneheight-4))"`, clipping from the bottom (four lines held back for the shell prompt) so the command reference stays on screen. Re-sources `~/.tmux.conf` on every invocation, not just at creation. |
| `new-agent <lane> [branch] [--effort low] "<prompt>"` | `bash/.profile.d/new-agent` | Provision + dispatch: fetches the repo's default branch, bases new branches on **fresh origin/<default>** (existing local/origin branches used as-is), provisions via the repo's `bin/create_worktree` when present (else plain `git worktree add` under `.worktrees/`), then dispatches `claude --bg` from inside the worktree. The fleet-inbox name is `<lane>/<first 4 slug words>` (capped 30 chars) when no branch is given, else the branch minus its prefix — short enough to read in the inbox and to pass to `pair`. **Branch is optional**: omit it and the worktree is created detached on `origin/<default>` (provisional branch instead when `bin/create_worktree` exists, since it requires one), with a note appended to the prompt telling the agent to name the branch `jjholmes927-<slug>[-TICKET]` per /e2e Stage 2 before its first commit. Effort defaults to `high`, never inherits the global setting; `--effort low` and `--effort=low` both parse. Dispatches with `--permission-mode bypassPermissions` (the `klaude` behaviour — a background agent that hits a permission prompt just blocks, so auto mode defeats the point); `--safe` drops back to auto mode and `--perm=<mode>` sets anything else. Aliases do not expand in scripts, so the flag is passed explicitly rather than by calling `klaude`. Cleans up its pre-created branch on failure. |
| `pair [name-or-id]` | `bash/.profile.d/deck` | Attaches a session in the **pair** window instead of in place: resolves a name substring or short id via `claude agents --json`, sends `claude attach <id>` to `:pair`, switches there. No argument picks the single background session. Refuses when the pair window is already running something, and sends `C-u` first — otherwise a half-typed line sitting in that pane concatenates with the attach command. Bound to `prefix P` (command-prompt) so it works from the fleet pane, which is a TUI with no shell; that path uses `run-shell`, so `pair` prints its candidate table to stdout — tmux swallows stderr. |
| `fleet-status complete\|awaiting "<note>" [--session <id>] [--stop]` | `bin/fleet-status`, symlinked into `~/.local/bin` | The stream's own end-of-run signal, run by the agent as its last action. Writes one TSV line — `state<TAB>ISO-8601 UTC<TAB>note` — to `~/.claude/fleet-status/$CLAUDE_CODE_SESSION_ID`; last call wins, and tabs/newlines in the note are flattened to spaces so the file stays one line. `CLAUDE_CODE_SESSION_ID` is the variable agent shells actually set (legacy `CLAUDE_SESSION_ID` is honoured as a fallback, `--session` overrides both); `--stop` best-effort stops the session afterwards. The unit of completion is the **stream**, not the ticket or the PR — a ticket spans many streams and a PR can be ticketless — so Linear and GitHub stay authoritative and refs just ride along in the free-form note. `new-agent` appends a one-sentence instruction to every prompt it dispatches; having /e2e call it from its final stage is a pending change in the plugin repo. Sidecars are keyed by session uuid, so stale files are inert — no reaper needed. |
| `closure-sweep` | `bash/.profile.d/closure-sweep` | The aging detector with a human at the end: flags authored PRs that are CONFLICTING ≥1d, quiet ≥2d, or stale drafts ≥7d (repos from `CLOSURE_REPOS`), plus any blocked background stream. Run it every morning; every line gets a next action, a hand-off, or a park. |
| `clone-status` / `gmp-all` / `lane-sweep` | `bash/.profile.d/lanes` | Lane upkeep. `gmp-all`: clean lanes pull; a dirty/parked lane is swept — WIP moved onto its own branch in a worktree, root returned to the default branch. A live Claude session in a lane root always blocks its sweep (checked via `claude agents --json`). |
| Cheat sheet | `tmux/deck-cheatsheet.txt` + `tmux/deck-cheat` | The plain-text source and its ANSI colouriser (headers blue, commands green, destructive bits red, caveats amber). Both the cheat pane and the popup run `deck-cheat`, never `cat` — keep the `.txt` plain so it stays diffable and width-checkable. Hard-wrapped to 42 cols to sit inside the 56-col right column; keep it that way. The pane only ever shows as much of the sheet as fits, so the `prefix ?` popup — available from **any** window, `pair` included — is the only view of the whole thing. |
| Notification hook | `claude/hooks/tmux-alert.sh` + matchers in `claude/settings.json` | Rings the tmux tab red on `permission_prompt`, `idle_prompt`, `elicitation_dialog`, `agent_needs_input`, `agent_completed`. Falls back to a `terminalSequence` BEL when there is no pane tty (background/agent-view contexts). |
| Statusline sync | `claude/scripts/statusline.sh` | Renames/recolours the tmux tab for attached sessions. Bails out when `CLAUDE_JOB_DIR` is set so background sessions can't rename live windows. |
| magicnotes worktree hook | `magicnotes/post_worktree_setup.local` → symlinked into each lane's `bin/` | Sourced by `bin/create_worktree`: links the worktree's Claude project dir to the parent checkout's agent memory (full non-alphanumeric slug encoding; leaves a non-empty real memory dir untouched). |
| /e2e pipeline | `jjholmes927/jjholmes927-claude-skills` plugin (joel-workflow) | The ticket→PR pipeline streams run. Stage 2 is isolation-aware since 2.12.1: reuse a bg job's worktree → `bin/create_worktree` → generic skill. |
| tmux keys | `tmux/.tmux.conf` | `extended-keys on` + `xterm*:extkeys` so Shift+Enter works in agent view. Prefix2 `C-s` eats agent view's grouping key — use `C-s C-s`. |

## 3. Per-machine configuration

All helpers read two env vars, overridden in a gitignored `~/.profile.d/local`:

```bash
export ENG_ROOT="$HOME/code"          # default: ~/engineering
export LANES="myproject otherproject" # default: mn1 mn2 mn3 mn4 mn5
```

Default branches are resolved per repo from `origin/HEAD` (fallback `main`); run `git remote set-head origin -a` once in repos whose default is `master`.

## 4. Verified landmines (do not relearn these)

- **Answering a blocked background session: the agent-view peek panel (Space; numbered questions answer with a keypress) or any attached client — attaching re-renders the pending question** (verified 2.1.238, 2026-08-21). That makes a scripted path possible: `tmux new-window -d 'claude attach <id>'` → `capture-pane` to read the question → `send-keys 1 Enter` to answer → kill the window. Headless paths still dead-end: SendMessage reports success while held or lands unsubmitted in the input box; `claude -p --resume` is refused for live bg sessions (retested 2.1.238); `--fork-session` answers a copy while the original stays blocked.
- **Scripts must poll `state` (`working`/`blocked`/`done`/`stopped`) + `waitingFor`, never `status`** — and read a session's final text from its JSONL transcript (`~/.claude/projects/<slug>/<sessionId>.jsonl`, last assistant row). `claude logs` is raw ANSI scrollback. A blocked session flushes no assistant row, so the pending question exists only on screen.
- **Background sessions inherit the launcher's effort** — a one-word answer cost $0.73 at xhigh. Always dispatch with `--effort` (new-agent does).
- **bg worktree isolation is lazy (before first edit)** and `.worktreeinclude` must never list `.env.local`: the env var beats `lib/worktree_offset.rb`'s path resolution, so a copied file pins the worktree to its parent lane's DB/ports. Env values are written fresh by provisioning.
- **Two id namespaces**: CLI short ids (for `attach/logs/stop/rm`) ≠ ListAgents refs. The short id is literally the **first 8 characters of `sessionId`** — the full uuid and the session name are both rejected with `No job matching`, so any script must slice it (`pair` does). `claude kill` is an alias of `stop`. View-delete (Ctrl+X ×2) removes worktrees *including uncommitted changes*; `claude rm` refuses when there is uncommitted work.
- **`claude rm` does not reap a provisioned worktree** — it only removes the lazy isolation worktree a background session created for itself. Anything `bin/create_worktree` or `new-agent`'s `git worktree add` fallback laid down survives the rm and needs `git worktree remove <path>` + `git branch -D <branch>` by hand. Closing a stream is two steps, not one.
- **From a Claude agent shell, always run `env -u TMUX deck` / `env -u TMUX pair`** — the agent shell inherits `$TMUX` from the session the CLI was launched in, so `deck` takes its in-tmux branch and `switch-client` yanks the operator's client over to the deck session mid-keystroke. Happened once while building this; recovered by switching back.
- **The cheat pane renders the sheet once, at deck-time** (`send-keys`, clipped to the pane height), so edits to `deck-cheatsheet.txt` do not appear until the deck session is rebuilt. The `prefix ?` popup always reads the current file — check new sheet text there.
- **Agent teams stay OFF** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) — named subagents launch as teammates that never return results, stalling /e2e.
- **Non-pinned idle background sessions stop after ~1h**; sessions survive sleep and terminal close, not reboot. Pin overnight work (Ctrl+T).
- **The fleet verbs are hidden top-level commands** (`claude attach|logs|stop|rm|respawn|daemon`) absent from `claude --help`.

## 5. New / second machine bootstrap

1. `git -C <dotfiles> pull`, then run `claude/install.sh` (idempotent, backs up anything it would overwrite) and, if codex is used on this machine, the codex installer. `claude update` to ≥ 2.1.235 (agent view, `--bg`, cross-session messaging).
2. Put `fleet-status` on `PATH` so streams can record their end state: `mkdir -p ~/.local/bin && ln -sf <dotfiles>/bin/fleet-status ~/.local/bin/` (check `~/.local/bin` is actually on `PATH`).
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
9. Smoke test: `deck` (fleet pane runs the agent view, cheat pane renders, ops pane shows the lane table) → `new-agent <lane> test-smoke --effort low "reply OK and finish"` (and once without the branch arg, to check the detached path) → row appears, goes done → `cat ~/.claude/fleet-status/*` shows its line → peek it → `claude rm` it, then remove the worktree and delete the test branch.
