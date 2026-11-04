#!/usr/bin/env python3

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def load(path):
    try:
        return read(path)
    except (OSError, ValueError):
        return {}


def refresh(config, marketplaces):
    environment = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
    failed = []
    for marketplace in marketplaces:
        try:
            subprocess.run(["claude", "plugin", "marketplace", "update", marketplace],
                           env=environment, capture_output=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            failed.append(marketplace)
    return failed


def check(home, daily=False):
    config = home / ".claude"
    plugins = config / "plugins"
    enabled = read(config / "settings.json").get("enabledPlugins", {})
    registry = read(plugins / "installed_plugins.json").get("plugins", {})
    known = read(plugins / "known_marketplaces.json")
    watched = []
    for identity, on in enabled.items():
        name, marketplace = identity.split("@", 1)
        if on is True and identity in registry and known.get(marketplace, {}).get("autoUpdate") is not True:
            watched.append((identity, name, marketplace))
    marker = plugins / ".plugin-updates-date"
    today = datetime.date.today().isoformat()
    if not (daily and marker.exists() and marker.read_text().strip() == today):
        failed = refresh(config, sorted({marketplace for _, _, marketplace in watched}))
        if failed:
            print(f"Could not refresh {', '.join(failed)}; plugin update check may be stale")
        else:
            marker.write_text(today + "\n")
    for identity, name, marketplace in watched:
        entry = next((entry for entry in registry[identity] if entry.get("scope") == "user"), None)
        location = known.get(marketplace, {}).get("installLocation")
        if entry is None or location is None:
            continue
        installed = load(Path(entry["installPath"]) / ".claude-plugin/plugin.json").get("version")
        catalog = load(Path(location) / ".claude-plugin/marketplace.json").get("plugins", [])
        latest = next((plugin.get("version") for plugin in catalog if plugin.get("name") == name), None)
        if installed and latest and installed != latest:
            print(f"{name} {installed} → {latest} available: claude plugin update {identity}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Report enabled plugins that are behind their marketplace, without updating them")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--daily", action="store_true", help="Refresh marketplaces at most once a day; always report")
    args = parser.parse_args()
    try:
        return check(args.home.expanduser().resolve(), args.daily)
    except (OSError, ValueError, KeyError) as error:
        print(f"Plugin update check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
