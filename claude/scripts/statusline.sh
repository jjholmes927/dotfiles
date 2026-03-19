#!/bin/bash
# Status line styled to match PS1

# Colors (matching bash-colours)
RED='\033[01;31m'
GREEN='\033[01;32m'
CYAN='\033[01;36m'
YELLOW='\033[00;33m'
RESET='\033[00m'

# Custom colors for status line
LIGHT_BLUE='\033[38;5;159m'
DEEP_RED='\033[38;5;160m'

# Read JSON input from stdin
INPUT=$(cat)

# Get git branch (skip optional locks for speed)
git_branch() {
    git --no-optional-locks branch 2>/dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/\1/'
}

# Get abbreviated path (first 3 + last 2 dirs)
abbrev_path() {
    local path="$1"
    echo "$path" | sed "s#\(/[^/]\{1,\}/[^/]\{1,\}/[^/]\{1,\}/\).*\(/[^/]\{1,\}/[^/]\{1,\}\)/\{0,1\}#\1_\2#g"
}

# Get current time
TIME=$(date +%T)

# Get username
USER=$(whoami)

# Get path from JSON input (fallback to pwd)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
if [[ -z "$CWD" ]]; then
    CWD=$(pwd)
fi
LOCATION=$(abbrev_path "$CWD")

# Get git branch
BRANCH=$(git_branch)

# Get dev server port from project tmp/dev_port (written by bin/dev)
dev_port() {
    local project_dir=$(echo "$INPUT" | jq -r '.workspace.project_dir // empty')
    if [[ -z "$project_dir" ]]; then
        project_dir="$CWD"
    fi
    local port_file="$project_dir/tmp/dev_port"
    if [[ -f "$port_file" ]]; then
        local port=$(cat "$port_file" 2>/dev/null)
        # Verify the port is actually in use (quick check)
        if [[ -n "$port" ]] && (echo >/dev/tcp/localhost/"$port") 2>/dev/null; then
            echo "$port"
        fi
    fi
}

DEV_PORT=$(dev_port)

# Get context usage from JSON input
context_usage() {
    # Use total_input_tokens (cumulative) rather than current_usage which may be null
    local used_pct=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0')
    local total_input=$(echo "$INPUT" | jq -r '.context_window.total_input_tokens // 0')
    local context_size=$(echo "$INPUT" | jq -r '.context_window.context_window_size // 0')

    # Only display if we have valid data
    if [[ "$context_size" -gt 0 ]]; then
        # Format context size with k suffix
        local size_k=$(awk "BEGIN {printf \"%.0fk\", $context_size/1000}")

        # Format total input tokens with k suffix
        local input_k=$(awk "BEGIN {printf \"%.1fk\", $total_input/1000}")

        # Round percentage for display
        local pct_display=$(awk "BEGIN {printf \"%.0f\", $used_pct}")

        # Display format: current_tokens/context_size (used%) in deep red
        printf "%b%s/%s (%s%%)%b" "$DEEP_RED" "$input_k" "$size_k" "$pct_display" "$RESET"
    fi
}

CONTEXT=$(context_usage)

# Get model display name
MODEL=$(echo "$INPUT" | jq -r '.model.display_name // empty')

# Format port display
PORT_DISPLAY=""
if [[ -n "$DEV_PORT" ]]; then
    PORT_DISPLAY=$(printf "%b:%s%b" "$GREEN" "$DEV_PORT" "$RESET")
fi

# Output styled status line
if [[ -n "$PORT_DISPLAY" ]]; then
    printf "%b%s%b %b%s%b %b%s%b %b%s%b %s\n" "$RED" "$TIME" "$RESET" "$GREEN" "$USER" "$RESET" "$CYAN" "$LOCATION" "$RESET" "$YELLOW" "$BRANCH" "$RESET" "$PORT_DISPLAY"
else
    printf "%b%s%b %b%s%b %b%s%b %b%s%b\n" "$RED" "$TIME" "$RESET" "$GREEN" "$USER" "$RESET" "$CYAN" "$LOCATION" "$RESET" "$YELLOW" "$BRANCH" "$RESET"
fi

# Second line: model and context
if [[ -n "$MODEL" && -n "$CONTEXT" ]]; then
    printf "%b%s%b | %s\n" "$LIGHT_BLUE" "$MODEL" "$RESET" "$CONTEXT"
elif [[ -n "$MODEL" ]]; then
    printf "%b%s%b\n" "$LIGHT_BLUE" "$MODEL" "$RESET"
elif [[ -n "$CONTEXT" ]]; then
    printf "%s\n" "$CONTEXT"
fi
