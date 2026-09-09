#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def debug(command):
    with tempfile.TemporaryFile(mode="w+") as output:
        result = subprocess.run(
            ["opencode", "debug", command], stdout=output,
            stderr=subprocess.PIPE, text=True, timeout=60
        )
        if result.returncode:
            print(f"OpenCode debug {command} failed: {result.stderr.strip()}", file=sys.stderr)
            raise SystemExit(result.returncode)
        output.seek(0)
        return json.load(output)


def main():
    config = debug("config")
    skills = debug("skill")
    names = {entry["name"] for entry in skills}
    commands = set(config.get("command", {}))
    expected = {
        "ship", "review-pr", "verify", "verify-ui", "pick-up-linear-ticket",
        "handoff", "second-brain", "style", "save-permissions", "simplify",
    }
    absent = expected - commands
    print(f"OpenCode resolved {len(commands)} commands and {len(names)} skills")
    print("Core commands: " + ("OK" if not absent else "MISSING " + ", ".join(sorted(absent))))
    print("Superpowers: " + ("OK" if "brainstorming" in names else "not discovered"))
    print("MCP definitions: " + ", ".join(sorted(config.get("mcp", {}))))
    print("Instruction files: " + str(len(config.get("instructions", []))))
    for path in config.get("instructions", []):
        if path.startswith("/") and not Path(path).is_file():
            print(f"Missing instruction file: {path}")
            absent.add(path)
    if absent:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
