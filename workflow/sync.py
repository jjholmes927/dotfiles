#!/usr/bin/env python3

import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "joel-workflow@jjholmes927-claude-skills"


def read(path):
    return json.loads(path.read_text())


def sync(home, refresh_only=False, daily=False):
    config = home / ".claude"
    plugins = config / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    with (plugins / ".workflow-sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = plugins / ".workflow-sync-date"
        today = datetime.date.today().isoformat()
        enabled = read(config / "settings.json").get("enabledPlugins", {})
        if enabled.get(IDENTITY) is not True:
            raise ValueError(f"Enable {IDENTITY} before syncing")
        marketplaces = read(plugins / "known_marketplaces.json")
        source = marketplaces.get("jjholmes927-claude-skills", {}).get("source", {})
        if source != {"source": "github", "repo": "jjholmes927/jjholmes927-claude-skills"}:
            raise ValueError("Normal sync requires the published GitHub marketplace; use temporary targets for previews")
        doctor = runpy.run_path(str(ROOT / "workflow/doctor.py"))
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) if home == Path.home() else home / ".config"
        if daily and marker.exists() and marker.read_text().strip() == today:
            results = doctor["audit"](home, home / ".codex", config_root / "opencode", home / ".cursor")
            if not any(status == "WARN" for status, *_ in results):
                return 0
        if not refresh_only and marker.exists():
            marker.unlink()
        registry = read(plugins / "installed_plugins.json").get("plugins", {})
        packages = [IDENTITY]
        beam = "beam-claude-skills@beam-claude-skills"
        if enabled.get(beam) is True and beam in registry:
            packages.append(beam)
        if not refresh_only:
            environment = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
            for identity in packages:
                marketplace = identity.split("@", 1)[1]
                subprocess.run(["claude", "plugin", "marketplace", "update", marketplace], env=environment, check=True, timeout=120)
                subprocess.run(["claude", "plugin", "update", identity], env=environment, check=True, timeout=120)
        codex = runpy.run_path(str(ROOT / "codex/sync-workflow.py"))
        source = codex["installed_source"](home)
        current = read(plugins / "installed_plugins.json")["plugins"][IDENTITY]
        selected = [entry for entry in current if entry.get("scope") == "user"]
        if selected[0].get("version") != read(source / "plugin.json")["version"]:
            raise ValueError("Installed plugin version differs from its source metadata")
        beam_source = codex["installed_source"](home, "beam", optional=True)
        targets = [("codex", home / ".codex"), ("cursor", home / ".cursor"), ("opencode", config_root / "opencode")]
        for name, target in targets:
            if not target.is_dir():
                print(f"SKIP {name}: not installed")
                continue
            adapter = runpy.run_path(str(ROOT / name / ("sync-workflow.py" if name == "codex" else "install.py")))
            if name == "opencode":
                adapter["install"](home, target)
            else:
                print(name, adapter["install"](source, target))
                if beam_source:
                    print(name, adapter["install"](beam_source, target, "beam"))
        status = doctor["after_refresh"]() if home == Path.home() else doctor["main"](["--home", str(home)])
        if status:
            raise ValueError("Workflow drift remains; resolve the doctor warnings before using these adapters")
        if not refresh_only and (not marker.exists() or marker.read_text().strip() != today):
            marker.write_text(today + "\n")
        print("Workflow sync complete. Start fresh sessions to load updated skills.")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Update the published marketplace and refresh every installed workflow adapter")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--refresh-only", action="store_true", help="Retry adapters against the selected published plugin without network updates")
    parser.add_argument("--daily", action="store_true", help="Skip if a complete update already succeeded today")
    args = parser.parse_args()
    try:
        return sync(args.home.expanduser().resolve(), args.refresh_only, args.daily)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Workflow sync failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
