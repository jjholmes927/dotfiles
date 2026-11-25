# Coder workspace setup: design

2026-11-23. Joel's Beam Coder workspace `joel-holmes-AKA-the-night-dragon` (template `beam-dev`, https://coder.beamify.dev).

> **TL;DR** A `~/personalize` hook pulls this repo and runs `coder/setup.sh` on every workspace start. The workspace then matches the Mac: Claude and Codex with plugins, skills and MCPs; Kandev as a service with Linear watches off; and magicnotes runnable (Ruby 4.0.10, Node 24, Postgres and Redis in Docker), so agents can do anything reasonable Joel can. The Mac setup does not change.

## Why

| | |
|---|---|
| **Intent** | Trial remote development at Beam. Run longer agent experiments on a box that stays up, **alongside** the Mac. |
| **Success** | Joel connects (SSH, VS Code, Cursor) and works as on the Mac. Kandev on the box can take a magicnotes ticket through `/e2e`: worktree, tests, app, PR. |
| **Bar** | "It needs to be able to do anything reasonable I can do." |

## Goals, non-goals, anti-goals

| Kind | Item |
|---|---|
| ✅ Goal | A fresh workspace is fully set up by: install the `~/personalize` stub, add secrets, do the one-time logins |
| ✅ Goal | Every restart re-applies the system layer on its own. Re-runs are safe and quick when nothing changed |
| ✅ Goal | magicnotes `bin/setup`, the test suite (including system tests) and `bin/dev` work; Kandev worktrees work |
| ⏸ Non-goal | Replacing the Mac; Linear watches on the box (off by default) |
| ⏸ Non-goal | Cursor and OpenCode harnesses (later) |
| ⏸ Non-goal | The agent GitHub bot (`gh-agent`) on the box |
| ⏸ Non-goal | Changing the Coder template (owned by the platform team) |
| ❌ Anti-goal | Any change in Mac behaviour: every Mac installer and hook behaves identically on Darwin |
| ❌ Anti-goal | Kandev's unauthenticated API reachable beyond `127.0.0.1` |
| ❌ Anti-goal | Secrets in git, in logs or in command output |
| ❌ Anti-goal | Two Kandevs taking the same Linear ticket |

## Workspace facts (verified 2026-11-23)

| Fact | Detail |
|---|---|
| **Machine** | Ubuntu 26.04, amd64, 8 cores, 125 GB RAM, 196 GB disk |
| **Survives restart** | `/home/coder` and `/var/lib/docker` (same volume). Everything else resets |
| **Start hook** | Template's Setup script runs `~/personalize` if executable, on every start, **before login is allowed** |
| **Privileges** | `sudo` without password; `docker` group |
| **Services** | systemd is PID 1 and running. `journald` has failed, so service logs must go to files |
| **Docker** | 29.9.3, Compose v5.7.1, data on the persistent volume |
| **GitHub** | `gh` logged in as `jjholmes927` through Coder (`GH_TOKEN`), https git via Coder's askpass. Reaches `wearebeam/magicnotes` and `wearebeam/beam-claude-skills`; **cannot reach `jjholmes927/life-vault`** |
| **Git identity** | Set by Coder: Joel Holmes, `joel.h@beam.org` |
| **Auto-stop** | None set, so long runs survive |
| **Already present** | git, gh, jq, tmux, python3 3.14, curl, docker. Missing: node, ruby, claude, codex, kandev, delta, bat |
| **Coder dotfiles setting** | Empty. An earlier attempt cloned over SSH and failed (Coder's SSH key is not on GitHub) |

## Approaches

| Approach | Trade-off | Verdict |
|---|---|---|
| **A. `~/personalize` runs `coder/setup.sh` from this repo** | One tracked script, repo at `~/engineering/dotfiles` like the Mac, runs in order before login | ✅ **Picked by Joel** (also the platform team's convention) |
| B. Coder's built-in dotfiles setting | Runs in parallel with Setup's `apt-get`, so package installs can collide; repo lands in `~/.config/coderv2/dotfiles`, which the scripts don't expect | Rejected |
| C. Install by hand, no script | Fastest today; the system layer is lost on restart and a new workspace can't be rebuilt | Rejected |

## Decisions

| Decision | Whose |
|---|---|
| Approach A | Joel |
| Box runs **alongside** the Mac; Linear watches off | Joel |
| magicnotes must be fully runnable on the box | Joel |
| Tools install into home, so they survive restarts; `personalize` only rebuilds the system layer | My call, Joel agreed |
| Claude and Codex now; Cursor and OpenCode later | My call, Joel agreed |
| Secrets as files under `~/.config/secrets/`, read through one helper | My call, Joel agreed |
| Kandev reached from the Mac with `coder port-forward` on local port 38430 | My call, Joel agreed |
| ~~Copy the Mac's existing Linear, Honeycomb and LaunchDarkly credentials~~ superseded below | Joel, 2026-11-24 |
| Secrets stored as **Coder user secrets** (`coder secret create … --file`), written by Coder on every start | Joel, 2026-11-24 |
| Least privilege: new Linear key (Read + Write, Interpret team only), new LaunchDarkly **Reader** token, existing Honeycomb **ingest** key (send-only) | Joel, 2026-11-24 |
| MCPs on the box: Linear via the Interpret-only key as a header (no OAuth login); Honeycomb OAuth **read-only**; Sentry OAuth scoped to `beam-eu/magic-notes`; logins with `claude mcp login <name> --no-browser` | Joel, 2026-11-24 |
| Production recordings and BigQuery for one experiment: your own `gcloud auth login`, only inside `prod-data-session`, which keeps the login and data in a private `/tmp` folder and on exit revokes the login and deletes the folder and its Claude and Codex history. A read-only service account is the later, stricter option | Joel, 2026-11-25 |
| Everything below this line | My call unless marked |

## Design

### Entry point

**`coder/personalize`** (tracked) is copied to `~/personalize` once by a bootstrap one-liner. On each start it:

1. Clones `https://github.com/jjholmes927/dotfiles` to `~/engineering/dotfiles` if missing.
2. Fast-forwards it only when the checkout is clean and on `master`; otherwise leaves it alone and logs why.
3. Runs `coder/setup.sh`, logging to `~/.local/state/coder-setup/<timestamp>.log`.
4. **Always exits 0.** Login is blocked while it runs, so a failure must be logged and summarised, never hang or block the workspace.
5. **Keeps the before-login part short.** The template's script timeout is not visible to us. Essentials (apt, Docker services, Kandev) run first; slow, non-essential steps (browser libraries, plugin builds) are handed to a background one-shot systemd unit, and `personalize` returns. apt's download cache lives in home so the per-start reinstall reuses files instead of downloading again.

### Two layers

| Layer | Lives in | Runs | Contents |
|---|---|---|---|
| **System** | Outside home (resets) | Every start | apt packages, Kandev and observer systemd units, `docker compose up -d` for Postgres and Redis, Playwright's system libraries |
| **Home** | `/home/coder` (persists) | First run, then no-ops | nvm + Node 24.19.0 + pnpm, rbenv + ruby-build + Ruby 4.0.10, Claude, Codex, Kandev binary, Go, overmind, ldcli, dotfile links, repo clones |

Order matters. The system layer runs first, because Ruby and native gems in home link against apt libraries that are reinstalled on each start.

**apt list**: derived from magicnotes' Brewfile, `bin/setup`, CI and Ruby's build needs. At least: build tools, `libpq-dev`, `libyaml-dev`, `libffi-dev`, `libssl-dev`, `zlib1g-dev`, `libvips42`, `ffmpeg`, `lsof`, `git-delta`, `bat`, `ripgrep`, `unzip`. The builder finalises it.

### Secrets

| Item | Detail |
|---|---|
| **Helper** | `bin/secret-get <name>`: on Darwin, `security find-generic-password -s <name> -w` (today's behaviour); on Linux, reads `~/.config/secrets/<name>` (dir 700, files 600) |
| **Callers switched** | Only where `security` is called today: `claude/hooks/otel-headers.sh`, `claude/hooks/otel-workflow-ledger.sh`, `kandev/configure.py`. `gh-agent` is untouched (non-goal) |
| **Needed on the box** | `linear-api-key` (Kandev). `honeycomb-agent-traces` (telemetry; optional, hooks stay silent without it) |
| **magicnotes** | From the Mac's `mn1`: `config/credentials/development.key` and `test.key` (gitignored; **never `staging.key` or `production.key`**, which also sit in `mn1`); the Avo licence line from `~/.bundle/config` (`BUNDLE_HTTPS://PACKAGER__DEV/AVO___HQ/`, needed by `bundle install` for `avo-advanced`; Tim used the same three); the LaunchDarkly CLI login (`~/.config/ldcli/config.yml`). No `.env.local` exists on the Mac. No Bundler token: since magicnotes #11596 (2026-11-19) `aicoustics` installs from `wearebeam/aic-sdk-ruby` over git, which Coder's token reaches |
| **Transfer** | Over `coder ssh` from the Mac, never echoed. Approved by Joel 2026-11-23 |
| **GitHub for agents** | Kandev's service does not inherit the login shell's `GH_TOKEN` or askpass, and Coder's token expires. A git credential helper and a `gh` wrapper fetch a fresh token on demand with `coder external-auth access-token github` (verified working on the box). Fallback if a service can't call it: a fine-grained token in the secrets folder |
| ⚠️ **Risk** | Anyone with admin access to Beam's cluster can read the volume. Acceptable for a trial; revisit before wider use |

### Kandev

| Item | Detail |
|---|---|
| **Install** | Linux release tarball `kandev-linux-x64.tar.gz`, **pinned to the Mac's version (v0.100.0)** for parity, into home, linked into `~/.local/bin` |
| **Service** | systemd unit, rebuilt on every start because `/etc` resets. Logs to `~/.kandev/logs/`. Bound to `127.0.0.1`; `install.sh` keeps refusing anything else |
| **Observer** | Second systemd unit replacing the launchd agent (Linux branch in `kandev/install.sh`; Darwin branch unchanged) |
| **Config** | `~/.config/kandev-fleet.json` on the box from a Coder example, written **before** `install.sh` runs (it stops on first run otherwise): lane `mn1`; **every core watch listed with `"enabled": false`**. This uses the existing per-watch `enabled` field, so there is no code change. The Codex watches resolve a Codex profile, so `codex login` comes before `configure.py` |
| **Access** | From the Mac: `coder port-forward joel-holmes-AKA-the-night-dragon --tcp 38430:38429`, then `http://localhost:38430` |
| **Plugins** | ADHD theme and Brainstorm need Go and npm, both installed in home |

### Harnesses

| Item | Detail |
|---|---|
| **Claude** | Native installer to `~/.local/bin/claude`. `claude/install.sh` runs unchanged: links, MCP sync, `~/.local/bin` tools, upstream skills. Plugins install on the first interactive session |
| **Codex** | `npm i -g @openai/codex` under nvm, then `codex/install.sh` unchanged |
| **Hooks** | `tmux-alert.sh`, `adhd-colours.py`, `statusline.sh` and `confirm-github-posts.sh` checked on Linux; any BSD-only command gets a portable form that keeps Darwin output identical |
| **One-time logins (Joel)** | Claude `/login`; `codex login --device-auth`; MCP OAuth for Linear, Sentry and Honeycomb. Their redirect lands on `localhost` on the box, so the callback port is forwarded with `coder port-forward` during login |
| **Personal private repos** | Coder's GitHub app is installed only on `wearebeam`, so `life-vault` and `second-brain` are unreachable, and neither is cloned to the box: `life-vault` holds private notes. `good-code-review` needs only `life-vault/06-principles/good-code.md`, so that one file is copied to `~/.config/good-code/good-code.md` and `GOOD_CODE_CHECKLIST` points at it. No personal GitHub token, no full `gh auth login` (decided by Joel 2026-11-24). The copy goes stale when the checklist changes; a documented one-line command re-copies it |
| **Agent memory** | Not ported. Memory is per machine and per project by design (`docs/operator-workflow.md`) |
| **agent-browser** | Installed in home so `/verify` and `verify-ui` work headless |

### Shell, git, tmux

| Item | Detail |
|---|---|
| **bash** | Linux branch in `bash/install.sh`: link the portable `.profile.d` files (alias, colours, completion, history, otel); skip `bash-exports`, `kinde` (1Password) and the Mac `.bash_profile`; add a Linux exports file (nvm, rbenv, `~/.local/bin`, `LD_DEV_SERVER=true` as on the Mac) |
| **git** | Do not link `git/gitconfig` (Mac paths, personal email). Coder's identity stays. Add delta and `zdiff3` with `git config --global` when missing |
| **tmux** | Link `.tmux.conf` and `.tmux.conf.local`; the copy binding already skips when `pbcopy` is absent |

### magicnotes

| Item | Detail |
|---|---|
| **Checkout** | `wearebeam/magicnotes` to `~/engineering/mn1` over https; `git remote set-head origin -a` |
| **Services** | Repo's `compose.yaml` (Postgres 16.1, Redis 7.2), brought up by `docker compose up -d` on every start; data survives on the Docker volume |
| **Toolchain** | Ruby 4.0.10, Node 24.19.0, pnpm, ffmpeg, vips, overmind, ldcli. `bin/setup`'s Homebrew branch is skipped on Linux; apt covers those packages |
| **Browsers** | System tests use Selenium with headless Chrome, fetched by Selenium Manager into home; the docs tests use Playwright Chromium, also in home. Their system libraries go in the per-start apt layer |
| **DB client** | `postgresql-client` in apt, needed by worktree cleanup |
| **Worktree adapter** | `magicnotes/kandev_worktree_setup.sh`: make `sed -i` work on both GNU and BSD sed. Darwin behaviour unchanged |

### Verification

| Check | Evidence |
|---|---|
| **Idempotent** | A second `setup.sh` run changes nothing and finishes quickly |
| **Restart** | `coder restart`, then: Kandev answers on `127.0.0.1:38429`, Postgres and Redis up, `claude --version`, `ruby -v`, `node -v` |
| **magicnotes** | `bin/rails db:prepare`; one model test and one system test pass; `bin/dev` serves on 3000 through a port forward |
| **Kandev** | A manually created task on `mn1` creates a worktree, runs the setup adapter and starts a Claude session |
| **Mac unchanged** | Repo tests (`tests/`, `workflow/`, `kandev/`) pass; `claude/install.sh` on the Mac prints only ✓ lines; `workflow/doctor.py` output unchanged |

## Left to the builder

- Final apt package list and Ruby build flags.
- How `kandev service install` behaves on Linux, or a hand-written unit if it assumes journald or launchd.
- File layout inside `coder/`.
- Install sources for overmind and ldcli on Linux.
