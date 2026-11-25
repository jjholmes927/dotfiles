#!/usr/bin/env bash
set -o pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
state="${CODER_SETUP_STATE:-$HOME/.local/state/coder-setup}"
mn1="$HOME/engineering/mn1"
secret_get="$repo/bin/secret-get"
export USER="${USER:-$(id -un)}"
. "$here/versions.env"
mkdir -p "$state"

say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }

set_status() {
  local file="$state/status"
  { grep -v "^$1 " "$file" 2>/dev/null; printf '%s\n' "$*"; } > "$file.tmp"
  mv "$file.tmp" "$file"
}

tighten_secrets() {
  if [ -d "$HOME/.config/secrets" ]; then
    chmod 700 "$HOME/.config/secrets"
    find "$HOME/.config/secrets" -type f -exec chmod 600 {} +
  fi
  [ -f "$HOME/.config/ldcli/config.yml" ] && chmod 600 "$HOME/.config/ldcli/config.yml"
  return 0
}

wait_for_docker() {
  for _ in $(seq 1 30); do
    docker info >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

docker_store() {
  local conf="${DOCKER_DAEMON_JSON:-/etc/docker/daemon.json}" merged
  command -v docker >/dev/null || return 0
  wait_for_docker || return 1
  [ "$(docker info --format '{{.Driver}}' 2>/dev/null)" = overlay2 ] && return 0
  merged=$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except FileNotFoundError:
    data = {}
data.setdefault("features", {})["containerd-snapshotter"] = False
print(json.dumps(data, indent=2))
' "$conf") || return 1
  sudo mkdir -p "$(dirname "$conf")" || return 1
  printf '%s\n' "$merged" | sudo tee "$conf" >/dev/null || return 1
  say "docker: moving images and containers onto /var/lib/docker"
  sudo systemctl restart docker && wait_for_docker
}

system_phase() {
  local cache="$HOME/.cache/apt-archives"
  local apt=(sudo DEBIAN_FRONTEND=noninteractive apt-get -o "Dir::Cache::archives=$cache" -o Dpkg::Use-Pty=0 -qq)
  tighten_secrets
  mkdir -p "$HOME/.cache"
  [ -O "$HOME/.cache" ] || sudo chown "$USER:" "$HOME/.cache" || return 1
  mkdir -p "$cache" && sudo mkdir -p "$cache/partial" || return 1
  say "apt update"
  "${apt[@]}" update || return 1
  say "apt install"
  "${apt[@]}" install -y --no-install-recommends $(grep -v '^[[:space:]]*$' "$here/apt-packages.txt") || return 1
  sudo locale-gen en_GB.UTF-8 >/dev/null || return 1
  docker_store || return 1
  if [ -f "$mn1/compose.yaml" ]; then
    wait_for_docker || return 1
    (cd "$mn1" && docker compose up -d) || return 1
  fi
}

results=()
skip_reason=""

skip() {
  skip_reason="$1"
  return 3
}

step() {
  local name="$1" rc
  shift
  say "== $name"
  skip_reason=""
  "$@"
  rc=$?
  case "$rc" in
    0) results+=("OK:$name") ;;
    3) results+=("SKIP:$skip_reason"); say "skipped: $skip_reason" ;;
    *) results+=("FAIL:$name"); say "failed: $name (exit $rc)" ;;
  esac
}

load_shell() {
  [ -f "$repo/bash/linux/exports" ] && . "$repo/bash/linux/exports"
  return 0
}

node_toolchain() {
  export NVM_DIR="$HOME/.nvm"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | PROFILE=/dev/null bash || return 1
  fi
  . "$NVM_DIR/nvm.sh" || return 1
  local node="$NVM_DIR/versions/node/v$NODE_VERSION/bin/node"
  if [ "$("$node" -v 2>/dev/null)" != "v$NODE_VERSION" ]; then
    rm -rf "$NVM_DIR/versions/node/v$NODE_VERSION"
    nvm install "$NODE_VERSION" || return 1
  fi
  nvm alias default "$NODE_VERSION" >/dev/null || return 1
  nvm use --silent "$NODE_VERSION" || return 1
  corepack enable || return 1
  corepack prepare "pnpm@$PNPM_VERSION" --activate || return 1
}

ruby_toolchain() {
  local rbenv="$HOME/.rbenv" ruby
  if [ ! -x "$rbenv/bin/rbenv" ]; then
    rm -rf "$rbenv.clone"
    git clone -q https://github.com/rbenv/rbenv.git "$rbenv.clone" || return 1
    mkdir -p "$rbenv"
    cp -a "$rbenv.clone/." "$rbenv/" && rm -rf "$rbenv.clone" || return 1
  fi
  if [ -d "$rbenv/plugins/ruby-build/.git" ]; then
    git -C "$rbenv/plugins/ruby-build" pull -q --ff-only || return 1
  else
    git clone -q https://github.com/rbenv/ruby-build.git "$rbenv/plugins/ruby-build" || return 1
  fi
  export PATH="$rbenv/bin:$PATH"
  eval "$(rbenv init - --no-rehash bash)"
  ruby="$rbenv/versions/$RUBY_VERSION/bin/ruby"
  if [ "$("$ruby" -e 'print RUBY_VERSION' 2>/dev/null)" != "$RUBY_VERSION" ]; then
    rm -rf "$rbenv/versions/$RUBY_VERSION"
    rbenv install "$RUBY_VERSION" || return 1
  fi
  rbenv global "$RUBY_VERSION"
}

go_toolchain() {
  [ "$("$HOME/.local/go/bin/go" env GOVERSION 2>/dev/null)" = "go$GO_VERSION" ] && return 0
  rm -rf "$HOME/.local/go"
  mkdir -p "$HOME/.local"
  curl -fsSL "https://go.dev/dl/go$GO_VERSION.linux-amd64.tar.gz" | tar -C "$HOME/.local" -xz
}

overmind_binary() {
  local bin="$HOME/.local/bin/overmind" url
  "$bin" --version 2>/dev/null | grep -q "$OVERMIND_VERSION" && return 0
  url="https://github.com/DarthSim/overmind/releases/download/v$OVERMIND_VERSION/overmind-v$OVERMIND_VERSION-linux-amd64.gz"
  mkdir -p "$HOME/.local/bin"
  curl -fsSL "$url" | gunzip > "$bin.tmp" && chmod +x "$bin.tmp" && mv "$bin.tmp" "$bin"
}

gcloud_cli() {
  local sdk="$HOME/.local/google-cloud-sdk"
  [ "$(cat "$sdk/VERSION" 2>/dev/null)" = "$GCLOUD_VERSION" ] && return 0
  rm -rf "$sdk" "$sdk.tmp"
  mkdir -p "$sdk.tmp" || return 1
  curl -fsSL "https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-$GCLOUD_VERSION-linux-x86_64.tar.gz" |
    tar -C "$sdk.tmp" -xz || return 1
  mv "$sdk.tmp/google-cloud-sdk" "$sdk" && rm -rf "$sdk.tmp"
}

claude_cli() {
  [ -x "$HOME/.local/bin/claude" ] && return 0
  curl -fsSL https://claude.ai/install.sh | bash
}

npm_globals() {
  local pkg
  for pkg in @openai/codex @launchdarkly/ldcli agent-browser; do
    npm ls -g --depth=0 "$pkg" >/dev/null 2>&1 || npm install -g "$pkg" || return 1
  done
  [ -f "$state/agent-browser-installed" ] && return 0
  agent-browser install && touch "$state/agent-browser-installed"
}

git_config() {
  git config --global --unset-all credential.https://github.com.helper 2>/dev/null
  git config --global --add credential.https://github.com.helper "" || return 1
  git config --global --add credential.https://github.com.helper "!$here/git-credential-coder" || return 1
  git config --global --unset-all url.https://github.com/.insteadOf 2>/dev/null
  git config --global --add url.https://github.com/.insteadOf git@github.com: || return 1
  git config --global --add url.https://github.com/.insteadOf ssh://git@github.com/ || return 1
  command -v delta >/dev/null && git config --global core.pager delta
  git config --global merge.conflictStyle zdiff3
}

links() {
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$repo/tmux/.tmux.conf" "$HOME/.tmux.conf" &&
    ln -sfn "$repo/tmux/.tmux.conf.local" "$HOME/.tmux.conf.local" &&
    ln -sfn "$here/gh" "$HOME/.local/bin/gh" &&
    ln -sfn "$here/prod-data-session" "$HOME/.local/bin/prod-data-session"
}

mcp_overrides() {
  local file="$HOME/.config/coder-setup/mcp-overrides.json" key
  mkdir -p "$(dirname "$file")"
  key=$("$secret_get" linear-api-key 2>/dev/null)
  (
    umask 077
    LINEAR_KEY="$key" python3 -c '
import json, os, sys
servers = {"sentry": {"type": "http", "url": "https://mcp.sentry.dev/mcp/beam-eu/magic-notes"}}
key = os.environ.get("LINEAR_KEY", "").strip()
if key:
    servers["linear-server"] = {"type": "http", "url": "https://mcp.linear.app/mcp",
                                "headers": {"Authorization": "Bearer " + key}}
json.dump(servers, open(sys.argv[1], "w"), indent=2)
' "$file"
  ) || return 1
  [ -n "$key" ] || skip linear-key
}

installers() {
  bash "$repo/bash/install.sh" && bash "$repo/claude/install.sh"
}

codex_installer() {
  [ -f "$HOME/.claude/plugins/installed_plugins.json" ] || skip claude-plugins || return
  bash "$repo/codex/install.sh"
}

repos() {
  if [ ! -d "$mn1/.git" ]; then
    git clone -q https://github.com/wearebeam/magicnotes.git "$mn1" || return 1
  fi
  git -C "$mn1" remote set-head origin -a >/dev/null
}

magicnotes_secrets() {
  local name value
  for name in development test; do
    value=$("$secret_get" "magicnotes-$name-key" 2>/dev/null) || skip magicnotes-secrets || return
    (umask 077; printf '%s' "$value" > "$mn1/config/credentials/$name.key") || return 1
  done
  value=$("$secret_get" avo-licence 2>/dev/null) || skip magicnotes-secrets || return
  bundle config set --global https://packager.dev/avo-hq/ "$value" >/dev/null
}

magicnotes_setup() {
  [ -f "$state/mn1-setup-done" ] && return 0
  [ -f "$mn1/config/credentials/development.key" ] || skip magicnotes-secrets || return
  wait_for_docker || return 1
  (cd "$mn1" && docker compose up -d && SKIP_SERVER_RESTART=1 bin/setup) || return 1
  touch "$state/mn1-setup-done"
}

kandev() {
  local conf="$HOME/.config/kandev-fleet.json"
  [ -f "$conf" ] || { mkdir -p "$(dirname "$conf")" && cp "$here/kandev-fleet.json" "$conf"; } || return 1
  "$secret_get" linear-api-key >/dev/null 2>&1 || skip linear-key || return
  codex login status >/dev/null 2>&1 || skip codex-login || return
  "$repo/kandev/install-linux.sh"
}

home_phase() {
  local log="$state/home-$(date -u +%Y%m%dT%H%M%SZ).log" failed=() skipped=() entry
  exec 9>"$state/home.lock"
  if ! flock -n 9; then
    say "another home run is active; leaving it"
    return 0
  fi
  exec >>"$log" 2>&1
  set_status home RUNNING "$log"
  ls -1t "$state"/home-*.log 2>/dev/null | tail -n +11 | while read -r old; do rm -f "$old"; done

  step shell load_shell
  step node node_toolchain
  step ruby ruby_toolchain
  step go go_toolchain
  step overmind overmind_binary
  step gcloud gcloud_cli
  step claude claude_cli
  step npm-globals npm_globals
  step git-config git_config
  step links links
  step mcp-overrides mcp_overrides
  step installers installers
  step codex-installer codex_installer
  step repos repos
  step magicnotes-secrets magicnotes_secrets
  step magicnotes-setup magicnotes_setup
  step kandev kandev

  for entry in "${results[@]}"; do
    case "$entry" in
      FAIL:*) failed+=("${entry#FAIL:}") ;;
      SKIP:*) [[ " ${skipped[*]} " == *" ${entry#SKIP:} "* ]] || skipped+=("${entry#SKIP:}") ;;
    esac
  done
  if [ "${#failed[@]}" -gt 0 ]; then
    set_status home FAIL "$log" "${failed[*]}"
  elif [ "${#skipped[@]}" -gt 0 ]; then
    set_status home SKIP "$log" "${skipped[*]}"
  else
    set_status home OK "$log"
  fi
  say "done: ${results[*]}"
}

case "${1:-}" in
  system) system_phase ;;
  home) home_phase ;;
  *) echo "usage: coder/setup.sh system|home" >&2; exit 2 ;;
esac
