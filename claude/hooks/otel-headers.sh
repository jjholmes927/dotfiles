#!/bin/sh
key=$("$HOME/.local/bin/secret-get" honeycomb-agent-traces 2>/dev/null) || exit 1
printf '{"x-honeycomb-team": "%s", "x-honeycomb-dataset": "claude-code-metrics"}\n' "$key"
