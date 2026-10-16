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
refs=()
while read -r repo _ ref _; do
  [[ -z "$repo" || "$repo" == \#* ]] && continue
  seen=""
  for i in "${!repos[@]}"; do
    [[ "${repos[$i]}" == "$repo" ]] || continue
    seen=1
    if [[ "${refs[$i]}" != "${ref:-}" ]]; then
      printf '  ✗ %s: every line for a repo must pin the same ref\n' "$repo" >&2
      exit 1
    fi
  done
  [[ -n "$seen" ]] && continue
  repos+=("$repo")
  refs+=("${ref:-}")
done < "$MANIFEST"

for i in "${!repos[@]}"; do
  repo="${repos[$i]}"
  ref="${refs[$i]}"
  checkout="$CACHE_DIR/${repo/\//__}"
  if [[ ! -d "$checkout/.git" ]]; then
    mkdir -p "$CACHE_DIR"
    git clone --quiet --depth 1 "https://github.com/$repo.git" "$checkout"
  fi
  if [[ -n "$ref" ]]; then
    if git -C "$checkout" fetch --quiet --depth 1 origin "$ref" && git -C "$checkout" checkout --quiet --detach FETCH_HEAD; then
      printf '  ✓ %s @ %s (pinned %s)\n' "$repo" "$(git -C "$checkout" rev-parse --short HEAD)" "$ref"
    else
      printf '  ⚠ %s: could not check out %s, keeping current checkout\n' "$repo" "$ref"
    fi
  else
    git -C "$checkout" pull --ff-only --quiet || printf '  ⚠ %s: pull failed, keeping current checkout\n' "$repo"
    printf '  ✓ %s @ %s\n' "$repo" "$(git -C "$checkout" rev-parse --short HEAD)"
  fi
done

while read -r repo path _; do
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
