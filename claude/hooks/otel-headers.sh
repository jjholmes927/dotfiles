#!/bin/sh
key=$(security find-generic-password -s honeycomb-agent-traces -w 2>/dev/null) || exit 1
printf '{"x-honeycomb-team": "%s", "x-honeycomb-dataset": "claude-code-metrics"}\n' "$key"
