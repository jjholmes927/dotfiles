# Coding-agent telemetry in Honeycomb (free)

Get every coding agent on your machine — Claude Code *and* Codex CLI — reporting cost, tokens, and exact skill/MCP/tool usage to one free Honeycomb board, split by machine and model.

Why bother: agents quietly skip skills and tools they should be using, or do sneaky workarounds. This makes it visible, and if you run a Claude-orchestrates / Codex-implements flow, you can watch the work split too.

## 0. Prereqs (~15 min total)

1. A free Honeycomb account — [honeycomb.io](https://www.honeycomb.io). Free tier is 20M events/month; one developer uses a fraction of that. Note your region: `ui.honeycomb.io` = US (`api.honeycomb.io`), `ui.eu1.honeycomb.io` = EU (`api.eu1.honeycomb.io`). Examples below use EU — swap the host if you're US.
2. Create a team + one environment. **Use a single environment for all your machines** — Honeycomb can't query across environments, and one env + a `host.name` split is what makes work-vs-personal comparable on one graph.
3. Grab an **ingest key**: environment → Settings → API keys.
4. Put it in the macOS Keychain so it never lands in a dotfiles repo:

```bash
security add-generic-password -a "$USER" -s honeycomb-agent-traces -w '<INGEST_KEY>' -U
```

(Linux: use `secret-tool` or just a chmod-600 env file — same idea, keep it out of git.)

## 1. Claude Code exporter

Non-secret config goes in `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.eu1.honeycomb.io"
  }
}
```

The secret header + per-machine host alias come from your shell profile (so the key stays in the Keychain). Add to a sourced profile file:

```bash
_hc_key=$(security find-generic-password -s honeycomb-agent-traces -w 2>/dev/null)
if [ -n "$_hc_key" ]; then
  export OTEL_EXPORTER_OTLP_HEADERS="x-honeycomb-team=${_hc_key},x-honeycomb-dataset=claude-code-metrics"
fi
unset _hc_key
export OTEL_RESOURCE_ATTRIBUTES="host.name=<your-machine-alias>"
```

Restart `claude` **from a shell that sourced that file**. Gotchas that will bite you otherwise:

- OTel env is read **once at startup** — editing config mid-session does nothing.
- The vars are deliberately **not passed to subprocesses**, so `echo $OTEL_*` inside a Claude session proves nothing.
- The `x-honeycomb-dataset` header is **required for metrics** (they land in a dataset of that name); logs auto-route to a dataset named after `service.name` (`claude-code`).
- Claude Code on the **web has no OTel export path** — this is local machines only.

Verify: within ~2 minutes of chatting, `claude-code` (logs) and a metrics dataset appear. Prompt content is NOT exported (the `prompt` field literally says `<REDACTED>`) unless you opt in with `OTEL_LOG_USER_PROMPTS=1`.

## 2. Codex CLI exporter

Codex has native OTel. Append to `~/.codex/config.toml` (this file stays machine-local, so the key is inline — it sits next to `auth.json` anyway):

```toml
[otel]
environment = "prod"
log_user_prompt = false
exporter = { otlp-http = { endpoint = "https://api.eu1.honeycomb.io/v1/logs", protocol = "binary", headers = { "x-honeycomb-team" = "<INGEST_KEY>" } } }
```

Verify: run any `codex exec`, and a `codex_exec` dataset appears with per-request token counts, model, and TTFT. Prompts are `[REDACTED]`.

## 3. Exact skill + MCP names (the important hack)

Claude Code's built-in attribution lumps all **plugin** skills as `third-party` and all MCP tools as `custom` — useless for "is my ship skill actually firing?". A tiny PreToolUse hook fixes it by shipping exact names to a `workflow-ledger` dataset.

Hook script (`~/.claude/hooks/otel-workflow-ledger.sh`, `chmod +x`):

```bash
#!/usr/bin/env bash
input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)
[ -z "$tool" ] && exit 0

event=""
extra="{}"
if [ "$tool" = "Skill" ]; then
  skill=$(echo "$input" | jq -r '.tool_input.skill // empty')
  [ -z "$skill" ] && exit 0
  event="skill_invoked"
  extra=$(jq -n --arg s "$skill" '{skill: $s}')
elif [[ "$tool" == mcp__* ]]; then
  event="mcp_tool_invoked"
  server=$(echo "$tool" | awk -F'__' '{print $2}')
  extra=$(jq -n --arg t "$tool" --arg srv "$server" '{mcp_tool: $t, mcp_server: $srv}')
else
  exit 0
fi

key=$(security find-generic-password -s honeycomb-agent-traces -w 2>/dev/null)
[ -z "$key" ] && exit 0

session=$(echo "$input" | jq -r '.session_id // "unknown"')
cwd=$(echo "$input" | jq -r '.cwd // "unknown"')
payload=$(jq -n --arg e "$event" --arg sid "$session" --arg c "$cwd" --arg h "$(hostname -s)" \
  '{event: $e, session_id: $sid, cwd: $c, "host.name": $h} + '"$extra")
curl -s -m 5 -X POST "https://api.eu1.honeycomb.io/1/events/workflow-ledger" \
  -H "X-Honeycomb-Team: ${key}" \
  -H "Content-Type: application/json" \
  -d "$payload" >/dev/null 2>&1 || true
exit 0
```

Wire it up in `~/.claude/settings.json` (async — adds zero latency, fails silent):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Skill|mcp__.*",
        "hooks": [
          {"type": "command", "command": "~/.claude/hooks/otel-workflow-ledger.sh", "async": true, "timeout": 10}
        ]
      }
    ]
  }
}
```

## 4. Board query recipes

Build these in the UI (New query) and pin to a board:

| Panel | Dataset | Query |
|-------|---------|-------|
| Cost by machine | metrics | `SUM(claude_code.cost.usage)` GROUP BY `host.name` |
| Cost main vs subagent | metrics | `SUM(claude_code.cost.usage)` GROUP BY `query_source` |
| % of sessions using skills | claude-code | `COUNT_DISTINCT(session.id)` filtered `tool_name = Skill` (named calc) ÷ unfiltered, as a formula |
| Conversations per skill | workflow-ledger | `COUNT_DISTINCT(session_id)` GROUP BY `skill` |
| MCP calls by exact name | workflow-ledger | `COUNT` GROUP BY `mcp_server`, `mcp_tool` |
| Tokens by model, Claude + Codex on one graph | environment-wide | calculated field summing `COALESCE`d token columns from both tools, GROUP BY `model` — see below |

The merged-tokens calculated field (environment-wide query; codex's `input/output_token_count` are string-typed, hence the `INT()`):

```
SUM(SUM(COALESCE($input_tokens, 0), IF(EXISTS($input_token_count), INT($input_token_count), 0)),
    SUM(SUM(COALESCE($output_tokens, 0), IF(EXISTS($output_token_count), INT($output_token_count), 0)),
        SUM(SUM(COALESCE($cache_read_tokens, 0), COALESCE($cache_creation_tokens, 0)),
            SUM(COALESCE($cached_token_count, 0), COALESCE($reasoning_token_count, 0)))))
```

## 5. Landmines (learned the hard way)

- **Environment-wide queries exclude metrics datasets** — merge Claude + Codex from their *log* events (Claude's `api_request` events carry token counts too).
- **Board panel IDs rotate on every board edit** — re-fetch before scripted updates.
- The board's **time picker defaults to 1 hour** — half your panels will look empty until you widen it.
- Google SSO **blocks automated browsers** — if an agent needs to see your board, screenshots or the query APIs are the path, not agent-browser login.
- Second machine = 4 things: settings env block, profile snippet + Keychain add, hook script + hook entry, codex `[otel]` block.
