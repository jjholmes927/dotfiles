# Coder Workspace Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **TL;DR** Six repo tasks make the dotfiles run on Linux without changing the Mac: a secrets helper, portable scripts, a bash Linux branch, Kandev under systemd, fresh Coder GitHub credentials for services, and the `~/personalize` bootstrap. Three box tasks then run it on `joel-holmes-AKA-the-night-dragon`, add secrets and logins with Joel, and prove magicnotes, Kandev and a restart all work. No personal GitHub token and no `life-vault` clone: only its good-code checklist file is copied.

**Goal:** Make Joel's Beam Coder workspace a full copy of his Mac dev setup (harnesses, plugins, MCPs, Kandev, runnable magicnotes) that rebuilds itself on every start.

**Architecture:** `~/personalize` (a symlink to `coder/personalize`) runs on every start. It refreshes the repo, runs `coder/setup.sh system` (apt, locale, Docker services) before login, then starts `coder/setup.sh home` in the background (toolchains, harnesses, dotfile installers, repos, Kandev). Mac-run scripts branch on `uname -s`; Darwin paths stay byte-identical.

**Tech Stack:** bash, Python 3 stdlib, `unittest`, systemd, Docker Compose, Coder CLI v2.38.10.

**Spec:** `docs/superpowers/specs/2026-11-23-coder-workspace-design.md`

## Global Constraints

- **Mac unchanged:** every changed script keeps identical behaviour and output on Darwin.
- **Versions:** Ruby `4.0.10`, Node `24.19.0`, pnpm `12.6.0` (from magicnotes `packageManager`), Kandev `0.100.0`, Claude ACP adapter `0.70.0`; Postgres `16.1` and Redis `7.2` from magicnotes `compose.yaml`. nvm, Go and overmind: current stable at implementation time, pinned in `coder/versions.env`.
- **Paths:** dotfiles `~/engineering/dotfiles`; magicnotes `~/engineering/mn1`; secrets `~/.config/secrets/<name>` (dir `700`, files `600`); Coder agent env `~/.config/coder-setup/agent.env` (`600`); setup state and logs `~/.local/state/coder-setup/`.
- **Kandev** listens on `127.0.0.1:38429` only. On the box, every Linear watch has `"enabled": false`.
- **Secrets** never appear in git, logs, test output or command echo.
- **`~/personalize` always exits 0.**
- **No code comments** (Joel's global rule). Machine-required markers are allowed.
- **Tests:** Python `unittest`, shell tools tested through `tests/shell_test.py`'s `ShellToolCase` with PATH stubs. Every new test module gets a line in the `.github/workflows/tests.yml` matrix.
- **Linux test run** (before the branch is pushed): `tar -C ~/engineering/dotfiles -cf - . | coder ssh joel-holmes-AKA-the-night-dragon -- 'rm -rf /tmp/df && mkdir /tmp/df && tar -C /tmp/df -xf - && cd /tmp/df/<dir> && python3 -m unittest -v <module>'`
- **Git:** branch `jjholmes927-coder-workspace`; imperative commit messages; no Claude attribution.

## Review Focus

1. **Restart during the first home run** (Ruby half-built, npm half-installed): the next start must finish the job, not skip it because a directory exists. Pinned by `test_partial_ruby_dir_is_rebuilt` (Task 7, Steps 2 and 4).
2. **Dotfiles checkout dirty or on a branch at boot:** no pull, setup still runs. Pinned by `test_skips_pull_when_dirty` and `test_skips_pull_on_branch` (Task 6).
3. **GitHub or apt unreachable at boot:** `personalize` exits 0 fast and the next shell shows a warning. Pinned by `test_exit_zero_and_fail_status_when_clone_fails` (Task 6) and `test_banner_shows_failed_status` (Task 3).
4. **Coder agent token rotates on restart:** credentials read the agent env at call time, never a cached copy. Pinned by `test_agent_env_read_on_every_call` (Task 5).
5. **Secret file with loose permissions, or a crafted name:** refused, nothing printed. Pinned by `test_linux_loose_permissions_refused` and `test_name_with_path_rejected` (Task 1).

---

### Task 1: `secret-get` helper

**Files:**
- Create: `bin/secret-get`, `tests/secret_get_test.py`, `kandev/test_secret.py`
- Modify: `claude/hooks/otel-headers.sh:2`, `claude/hooks/otel-workflow-ledger.sh:21`, `kandev/configure.py:110-114,290-294`, `claude/install.sh:93` (tool list), `.github/workflows/tests.yml`

**Interfaces:**
- Produces: `secret-get <name>`: prints the secret to stdout and exits 0. Missing secret: no output, exit 1. Bad name or loose file mode: message on stderr, exit 2. On Darwin it runs `security find-generic-password -s <name> -w`; otherwise it reads `${SECRETS_DIR:-$HOME/.config/secrets}/<name>`. Linked to `~/.local/bin/secret-get` by `claude/install.sh`.
- Produces: `configure.keychain_secret(item: str) -> str` keeps its signature and now runs `[REPO/bin/secret-get, item]`.

- [ ] **Step 1: Record the Mac baseline**

Run: `python3 workflow/doctor.py > "$TMPDIR/doctor-before.txt"; claude/hooks/otel-headers.sh | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)))' > "$TMPDIR/otel-before.txt"`
Expected: both files written (needed by Task 9).

- [ ] **Step 2: Write the failing tests** in `tests/secret_get_test.py` (`class SecretGet(ShellToolCase)`, with stub `uname` printing `Darwin` or `Linux`):
  - `test_darwin_reads_keychain`: stub `security` outputs `abc\n`. Expect stdout `abc\n`, rc 0, and `security` argv `["find-generic-password", "-s", "linear-api-key", "-w"]`.
  - `test_linux_reads_file`: `~/.config/secrets/linear-api-key` holds `xyz\n` with mode `600`. Expect stdout `xyz\n`, rc 0, and no `security` call.
  - `test_linux_missing_is_silent_exit_1`: expect rc 1 and empty stdout.
  - `test_linux_loose_permissions_refused`: mode `644`. Expect rc 2, empty stdout, stderr containing `mode 600`.
  - `test_name_with_path_rejected`: name `../x`. Expect rc 2 and empty stdout.

  And in `kandev/test_secret.py`: `test_keychain_secret_uses_secret_get` patches `configure.subprocess.run`, then asserts argv `[str(configure.SECRET_GET), "linear-api-key"]` and that the stripped stdout is returned.

- [ ] **Step 3: Run them and see them fail**

Run: `cd tests && python3 -m unittest -v secret_get_test; cd ../kandev && python3 -m unittest -v test_secret`
Expected: FAIL (`missing executable: .../bin/secret-get`; `AttributeError: SECRET_GET`).

- [ ] **Step 4: Implement**
  - Write `bin/secret-get` in bash. Accept names matching `^[A-Za-z0-9._-]+$` only, and check the mode with `stat -c %a` (Linux branch only).
  - In `configure.py`, set `SECRET_GET = Path(__file__).resolve().parent.parent / "bin/secret-get"`. On Linux, the missing-key message becomes ``write it to ~/.config/secrets/{item} (mode 600)``; the Darwin text stays unchanged.
  - In both hooks, replace the `security …` call with `"$HOME/.local/bin/secret-get" honeycomb-agent-traces 2>/dev/null`.
  - Add `secret-get` to the `claude/install.sh` tool loop.

- [ ] **Step 5: Run the tests on the Mac and on Linux**

Run the Step 3 command, then the **Linux test run** for `tests secret_get_test`.
Expected: PASS on both.

- [ ] **Step 6: Commit** with message `feat: Add secret-get so secrets work off the Mac Keychain`

### Task 2: Portable worktree adapter and host name

**Files:**
- Modify: `magicnotes/kandev_worktree_setup.sh:28,42-45`, `bin/agent-host-name`, `.github/workflows/tests.yml`
- Create: `tests/portability_test.py`

**Interfaces:**
- Produces: `agent-host-name` prints `joel-coder` when `CODER_WORKSPACE_NAME` is set; the existing mapping is unchanged otherwise.

- [ ] **Step 1: Write the failing tests** in `tests/portability_test.py` (`ShellToolCase`):
  - `test_worktree_setup_rewrites_env_with_any_sed`: a temp git repo at `<root>/tasks/feat/repo` has a `bin/create_worktree` stub containing the text `WORKTREE_NAME` that writes `.env` with `PORT=3000`, `DEV_WEB_PORT=3000`, `VITE_PORT=3130`, `WSS_PORT=28080`, `REDIS_PORT=6379`, `REDIS_URL=redis://localhost:6379/1`, `SERVICE_URL=http://localhost:3000`, `WORKTREE_OFFSET=x`. A stub `lsof` exits 1. Run `bash magicnotes/kandev_worktree_setup.sh` in the repo. Expect rc 0 and `.env` values `WORKTREE_OFFSET=kandev-feat`, `PORT=3001`, `DEV_WEB_PORT=3001`, `VITE_PORT=3131`, `WSS_PORT=28081`, `REDIS_PORT=6380`, `REDIS_URL=redis://localhost:6380/1`, `SERVICE_URL=http://localhost:3001`. No `.env.kandev-bak` file and no stray file named `''` remain.
  - `test_host_name_on_coder`: env `CODER_WORKSPACE_NAME=x`. Expect stdout `joel-coder\n`.
  - `test_host_name_unchanged_off_coder`: stub `hostname` prints `Joel-Holmes-Product-Engineering`. Expect `joel-work-mbp\n`.

- [ ] **Step 2: Run them on Linux and see them fail**

Run: **Linux test run** for `tests portability_test`.
Expected: FAIL. The worktree test fails because GNU sed reads `''` as the script; `test_host_name_on_coder` prints `joel-personal-mbp`.

- [ ] **Step 3: Implement**
  - Replace both `sed -i ''` calls with `sed -i.kandev-bak … .env && rm -f .env.kandev-bak`.
  - Add the `CODER_WORKSPACE_NAME` check at the top of `agent-host-name`.

- [ ] **Step 4: Run on the Mac and on Linux**

Expected: PASS on both.

- [ ] **Step 5: Commit** with message `fix: Make the worktree adapter and host name work on Linux`

### Task 3: bash Linux branch

**Files:**
- Modify: `bash/install.sh`, `.github/workflows/tests.yml`
- Create: `bash/linux/exports`, `tests/bash_install_test.py`

**Interfaces:**
- Produces: on Linux, `~/.profile.d/{alias,bash-colours,bash-completion,bash-history,otel}` link to the repo, and `~/.profile.d/linux-exports` links to `bash/linux/exports`. `~/.bashrc` holds exactly one block between `# >>> dotfiles profile.d >>>` and `# <<< dotfiles profile.d <<<` that sources every `~/.profile.d/*`.
- Produces: `bash/linux/exports` sets up nvm (`$HOME/.nvm`), rbenv, PATH (`$HOME/.local/bin`, `$HOME/.local/go/bin`, `$HOME/.rbenv/bin` first), `LD_DEV_SERVER=true`, `GOOD_CODE_CHECKLIST=$HOME/.config/good-code/good-code.md` and `LANG`/`LC_ALL=en_GB.UTF-8`. In interactive shells it prints one line, `coder-setup: <status line>`, when `~/.local/state/coder-setup/status` contains `FAIL`, `RUNNING` or `SKIP`.

- [ ] **Step 1: Write the failing tests** (stub `uname`):
  - `test_linux_links_portable_files_only`: expect the six links above. Expect no `~/.profile.d/bash-exports`, no `~/.profile.d/kinde` and no `~/.bash_profile`.
  - `test_linux_bashrc_block_added_once`: run the installer twice. Expect `~/.bashrc` to contain the start marker exactly once and to keep its original content.
  - `test_darwin_unchanged`: expect `~/.bash_profile` and all seven `.profile.d` files linked, and `~/.bashrc` untouched.
  - `test_banner_shows_failed_status`: the status file holds `home FAIL /x.log`. Run `bash -ic 'true'` with `HOME` set to the temp home after a Linux install. Expect stdout to contain `coder-setup: home FAIL /x.log`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd tests && python3 -m unittest -v bash_install_test`
Expected: FAIL (Linux run links `.bash_profile`).

- [ ] **Step 3: Implement** a `uname -s` branch in `bash/install.sh` and the `bash/linux/exports` file.

- [ ] **Step 4: Run on the Mac and on Linux**

Expected: PASS on both.

- [ ] **Step 5: Commit** with message `feat: Install the portable bash profile on Linux`

### Task 4: Kandev under systemd on Linux

**Files:**
- Create: `kandev/install-linux.sh`, `kandev/systemd/kandev.service`, `kandev/systemd/kandev-observer.service`, `kandev/test_install_linux.py`
- Modify: `kandev/install.sh` (after `here=…`, add `[ "$(uname -s)" = Linux ] && exec "$here/install-linux.sh" "$@"`), `kandev/configure.py:96,102` (Linux install hint), `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: `~/.config/kandev-fleet.json` key `kandev_version` (required on Linux), and the Task 1 `secret-get` via `configure.py`.
- Produces: `install-linux.sh [--render-units <dir>]`. With the flag, it only writes the rendered units to `<dir>` and exits. Without it, it:
  1. installs Kandev when missing, from `https://github.com/kdlbs/kandev/releases/download/v<version>/kandev-linux-x64.tar.gz` with its `.sha256` checked, into `~/.local/share/kandev/<version>/`, linked as `~/.local/bin/kandev`;
  2. enforces the loopback `~/.kandev/config.yaml` exactly as `install.sh` does;
  3. warms the ACP cache;
  4. writes the units to `/etc/systemd/system/` with `sudo install -m 644`;
  5. runs `daemon-reload`, then `enable --now`; it restarts only when a unit changed or `KANDEV_RESTART=1`;
  6. waits for the API, runs `configure.py`, then installs the adhd-theme plugin when `go` exists.
- Unit placeholders: `@HOME@`, `@PATH@`, `@REPO@`. The Kandev unit has `User=coder`, `ExecStart=@HOME@/.local/bin/kandev --headless`, `EnvironmentFile=-@HOME@/.config/coder-setup/agent.env`, `Restart=always`, `StandardOutput=append:@HOME@/.kandev/logs/service.out` and `StandardError=append:@HOME@/.kandev/logs/service.err`. The observer unit runs `@REPO@/kandev/fleet-observer.sh` and logs to `observer.out`/`observer.err`.

- [ ] **Step 1: Write the failing tests** in `kandev/test_install_linux.py`:
  - `test_render_units_fills_placeholders`: run with `--render-units <tmp>` and env `HOME=/home/t`, `PATH=/a:/b`. Expect both files to exist, contain no `@`, and include `ExecStart=/home/t/.local/bin/kandev --headless`, `Environment=PATH=/a:/b` and `EnvironmentFile=-/home/t/.config/coder-setup/agent.env`.
  - `test_install_sh_dispatches_on_linux`: with stub `uname` → `Linux` and a stub `install-linux.sh` copied beside a copy of `install.sh`, running `install.sh --x` calls the stub with `--x`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd kandev && python3 -m unittest -v test_install_linux`
Expected: FAIL (`install-linux.sh` missing).

- [ ] **Step 3: Implement** `install-linux.sh` and the two unit templates. Inspect the tarball's layout with `tar -tzf` to find the binary path.

- [ ] **Step 4: Run on the Mac and on Linux**

Expected: PASS on both.

- [ ] **Step 5: Commit** with message `feat: Run Kandev as a systemd service on Linux`

### Task 5: GitHub credentials on the box

**Files:**
- Create: `coder/git-credential-coder`, `coder/gh`, `tests/coder_credentials_test.py`
- Modify: `.github/workflows/tests.yml`

**Interfaces:**
- Produces: a git credential helper `coder/git-credential-coder get|store|erase`. For `get`, it reads `protocol`/`host`/`path` from stdin:
  - host other than `github.com`: no output, exit 0;
  - `github.com`: `username=x-access-token` and the password from `coder external-auth access-token github`. When `CODER_AGENT_TOKEN` is unset, it sources `~/.config/coder-setup/agent.env` first, on every call.

  `store` and `erase` exit 0 silently.
- Produces: `coder/gh`, linked as `~/.local/bin/gh`. It sets `GH_TOKEN` from the same Coder token path, then runs the next `gh` on PATH after its own directory.

- [ ] **Step 1: Write the failing tests** (`ShellToolCase`, stub `coder` printing `$CODER_AGENT_TOKEN-tok`):
  - `test_beam_repo_uses_coder_token`: stdin `protocol=https\nhost=github.com\npath=wearebeam/magicnotes.git\n` with `agent.env` holding `CODER_AGENT_TOKEN=one`. Expect `password=one-tok` and `coder` argv `["external-auth", "access-token", "github"]`.
  - `test_other_host_is_silent`: host `gitlab.com`. Expect empty stdout and rc 0.
  - `test_agent_env_read_on_every_call`: call once, rewrite `agent.env` to `CODER_AGENT_TOKEN=two`, call again. Expect `one-tok` then `two-tok`.
  - `test_store_and_erase_are_noops`.
  - `test_gh_wrapper_sets_fresh_token`: a stub real `gh` in a later PATH directory writes `$GH_TOKEN` to the log. Expect `one-tok`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd tests && python3 -m unittest -v coder_credentials_test`
Expected: FAIL (missing files).

- [ ] **Step 3: Implement both scripts** in bash.

- [ ] **Step 4: Run on the Mac and on Linux**

Expected: PASS on both.

- [ ] **Step 5: Commit** with message `feat: Give box agents fresh GitHub credentials`

### Task 6: `personalize` and `setup.sh`

**Files:**
- Create: `coder/personalize`, `coder/setup.sh`, `coder/apt-packages.txt`, `coder/versions.env`, `coder/kandev-fleet.json`, `tests/coder_personalize_test.py`
- Modify: `README.md` (a "Coder workspace" section: the bootstrap command from Task 7, the checklist re-copy command from Task 8 Step 2, and a link to the spec), `docs/agent-setup.md` (one row for `coder/`), `.github/workflows/tests.yml`

**Interfaces:**
- Consumes: Tasks 1–5.
- `coder/personalize` env overrides, for tests: `DOTFILES_DIR` (default `~/engineering/dotfiles`), `DOTFILES_URL` (default `https://github.com/jjholmes927/dotfiles.git`), `CODER_SETUP_STATE` (default `~/.local/state/coder-setup`). It:
  1. writes `CODER_AGENT_URL`, `CODER_AGENT_TOKEN` and `CODER_AGENT_AUTH` (whichever are set) to `~/.config/coder-setup/agent.env`, mode 600;
  2. clones when the checkout is missing (timeout 60 s); fast-forwards only when on `master` with a clean status; otherwise logs `skip pull: dirty` or `skip pull: on <branch>`;
  3. runs `setup.sh system` in the foreground, then starts `setup.sh home` detached with `setsid nohup`;
  4. writes `system OK|FAIL <log>` to `$CODER_SETUP_STATE/status` (each phase replaces only its own line there), keeps the last 10 logs, and exits 0 on every path.
- `coder/setup.sh system`:
  - apt `update` and `install --no-install-recommends` of `apt-packages.txt`, with `Dir::Cache::archives=$HOME/.cache/apt-archives`;
  - `locale-gen en_GB.UTF-8`;
  - `docker compose up -d` in `~/engineering/mn1` when it exists.
- `coder/setup.sh home`:
  - Writes `home RUNNING <log>`. Each step runs through `step <name> <cmd…>`, which logs it and records `OK`, `FAIL` or `SKIP <reason>`. It ends with `home OK|FAIL|SKIP <log> <failed or skipped names>`.
  - **Toolchains, each checked by running the binary's version, never by a directory existing:** nvm, then Node and pnpm through corepack; rbenv, ruby-build (`git pull`) and Ruby; Go into `~/.local/go`; overmind into `~/.local/bin`.
  - **Claude:** the native installer, when `~/.local/bin/claude` is missing.
  - **npm globals:** `@openai/codex`, `@launchdarkly/ldcli`, `agent-browser`, then `agent-browser install` once.
  - **git config:** the credential helper for `https://github.com` with `useHttpPath true`, `core.pager delta`, `merge.conflictStyle zdiff3`.
  - **Links:** `~/.tmux.conf` and `~/.tmux.conf.local`; `coder/gh` as `~/.local/bin/gh`.
  - **Installers:** `bash/install.sh`, `claude/install.sh`, `codex/install.sh`.
  - **Repos:** clone magicnotes to `mn1` and run `git remote set-head origin -a`. `life-vault` and `second-brain` are never cloned on the box.
  - **magicnotes setup:** `docker compose up -d`, then `bin/setup`, once. It needs `development.key` (`SKIP` without it) and leaves the marker `$CODER_SETUP_STATE/mn1-setup-done`.
  - **Kandev:** copy `coder/kandev-fleet.json` to `~/.config/kandev-fleet.json` when missing, then run `kandev/install-linux.sh`. `SKIP linear-key` when `secret-get linear-api-key` fails; `SKIP codex-login` when `codex login status` fails.
  - **PATH:** sources `bash/linux/exports` before any step, so `configure.py` records the full PATH.
- `coder/kandev-fleet.json`: `workspace` `Default Workspace`, `workflow` `Development`, `executor` `worktree`, `kandev_version` `0.100.0`, `claude_acp_version` `0.70.0`, `claude_profile` `{auto_approve: true, model: "opus[1m]"}`, lanes `[{name: "mn1", path: "~/engineering/mn1"}]`. `linear` has `keychain_item: linear-api-key`, `team: INT`, `state: Todo`, `assigned: me`, `poll_seconds: 60`, `max_inflight: 1`, and the four core labels (`agent:implement`, `agent:investigate`, `agent:implement-codex`, `agent:investigate-codex`), each with `repository: mn1, enabled: false`.
- `coder/apt-packages.txt`: one package per line, covering build tools, `libpq-dev`, `postgresql-client`, `libyaml-dev`, `libffi-dev`, `libssl-dev`, `zlib1g-dev`, `libreadline-dev`, `libvips42`, `ffmpeg`, `lsof`, `git-delta`, `bat`, `ripgrep`, `unzip`, `locales`, and the Chrome runtime libraries Playwright lists for Ubuntu (`libnss3`, `libgbm1`, `libasound2t64`, `libatk-bridge2.0-0t64`, `libxkbcommon0`, `libxcomposite1`, `libxdamage1`, `libxrandr2`, `libpango-1.0-0`, `libcairo2`, `libcups2t64`).

- [ ] **Step 1: Write the failing tests** in `tests/coder_personalize_test.py` (`ShellToolCase`; the origin repo holds a stub `coder/setup.sh` that appends `$1` to `$STUB_LOG_DIR/setup.log`; tests poll up to 5 s for the detached `home` call):
  - `test_clones_when_missing_and_runs_both_phases`: expect a checkout at `DOTFILES_DIR`, `setup.log` lines `system` then `home`, rc 0 and status `system OK`.
  - `test_fast_forwards_clean_master`: push a commit to the origin. Expect local `HEAD` to equal `origin/master`.
  - `test_skips_pull_when_dirty`: an untracked file is in the checkout. Expect `HEAD` unchanged, the log to contain `skip pull: dirty`, and `setup.log` to contain `system`.
  - `test_skips_pull_on_branch`: on branch `x`. Expect `HEAD` unchanged and `skip pull: on x`.
  - `test_exit_zero_and_fail_status_when_clone_fails`: `DOTFILES_URL=/nonexistent`. Expect rc 0 and status starting `system FAIL`.
  - `test_agent_env_written_private`: env `CODER_AGENT_TOKEN=t`. Expect `agent.env` with mode `600` containing `CODER_AGENT_TOKEN=t`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd tests && python3 -m unittest -v coder_personalize_test`
Expected: FAIL (missing `coder/personalize`).

- [ ] **Step 3: Implement** `personalize`, then `setup.sh`, the data files and the docs.

- [ ] **Step 4: Run on the Mac and on Linux**, plus the full suite:

Run: `for m in tests/secret_get_test tests/portability_test tests/bash_install_test tests/coder_credentials_test tests/coder_personalize_test kandev/test_secret kandev/test_install_linux kandev/test_core_watches workflow/test_doctor; do (cd ${m%/*} && python3 -m unittest ${m#*/}) || echo "FAILED $m"; done`
Expected: no `FAILED` lines.

- [ ] **Step 5: Commit** with message `feat: Bootstrap the Coder workspace from ~/personalize`

### Task 7: First run on the box

**Files:** none (operational)

- [ ] **Step 1: Push the branch:** `git push -u origin jjholmes927-coder-workspace`

- [ ] **Step 2: Seed the partial-Ruby case** (Review Focus 1): `coder ssh joel-holmes-AKA-the-night-dragon -- 'mkdir -p ~/.rbenv/versions/4.0.10'`

- [ ] **Step 3: Bootstrap**

Run: `coder ssh joel-holmes-AKA-the-night-dragon -- 'git clone -b jjholmes927-coder-workspace https://github.com/jjholmes927/dotfiles.git ~/engineering/dotfiles && ln -sf ~/engineering/dotfiles/coder/personalize ~/personalize && ~/personalize'`
Expected: returns in under 3 minutes with rc 0, and `~/.local/state/coder-setup/status` shows `system OK`.

- [ ] **Step 4: Wait for the home phase**, polling `cat ~/.local/state/coder-setup/status` every 2 minutes. Ruby compiles on the first run.
Expected: `home SKIP … linear-key codex-login magicnotes-setup`, and no `FAIL`. **`test_partial_ruby_dir_is_rebuilt`:** `~/.rbenv/versions/4.0.10/bin/ruby -v` prints `ruby 4.0.10`.

- [ ] **Step 5: Check the tools:** `bash -lc 'node -v; pnpm -v; ruby -v; go version; claude --version; codex --version; overmind -v; ldcli --version; agent-browser --version; gh auth status; ls -l ~/.claude/CLAUDE.md'`
Expected: Node `v24.19.0`, pnpm `12.6.0`, Ruby `4.0.10`; every command resolves; `CLAUDE.md` is a link into the dotfiles.

### Task 8: Secrets and logins (with Joel)

**Files:** none (operational). Values are piped and never printed.

- [ ] **Step 1: Copy the Mac secrets:**

```bash
B=joel-holmes-AKA-the-night-dragon
security find-generic-password -s linear-api-key -w | coder ssh $B -- 'umask 077; mkdir -p ~/.config/secrets; cat > ~/.config/secrets/linear-api-key'
security find-generic-password -s honeycomb-agent-traces -w | coder ssh $B -- 'umask 077; cat > ~/.config/secrets/honeycomb-agent-traces'
coder ssh $B -- 'umask 077; cat > ~/engineering/mn1/config/credentials/development.key' < ~/engineering/mn3/config/credentials/development.key
coder ssh $B -- 'umask 077; mkdir -p ~/.config/ldcli; cat > ~/.config/ldcli/config.yml' < ~/.config/ldcli/config.yml
```

- [ ] **Step 2: Copy the good-code checklist** (the only `life-vault` file the box needs; re-run this whenever the checklist changes): `coder ssh joel-holmes-AKA-the-night-dragon -- 'mkdir -p ~/.config/good-code && cat > ~/.config/good-code/good-code.md' < ~/engineering/life-vault/06-principles/good-code.md`
Expected: `ls ~/.config/good-code/good-code.md` on the box lists the file; `/good-code-review` there reports the checklist path in its header line.

- [ ] **Step 3: Joel's logins** in `coder ssh joel-holmes-AKA-the-night-dragon`:
  - `claude`, then `/login`.
  - `codex login --device-auth`.
  - In `claude`, `/mcp`, then authenticate Linear, Sentry and Honeycomb. When the browser fails on `localhost:<port>`, run `coder port-forward joel-holmes-AKA-the-night-dragon --tcp <port>:<port>` on the Mac and retry.

- [ ] **Step 4: Rerun the home phase:** `coder ssh … -- '~/engineering/dotfiles/coder/setup.sh home'`
Expected: status `home OK`; `secret-get linear-api-key >/dev/null && echo ok` prints `ok`; `ls -l ~/.config/secrets` shows `-rw-------` on every file.

### Task 9: Prove it end to end

**Files:** none (operational)

- [ ] **Step 1: magicnotes.** In `~/engineering/mn1`, run `bin/rails db:prepare`, one model test and one system test, then `bin/dev`. On the Mac, run `coder port-forward … --tcp 3005:3000` and `curl -sI localhost:3005`.
Expected: both tests pass; curl returns `200` or `302`.

- [ ] **Step 2: Kandev UI and watches.** Run `coder port-forward … --tcp 38430:38429` and open `http://localhost:38430`. Run `curl -s 127.0.0.1:38429/api/v1/linear/watches/issue?workspace_id=<id>` on the box.
Expected: the UI loads; four watches, all `"enabled": false`.

- [ ] **Step 3: A Kandev task.** Create a manual task on lane `mn1` with the prompt `Run bin/rails test test/models/user_test.rb, then run git ls-remote origin HEAD, and report both results`.
Expected: a worktree is created, `kandev-worktree-setup: done` appears in the task log, the test passes, and `ls-remote` prints a hash (the credential helper works under the service).

- [ ] **Step 4: Restart.** Run `coder restart joel-holmes-AKA-the-night-dragon -y`, then wait for the agent.
Expected: login within 3 minutes; status `system OK` and then `home OK`; `systemctl is-active kandev kandev-observer` prints `active` twice; `docker compose ps` in `mn1` shows Postgres and Redis running; `ruby -v` prints `4.0.10` with no rebuild in the log.

- [ ] **Step 5: Mac unchanged.**
  - Re-run `claude/install.sh` and `bash/install.sh` on the Mac. Expect only `✓` lines, plus the new `secret-get` link.
  - Run `python3 workflow/doctor.py | diff "$TMPDIR/doctor-before.txt" -` and `claude/hooks/otel-headers.sh | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)))' | diff "$TMPDIR/otel-before.txt" -`. Expect no differences.

- [ ] **Step 6: Hand off** with `/ship` for the PR, which runs `writing-pr-descriptions`.
