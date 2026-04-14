#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="$SCRIPT_DIR/mcp-servers.json"
TARGET_FILE="$HOME/.claude.json"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Missing MCP source file: $SOURCE_FILE" >&2
  exit 1
fi

python3 - "$SOURCE_FILE" "$TARGET_FILE" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])

source_servers = json.loads(source_path.read_text())
filtered_servers = dict(source_servers)
skipped = []

gws = filtered_servers.get("gws")
if (
    isinstance(gws, dict)
    and gws.get("type") == "stdio"
    and gws.get("command") == "gws"
    and gws.get("args", [None])[0] == "mcp"
):
    gws_result = shutil.which("gws")
    if gws_result is None:
        filtered_servers.pop("gws", None)
        skipped.append("gws")
    else:
        import subprocess

        probe = subprocess.run(
            ["gws", "mcp", "--help"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            filtered_servers.pop("gws", None)
            skipped.append("gws")

if target_path.exists():
    target_data = json.loads(target_path.read_text())
else:
    target_data = {}

previous = target_data.get("mcpServers", {})

if previous == filtered_servers:
    print("Claude MCP config already up to date.")
    raise SystemExit(0)

target_data["mcpServers"] = filtered_servers

if target_path.exists():
    backup = target_path.with_name(
        f"{target_path.name}.backup-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    )
    shutil.copy2(target_path, backup)
    print(f"Backed up {target_path} to {backup}")

target_path.write_text(json.dumps(target_data, indent=2) + "\n")
print(f"Synced {len(filtered_servers)} Claude MCP servers into {target_path}")
for name in filtered_servers:
    print(f"  - {name}")
if skipped:
    print("Skipped MCP servers without local support:")
    for name in skipped:
        print(f"  - {name}")
PY
