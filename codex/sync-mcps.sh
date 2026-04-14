#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="$SCRIPT_DIR/../claude/mcp-servers.json"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Missing shared MCP source file: $SOURCE_FILE" >&2
  exit 1
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "codex CLI is not installed or not on PATH." >&2
  exit 1
fi

python3 - "$SOURCE_FILE" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

source = json.loads(Path(sys.argv[1]).read_text())

def run(*args):
    return subprocess.run(args, capture_output=True, text=True)

def exists(name):
    result = run("codex", "mcp", "get", name, "--json")
    return result.returncode == 0

def remove(name):
    result = run("codex", "mcp", "remove", name)
    return result.returncode == 0, result

def gws_mcp_supported():
    result = run("gws", "mcp", "--help")
    return result.returncode == 0

skipped = []

for name, config in source.items():
    if (
        config["type"] == "stdio"
        and config.get("command") == "gws"
        and config.get("args", [None])[0] == "mcp"
        and not gws_mcp_supported()
    ):
        skipped.append(name)
        if exists(name):
            ok, result = remove(name)
            if not ok:
                print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
                raise SystemExit(result.returncode)
            print(f"Removed unsupported Codex MCP server: {name}")
        else:
            print(f"Skipping unsupported Codex MCP server on this machine: {name}")
        continue

    if exists(name):
        print(f"Already configured in Codex: {name}")
        continue

    if config["type"] == "http":
        result = run("codex", "mcp", "add", name, "--url", config["url"])
    elif config["type"] == "stdio":
        command = [config["command"], *config.get("args", [])]
        result = run("codex", "mcp", "add", name, "--", *command)
    else:
        print(f"Skipping unsupported MCP type for {name}: {config['type']}")
        continue

    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        raise SystemExit(result.returncode)

    print(f"Added Codex MCP server: {name}")

print("MCP sync complete.")
if skipped:
    print("Skipped MCP servers without local support:")
    for name in skipped:
        print(f"  - {name}")
print("Authenticate user-level HTTP MCPs as needed with:")
for name, config in source.items():
    if config["type"] == "http":
        print(f"  codex mcp login {name}")
PY
