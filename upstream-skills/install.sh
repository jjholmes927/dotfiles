#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$SCRIPT_DIR/skills.txt"
CACHE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/upstream-skills"

HARNESS_HOMES=(
  "$HOME/.claude"
  "$HOME/.codex"
  "$HOME/.cursor"
  "$HOME/.config/opencode"
)


repos=()
while read -r repo _; do
  [[ -z "$repo" || "$repo" == \#* ]] && continue
  [[ " ${repos[*]-} " == *" $repo "* ]] || repos+=("$repo")
done < "$MANIFEST"

for repo in "${repos[@]}"; do
  checkout="$CACHE_DIR/${repo/\//__}"
  if [[ -d "$checkout/.git" ]]; then
    git -C "$checkout" pull --ff-only --quiet || printf '  ⚠ %s: pull failed, keeping current checkout\n' "$repo"
  else
    mkdir -p "$CACHE_DIR"
    git clone --quiet --depth 1 "https://github.com/$repo.git" "$checkout"
  fi
  printf '  ✓ %s @ %s\n' "$repo" "$(git -C "$checkout" rev-parse --short HEAD)"
done

while read -r repo path; do
  [[ -z "$repo" || "$repo" == \#* ]] && continue
  src="$CACHE_DIR/${repo/\//__}/$path"
  name="$(basename "$path")"
  if [[ ! -f "$src/SKILL.md" ]]; then
    printf '  ⚠ %s/%s: no SKILL.md upstream, skipped\n' "$repo" "$path"
    continue
  fi
  for home in "${HARNESS_HOMES[@]}"; do
    [[ -d "$home" ]] || continue
    dest="$home/skills/$name"
    mkdir -p "$home/skills"
    if [[ -L "$dest" && "$(readlink "$dest")" == "$src" ]]; then
      printf '  ✓ %s\n' "$dest"
    elif [[ -e "$dest" || -L "$dest" ]]; then
      printf '  ⚠ %s exists and is not this upstream skill, left alone\n' "$dest"
    else
      ln -s "$src" "$dest"
      printf '  → %s -> %s\n' "$dest" "$src"
    fi
  done
done < "$MANIFEST"
