#!/bin/bash
# Send bell to Claude Code's tmux pane to trigger window alert
if command -v tmux &>/dev/null && [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
  pane_tty=$(tmux display-message -p -t "$TMUX_PANE" '#{pane_tty}')
  if [ -n "$pane_tty" ]; then
    printf '\a' > "$pane_tty"
  fi
fi
