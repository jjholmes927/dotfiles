# Deck Window Merge + fleet-status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the deck's fleet/ops/cheat windows into one two-pane-column tmux window, and add a `fleet-status` sidecar command that records each background stream's end-state (complete vs awaiting).

**Architecture:** All changes are shell: one new executable (`bin/fleet-status`) writing one-line TSV sidecar files keyed by session id, one function rewrite (`deck()` builds 2 windows instead of 3 and re-sources tmux config), one prompt-note addition (`new-agent`), plus doc/cheatsheet updates. No test framework exists in this repo — every task carries exact verify commands with expected output, run against throwaway resources (a `decktest` tmux session, a low-effort background session) so the live `interpret` session and real streams are never touched.

**Tech Stack:** bash, tmux ≥3.2, Claude Code CLI ≥2.1.235.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-21-deck-merge-and-fleet-status-design.md`.
- `tmux/deck-cheatsheet.txt` stays hard-wrapped ≤42 columns (ops/cheat pane is 46 cols wide minus borders).
- No code comments in shell changes except where the surrounding file already has them (repo rule; cheat-popup comments in `.tmux.conf.local` are pre-existing and stay).
- Never kill or restructure the live `interpret` tmux session; smoke tests use a separate `deck decktest` session.
- tmux uses base-index 1 for windows AND panes on this machine (gpakosz config) — never hardcode pane/window indexes; capture pane ids with `split-window -P -F '#{pane_id}'`.
- Commits: imperative mood, no Claude attribution.

---

### Task 1: `bin/fleet-status` executable + PATH symlink

**Files:**
- Create: `bin/fleet-status` (mode 755)
- Create (outside repo): symlink `~/.local/bin/fleet-status → <dotfiles>/bin/fleet-status`

**Interfaces:**
- Produces: `fleet-status complete|awaiting "<note>" [--session <id>] [--stop]` on PATH; sidecar file `~/.claude/fleet-status/<sessionId>` containing one line `state<TAB>ISO-8601-UTC<TAB>note`. Task 2's prompt note and the future wrapper TUI both rely on exactly this CLI and file format.

- [ ] **Step 1: Verify the command does not exist yet (failing state)**

Run: `command -v fleet-status`
Expected: no output, exit 1.

- [ ] **Step 2: Write the script**

Create `bin/fleet-status`:

```bash
#!/usr/bin/env bash
set -euo pipefail

usage='usage: fleet-status complete|awaiting "<note>" [--session <id>] [--stop]'

session="${CLAUDE_SESSION_ID:-}" stop=0
positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    --session)   session="$2"; shift 2 ;;
    --session=*) session="${1#*=}"; shift ;;
    --stop)      stop=1; shift ;;
    -*)          echo "unknown flag: $1" >&2; echo "$usage" >&2; exit 1 ;;
    *)           positional+=("$1"); shift ;;
  esac
done

if [ "${#positional[@]}" -ne 2 ]; then echo "$usage" >&2; exit 1; fi
state="${positional[0]}"
note="${positional[1]//$'\t'/ }"
case "$state" in complete|awaiting) ;; *) echo "bad state: $state" >&2; echo "$usage" >&2; exit 1 ;; esac
if [ -z "$session" ]; then
  echo 'no session id: $CLAUDE_SESSION_ID unset and no --session given' >&2
  exit 1
fi

dir="$HOME/.claude/fleet-status"
mkdir -p "$dir"
printf '%s\t%s\t%s\n' "$state" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$note" > "$dir/$session"
echo "fleet-status: $state recorded for ${session:0:8}"

if [ "$stop" = 1 ]; then
  claude stop "${session:0:8}" >/dev/null 2>&1 || true
  echo "fleet-status: stop requested for ${session:0:8}"
fi
```

- [ ] **Step 3: Make it executable and symlink onto PATH**

```bash
chmod +x bin/fleet-status
ln -sf "$PWD/bin/fleet-status" ~/.local/bin/fleet-status
```

- [ ] **Step 4: Verify behaviour**

Run each; check output exactly:

```bash
fleet-status complete                       # exit 1, usage line
fleet-status done "x" --session test-123    # exit 1, "bad state: done"
env -u CLAUDE_SESSION_ID fleet-status complete "x"   # exit 1, "no session id" message
fleet-status complete $'has\ttab' --session test-123 # exit 0
cat ~/.claude/fleet-status/test-123
```

Expected final line: `complete<TAB><timestamp>Z<TAB>has tab` (tab in note replaced by space; exactly 3 TSV fields).

```bash
fleet-status awaiting "second write" --session test-123 && cat ~/.claude/fleet-status/test-123
```

Expected: single line starting `awaiting` — last call wins, no append.

- [ ] **Step 5: Verify `--stop` against a throwaway background session**

```bash
cd "$(mktemp -d)" && claude --bg --name fs-stop-test --effort low --permission-mode bypassPermissions "reply OK and finish" 2>&1 | head -1
```

Take the short id it prints, find the full sessionId via `claude agents --json --all`, then:

```bash
fleet-status complete "stop test" --session <full-sessionId> --stop
claude agents --json --all | python3 -c 'import json,sys; print([r["state"] for r in json.load(sys.stdin) if (r.get("sessionId") or "").startswith("<short-id>")])'
```

Expected: state is `stopped` (or `done` if it finished before the stop landed — both acceptable; the file write is the assertion, the stop is best-effort). Clean up: `claude rm <short-id>`, `rm ~/.claude/fleet-status/test-123 ~/.claude/fleet-status/<full-sessionId>`.

- [ ] **Step 6: Commit**

```bash
git add bin/fleet-status
git commit -m "add: fleet-status records a stream's end-state in a sidecar file"
```

---

### Task 2: `new-agent` appends the fleet-status fallback line

**Files:**
- Modify: `bash/.profile.d/new-agent` (function `new-agent`, after the branch-note append at the end, before the dispatch line)

**Interfaces:**
- Consumes: `fleet-status` CLI from Task 1 (name and arg shape quoted verbatim in the note).
- Produces: every dispatched prompt ends with the status note; `_new_agent_status_note` helper.

- [ ] **Step 1: Add the note helper and append it**

Add below `_new_agent_branch_note()`:

```bash
_new_agent_status_note() {
  cat <<'NOTE'

---
When your work is fully complete, or you are parked waiting on a human, record it
by running: fleet-status complete|awaiting "<one line, include ticket/PR refs>"
NOTE
}
```

In `new-agent()`, immediately after the existing block

```bash
  if [ -z "$branch" ]; then
    prompt="$prompt$(_new_agent_branch_note)"
  fi
```

add:

```bash
  prompt="$prompt$(_new_agent_status_note)"
```

- [ ] **Step 2: Verify with a throwaway dispatch**

```bash
source bash/.profile.d/new-agent
new-agent mn5 --effort low "reply OK and finish"
```

(Any idle lane works; adjust if mn5 is busy.) Then check the prompt the agent actually received: find the transcript `~/.claude/projects/*/<sessionId>.jsonl` for the new session and confirm the first user message ends with the fleet-status note. Expected: both the branch note AND the status note appear (branch was omitted).

Clean up: `claude rm <short-id>` and delete the provisional branch if `bin/create_worktree` made one.

- [ ] **Step 3: Commit**

```bash
git add bash/.profile.d/new-agent
git commit -m "add: new-agent tells streams to record fleet-status on completion"
```

---

### Task 3: `deck()` merged two-window layout + tmux re-source

**Files:**
- Modify: `bash/.profile.d/deck` (function `deck()` only; `_agent_pick` and `pair` untouched)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: tmux session with window `deck` (fleet pane left, cheat pane top-right, ops pane bottom-right 14 rows) and window `pair`. `pair()` keeps working because it targets `:pair` by name.

- [ ] **Step 1: Rewrite `deck()`**

Replace the whole `deck()` function with:

```bash
deck() {
  local name=${1:-interpret} root="${ENG_ROOT:-$HOME/engineering}" cheat fleet right ops
  cheat="$(dirname "$(readlink "$HOME/.tmux.conf" 2>/dev/null)")/deck-cheat"
  if ! tmux has-session -t "=$name" 2>/dev/null; then
    fleet=$(tmux new-session -d -s "$name" -c "$root" -n deck -P -F '#{pane_id}')
    tmux set-option -w -t "=$name:deck" automatic-rename off
    tmux send-keys -t "$fleet" "claude agents --cwd \"$root\" --dangerously-skip-permissions" C-m
    if [ -x "$cheat" ]; then
      right=$(tmux split-window -h -l 46 -t "$fleet" -c "$root" -P -F '#{pane_id}' \
        "bash -c 'h=\$(tmux display -p \"#{pane_height}\"); \"$cheat\" | head -n \$((h-1)); exec bash'")
    else
      right=$(tmux split-window -h -l 46 -t "$fleet" -c "$root" -P -F '#{pane_id}')
    fi
    ops=$(tmux split-window -v -l 14 -t "$right" -c "$root" -P -F '#{pane_id}')
    tmux send-keys -t "$ops" 'clone-status' C-m
    tmux select-pane -t "$fleet"
    tmux new-window -t "=$name" -n pair -c "$root"
    tmux select-window -t "=$name:deck"
  fi
  tmux source-file "$HOME/.tmux.conf" >/dev/null 2>&1 || true
  if [ -n "$TMUX" ]; then tmux switch-client -t "=$name"; else tmux attach -t "=$name"; fi
}
```

Notes for the implementer: the unconditional `tmux source-file` is the fix for the 2026-08-21 stale-config landmine (server outlives a dotfiles pull); it is a no-op cost when the config is fresh. `$cheat` expands at deck-time (existing behaviour); `\$(tmux display ...)` must expand inside the pane, hence the escaping. `head -n $((h-1))` clips the 43-line sheet from the bottom so the command reference stays visible on short panes; the trailing `exec bash` keeps the pane alive (same pattern as the old ops split).

- [ ] **Step 2: Verify with a scratch deck session (never touch `interpret`)**

```bash
source bash/.profile.d/deck   # also sources lanes helpers via profile in real shells; clone-status must exist: source bash/.profile.d/lanes too
deck decktest &
sleep 3
tmux list-windows -t decktest -F '#I #W'
tmux list-panes -t decktest:deck -F '#{pane_id} #{pane_width}x#{pane_height} #{pane_current_command}'
```

Expected: windows `1 deck` and `2 pair`; three panes in `deck` — one wide pane (claude agents running, ~width minus 47), one 46-wide top-right, one 46x14 bottom-right. Then:

```bash
tmux capture-pane -t decktest:deck.2 -p | head -3
```

(Adjust pane index to the cheat pane's id from the listing.) Expected: first line ` DECK CHEAT SHEET  ? = this  P = pair` — clipped from the bottom, not scrolled to the tail.

- [ ] **Step 3: Verify the re-source path**

```bash
tmux unbind-key '?' ; deck decktest >/dev/null 2>&1 &
sleep 1; tmux list-keys -T prefix '?' | head -1
```

Expected: the `display-popup` deck-cheat binding is back (re-source restored it).

- [ ] **Step 4: Clean up and commit**

```bash
tmux kill-session -t decktest
git add bash/.profile.d/deck
git commit -m "ref: deck merges fleet/ops/cheat into one window and re-sources tmux config"
```

---

### Task 4: Cheat sheet text

**Files:**
- Modify: `tmux/deck-cheatsheet.txt`

**Interfaces:**
- Consumes: `fleet-status` CLI shape from Task 1.

- [ ] **Step 1: Edit the sheet**

Change the `FLEET (window 0)` header line to `FLEET (left pane)`. After the `closure-sweep` line, insert:

```
 fleet-status complete|awaiting "<note>"
                   mark stream end-state
```

- [ ] **Step 2: Verify the 42-column rule**

Run: `awk 'length > 42 {print FILENAME": "NR" ("length")"; bad=1} END {exit bad}' tmux/deck-cheatsheet.txt`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tmux/deck-cheatsheet.txt
git commit -m "docs: cheat sheet covers merged deck window and fleet-status"
```

---

### Task 5: operator-workflow.md

**Files:**
- Modify: `docs/operator-workflow.md` (§1 tmux diagram + window table, §2 component table, §5 bootstrap)

**Interfaces:**
- Consumes: final behaviour from Tasks 1–4 (describe what shipped, not the spec).

- [ ] **Step 1: Update §1**

Replace the three-window diagram and table with the two-window layout (deck window: fleet pane / cheat pane / ops pane 14 rows; pair window unchanged), noting: notifications need the fleet pane open (same rule, now a pane), `prefix z` zooms the ops pane for wide output, `prefix ?` popup remains the full-sheet view on short panes, and `deck` re-sources `~/.tmux.conf` on every invocation (stale-config fix, dated 2026-08-21).

- [ ] **Step 2: Update §2 and §5**

§2: update the `deck` row; add a `fleet-status` row (`bin/fleet-status`, sidecar path, TSV format, `--stop`, stream-is-the-unit rationale, `/e2e` will call it from its final stage — plugin-repo change, pending). §5: add bootstrap step `ln -sf <dotfiles>/bin/fleet-status ~/.local/bin/` next to the existing per-machine steps, and note the cheat pane requires rebuilding the deck session to show new text (existing landmine, still true).

- [ ] **Step 3: Commit**

```bash
git add docs/operator-workflow.md
git commit -m "docs: operator workflow reflects merged deck window and fleet-status"
```

---

### Task 6: Live cutover

- [ ] **Step 1: Rebuild the real deck session at a moment the user confirms** — `tmux kill-session -t interpret` closes the fleet view (background streams keep running; notifications pause until the view reopens), then `deck`. Confirm with the user first; never do this while a stream is blocked on a gate.

- [ ] **Step 2: Smoke the day loop** — fleet pane shows rows, `Space` peek works at the narrower width, `prefix P` pairs a session into the pair window, `prefix ?` popup renders, ops pane runs `new-agent mn5 --effort low "run: fleet-status complete \"smoke\" then finish"` and the sidecar file appears. `claude rm` the smoke session.
