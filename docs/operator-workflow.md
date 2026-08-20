# The operator workflow

How development runs day to day: parallel agent streams in isolated worktrees, one fleet inbox, one human gate per stream. This documents the whole system from the operating model down to each script, so it survives machine moves and memory loss. Written 2026-08-19; mechanics were live-verified on Claude Code v2.1.235 that day.

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

The day loop: `deck` → work the `s:blocked` queue with Space-peeks → `closure-sweep` → `new-agent` to start streams → attach only for deliberate deep work → `claude rm` + memory line to close. Concurrency cap: 3–4 streams (quota is the binding constraint; background sessions bill like interactive ones and inherit effort settings).

```
tmux "interpret"                                (deck builds this)
├── 0 fleet   claude agents --cwd $ENG_ROOT     ← live here: the inbox
├── 1 pair    claude attach <id>                ← the ONE deep-work session
└── 2 ops     bash · clone-status ┆ cheat pane  ← launch + reap
```

The tmux session has three windows, not one per stream:

| Window | Runs | Job |
|--------|------|-----|
| `fleet` | `claude agents --cwd $ENG_ROOT` | The inbox. Never closes — needs-input/completed notifications only fire while it is open. |
| `pair` | whatever you attach | The one session you steer live. Statusline renames/colours the tab. |
| `ops` | bash + cheat-sheet pane | `new-agent`, `clone-status`, `gmp-all`, `claude rm`, git surgery. |

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
     ▼                                                              │ merge
 s:blocked shows it whenever it waits on you                        ▼
                                              claude rm  →  worktree + branch reaped
```

## 2. Components and where they live

| Piece | Location | What it does |
|-------|----------|--------------|
| `deck [name]` | `bash/.profile.d/deck` | Creates-or-attaches the fleet/pair/ops tmux session. Fleet auto-runs the scoped agent view; ops shows `tmux/deck-cheatsheet.txt` in a 44-col pane. |
| `new-agent <lane> [branch] [--effort low] "<prompt>"` | `bash/.profile.d/new-agent` | Provision + dispatch: fetches the repo's default branch, bases new branches on **fresh origin/<default>** (existing local/origin branches used as-is), provisions via the repo's `bin/create_worktree` when present (else plain `git worktree add` under `.worktrees/`), then dispatches `claude --bg` from inside the worktree. **Branch is optional**: omit it and the worktree is created detached on `origin/<default>` (provisional branch instead when `bin/create_worktree` exists, since it requires one), with a note appended to the prompt telling the agent to name the branch `jjholmes927-<slug>[-TICKET]` per /e2e Stage 2 before its first commit. Effort defaults to `high`, never inherits the global setting; `--effort low` and `--effort=low` both parse. Cleans up its pre-created branch on failure. |
| `closure-sweep` | `bash/.profile.d/closure-sweep` | The aging detector with a human at the end: flags authored PRs that are CONFLICTING ≥1d, quiet ≥2d, or stale drafts ≥7d (repos from `CLOSURE_REPOS`), plus any blocked background stream. Run it every morning; every line gets a next action, a hand-off, or a park. |
| `clone-status` / `gmp-all` / `lane-sweep` | `bash/.profile.d/lanes` | Lane upkeep. `gmp-all`: clean lanes pull; a dirty/parked lane is swept — WIP moved onto its own branch in a worktree, root returned to the default branch. A live Claude session in a lane root always blocks its sweep (checked via `claude agents --json`). |
| Cheat sheet | `tmux/deck-cheatsheet.txt` | The command + fleet-key reference shown in the ops pane, and in a `prefix ?` popup from **any** window — the fleet window has no ops pane, so the popup is the only way to read the fleet keys without leaving the inbox. Hard-wrapped to 42 cols to fit the 44-col ops pane; keep it that way. The ops pane `cat`s the file once at pane creation, so an already-running deck shows the old text until the pane is recreated. |
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

- **Answering a blocked background session works ONLY from the agent-view peek panel** (Space; numbered questions answer with a keypress). Every programmatic path dead-ends: SendMessage reports success while held or lands unsubmitted in the input box; `claude -p --resume` is refused for live bg sessions; `--fork-session` answers a copy while the original stays blocked.
- **Scripts must poll `state` (`working`/`blocked`/`done`/`stopped`) + `waitingFor`, never `status`** — and read a session's final text from its JSONL transcript (`~/.claude/projects/<slug>/<sessionId>.jsonl`, last assistant row). `claude logs` is raw ANSI scrollback. A blocked session flushes no assistant row, so the pending question exists only on screen.
- **Background sessions inherit the launcher's effort** — a one-word answer cost $0.73 at xhigh. Always dispatch with `--effort` (new-agent does).
- **bg worktree isolation is lazy (before first edit)** and `.worktreeinclude` must never list `.env.local`: the env var beats `lib/worktree_offset.rb`'s path resolution, so a copied file pins the worktree to its parent lane's DB/ports. Env values are written fresh by provisioning.
- **Two id namespaces**: CLI short ids (for `attach/logs/stop/rm`) ≠ ListAgents refs. `claude kill` is an alias of `stop`. View-delete (Ctrl+X ×2) removes worktrees *including uncommitted changes*; `claude rm` refuses.
- **Agent teams stay OFF** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`) — named subagents launch as teammates that never return results, stalling /e2e.
- **Non-pinned idle background sessions stop after ~1h**; sessions survive sleep and terminal close, not reboot. Pin overnight work (Ctrl+T).
- **The fleet verbs are hidden top-level commands** (`claude attach|logs|stop|rm|respawn|daemon`) absent from `claude --help`.

## 5. New / second machine bootstrap

1. `git -C <dotfiles> pull`, then run `claude/install.sh` (idempotent, backs up anything it would overwrite) and, if codex is used on this machine, the codex installer. `claude update` to ≥ 2.1.235 (agent view, `--bg`, cross-session messaging).
2. Create the machine-local override — gitignored, sourced automatically:
   ```bash
   cat > ~/.profile.d/local <<'EOF'
   export ENG_ROOT="$HOME/code"
   export LANES="myproject otherproject"
   export CLOSURE_REPOS="me/myproject me/otherproject"
   EOF
   ```
3. `gh auth login` (closure-sweep and PR flows need it). Claude and codex auth are per-machine too.
4. Per repo, once: `git remote set-head origin -a` (default-branch resolution), and ignore worktree dirs globally rather than per-repo:
   ```bash
   git config --global core.excludesfile ~/.gitignore
   printf '.worktrees/
.claude/
' >> ~/.gitignore
   ```
5. Repos without `bin/create_worktree` are fine — `new-agent` falls back to plain `git worktree add` (no DB provisioning, which simpler projects don't need). Lane repos WITH provisioning also get the memory hook: `ln -s <dotfiles>/magicnotes/post_worktree_setup.local <lane>/bin/`.
6. If tmux is already running, `tmux source-file ~/.tmux.conf` picks up the extended-keys settings.
7. Expect two silent no-ops on a personal machine: the workflow-ledger hook exits quietly without the `honeycomb-agent-traces` keychain item, and Beam MCPs simply aren't configured. Agent memory is per-machine and per-project — nothing ports, nothing needs to.
8. Smoke test: `deck` (fleet tab title reads `claude agents`, cheat pane renders) → `new-agent <lane> test-smoke --effort low "reply OK and finish"` (and once without the branch arg, to check the detached path) → row appears, goes done → peek it → `claude rm` it and delete the test branch.
