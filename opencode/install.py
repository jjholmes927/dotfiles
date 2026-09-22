#!/usr/bin/env python3

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent


def merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def description(path):
    content = path.read_text()
    if content.startswith("---\n"):
        front = content.split("---", 2)[1]
        match = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
        if match and match[1] not in ("|", ">", "|-", ">-"):
            return match[1].strip().strip("\"'")[:1024]
    return "Run the " + path.stem.replace("-", " ") + " workflow."


def wrapper(name, source, plugin_root=None, skill=False, compatibility=None):
    desc = description(source)
    if source.name == "SKILL.md" and desc == "Run the SKILL workflow.":
        desc = "Use " + name.replace("-", " ") + " for its specialized workflow."
    front = f"name: {name}\n" if skill else ""
    body = (
        f"---\n{front}description: {json.dumps(desc)}\n---\n\n"
        f"Read `{source}` in full and perform its workflow for the user's request.\n"
        f"Apply the OpenCode compatibility rules in `{compatibility or ROOT / 'AGENTS.md'}`.\n"
        "Treat source frontmatter as metadata, not tool permissions. Resolve all\n"
        f"relative file references from `{source.parent}`.\n"
    )
    if plugin_root:
        body += (
            f"Substitute `{plugin_root}` for `${{CLAUDE_PLUGIN_ROOT}}` in paths.\n"
            "For a script that uses that variable internally, set it only for that\n"
            "script invocation to this source root.\n"
        )
    if not skill:
        body += (
            "\nInvocation arguments: $ARGUMENTS\n\n"
            "Substitute these arguments for placeholders in the source workflow.\n"
            "Do not execute example shell blocks merely because they appear in\n"
            "the source; execute only the steps needed for this invocation.\n"
        )
    return body


def plugins(home):
    registry = home / ".claude/plugins/installed_plugins.json"
    settings = home / ".claude/settings.json"
    if not registry.exists() or not settings.exists():
        return []
    installed = json.loads(registry.read_text()).get("plugins", {})
    enabled = json.loads(settings.read_text()).get("enabledPlugins", {})
    result = []
    for name, active in enabled.items():
        if not active:
            continue
        entries = [x for x in installed.get(name, []) if x.get("scope") == "user"]
        if not entries:
            continue
        path = Path(entries[-1]["installPath"])
        if path.is_dir():
            result.append((name.split("@")[0], path))
    return result


def mcp_config(source, check_local=True):
    result, unavailable = {}, []
    for name, entry in source.items():
        if entry["type"] in ("http", "sse"):
            server = {"type": "remote", "url": entry["url"]}
            if entry.get("headers"):
                server["headers"] = entry["headers"]
        elif entry["type"] == "stdio":
            command = [entry["command"], *entry.get("args", [])]
            supported = True
            if check_local:
                supported = shutil.which(command[0]) is not None
                if supported and command[:2] == ["gws", "mcp"]:
                    try:
                        supported = subprocess.run(
                            ["gws", "mcp", "--help"], capture_output=True, timeout=15
                        ).returncode == 0
                    except (OSError, subprocess.TimeoutExpired):
                        supported = False
            server = {"type": "local", "command": command, "enabled": supported}
            if entry.get("env"):
                server["environment"] = entry["env"]
            if not supported:
                unavailable.append(f"{name}: local command unavailable; configured disabled")
        else:
            unavailable.append(f"{name}: unsupported transport {entry['type']}")
            continue
        result[name] = server
    return result, unavailable


class Installer:
    def __init__(self, target):
        self.target = target
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.backup = target / "backups" / stamp
        self.changed = []
        self.generated = {}

    def write(self, relative, content):
        if relative.startswith(("commands/", "skills/")) or relative == "workflow-compat.md":
            self.generated[relative] = hashlib.sha256(content.encode()).hexdigest()
        path = self.target / relative
        if path.is_file() and not path.is_symlink() and path.read_text() == content:
            return
        if path.exists() or path.is_symlink():
            saved = self.backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                saved.symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, saved)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".dotfiles-tmp")
        temporary.write_text(content)
        temporary.replace(path)
        self.changed.append(relative)


def install(home, target):
    importer = Installer(target)
    importer.write("workflow-compat.md", (ROOT / "AGENTS.md").read_text())
    sources = {}
    skill_sources = {}
    native_plugins = []
    notes = []
    for path in sorted((ROOT.parent / "claude/commands").glob("*.md")):
        if path.name.startswith("review-") and path.name != "review-pr.md":
            notes.append(f"/{path.stem}: requires code-reviewer MCP, absent from the shared server list")
        sources[path.stem] = (path, None)
    for path in sorted((ROOT.parent / "codex/skills").glob("*/SKILL.md")):
        skill_sources[path.parent.name] = (path, None)
    installed = plugins(home)
    installed.sort(key=lambda item: item[0] == "joel-workflow")
    for name, directory in installed:
        if name == "superpowers":
            native = directory / ".opencode/plugins/superpowers.js"
            if native.is_file():
                native_plugins.append(native.as_uri())
                continue
        for path in sorted((directory / "skills").glob("*/SKILL.md")):
            skill_sources[path.parent.name] = (path, directory)
        for path in sorted((directory / "commands").glob("*.md")):
            if path.stem.lower() == "readme":
                continue
            command_name = path.stem
            if name == "beam-claude-skills":
                command_name = "beam-" + command_name
            sources[command_name] = (path, directory)
    for name, entry in sources.items():
        if name in skill_sources:
            skill_sources[name] = entry
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        skill_sources[path.parent.name] = (path, None)
        sources[path.parent.name] = (path, None)
    for name, entry in skill_sources.items():
        sources.setdefault(name, entry)
    for name, (source, plugin_root) in sources.items():
        importer.write(f"commands/{name}.md", wrapper(name, source, plugin_root, compatibility=target / "workflow-compat.md"))
    for name, (source, plugin_root) in skill_sources.items():
        importer.write(f"skills/{name}/SKILL.md", wrapper(name, source, plugin_root, True, target / "workflow-compat.md"))
    importer.write("AGENTS.md", (ROOT / "AGENTS.md").read_text())
    importer.write("plugins/dotfiles-notifications.js", (ROOT / "plugins/notifications.js").read_text())
    config_path = target / "opencode.json"
    existing = json.loads(config_path.read_text()) if config_path.exists() else {}
    report_path = target / "migration.json"
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    config = merge(json.loads((ROOT / "opencode.json").read_text()), existing)
    instruction_paths = [
        str(ROOT.parent / "claude/CLAUDE.md"),
        str(ROOT.parent / "claude/output-styles/attention-kind.md"),
    ]
    if existing.get("instructions") is not None:
        instruction_paths = [instruction_paths[0]]
    config["instructions"] = list(dict.fromkeys(existing.get("instructions", []) + instruction_paths))
    unmanaged_plugins = [p for p in existing.get("plugin", []) if p not in previous.get("native_plugins", [])]
    config["plugin"] = list(dict.fromkeys(unmanaged_plugins + native_plugins))
    shared = json.loads((ROOT.parent / "claude/mcp-servers.json").read_text())
    servers, unavailable = mcp_config(shared)
    config["mcp"] = merge(servers, existing.get("mcp", {}))
    notes.extend(unavailable)
    notes.extend([
        "MCP OAuth must be completed separately in OpenCode; model login is preserved.",
        "Claude sessions, auto-memory, statusline, fleet launchers, plugin update hooks, and OTel telemetry are not imported.",
        "Claude marketplace plugins supply workflow sources only; hooks and LSP registration are not executed.",
        "Cross-model e2e/codex-collab retain their external CLI dependencies; no live implementation or publication was run during install.",
    ])
    importer.write("opencode.json", json.dumps(config, indent=2) + "\n")
    report = {
        "dotfiles": str(ROOT.parent),
        "commands": {k: str(v[0]) for k, v in sorted(sources.items())},
        "skills": {k: str(v[0]) for k, v in sorted(skill_sources.items())},
        "source_hashes": {str(source): hashlib.sha256(source.read_bytes()).hexdigest()
                          for source, _ in [*sources.values(), *skill_sources.values()]},
        "native_plugins": native_plugins,
        "notes": notes,
        "packages": {name: str(directory) for name, directory in installed},
        "generated_hashes": importer.generated,
        "generator_hashes": generator_hashes(),
    }
    importer.write("migration.json", json.dumps(report, indent=2) + "\n")
    print(f"Installed {len(sources)} commands and {len(skill_sources)} skill adapters into {target}")
    print(f"Changed {len(importer.changed)} files")
    if importer.backup.exists():
        print(f"Backups: {importer.backup}")
    for note in notes:
        print(f"Note: {note}")
    return report


def main():
    parser = argparse.ArgumentParser()
    default = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "opencode"
    parser.add_argument("--target", type=Path, default=default)
    parser.add_argument("--workflow-only", action="store_true")
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    if args.workflow_only:
        refresh_workflow(Path.home(), target)
    else:
        install(Path.home(), target)
    if target == default.expanduser().resolve():
        doctor = runpy.run_path(str(ROOT.parent / "workflow/doctor.py"))
        doctor["after_refresh"]()


def generator_hashes():
    return {f"opencode/{name}": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ["install.py", "AGENTS.md"]}


def refresh_workflow(home, target):
    installed = plugins(home)
    matches = [root for name, root in installed if name == "joel-workflow"]
    if len(matches) != 1:
        raise ValueError("Expected one enabled user installation of joel-workflow")
    root = matches[0]
    report = json.loads((target / "migration.json").read_text())
    importer = Installer(target)
    report.setdefault("packages", {})["joel-workflow"] = str(root)
    importer.write("workflow-compat.md", (ROOT / "AGENTS.md").read_text())
    skills = {p.parent.name: p for p in (root / "skills").glob("*/SKILL.md")}
    commands = {**skills, **{p.stem: p for p in (root / "commands").glob("*.md") if p.stem.lower() != "readme"}}
    for name in report["skills"]:
        if name in commands:
            skills[name] = commands[name]
    refreshed_sources = set(commands.values()) | set(skills.values())
    for kind, entries in [("commands", commands), ("skills", skills)]:
        for name, source in sorted(entries.items()):
            destination = f"commands/{name}.md" if kind == "commands" else f"skills/{name}/SKILL.md"
            importer.write(destination, wrapper(name, source, root, kind == "skills", target / "workflow-compat.md"))
            report[kind][name] = str(source)
    for name, directory in installed:
        if name != "beam-claude-skills":
            continue
        source = directory / "commands/review-pr.md"
        if source.is_file():
            importer.write("commands/beam-review-pr.md", wrapper("beam-review-pr", source, directory, compatibility=target / "workflow-compat.md"))
            report["commands"]["beam-review-pr"] = str(source)
            refreshed_sources.add(source)
    hashes = report.get("source_hashes", {})
    hashes.update({str(source): hashlib.sha256(source.read_bytes()).hexdigest() for source in refreshed_sources})
    references = {*report["commands"].values(), *report["skills"].values()}
    report["source_hashes"] = {source: hashes[source] for source in sorted(references) if source in hashes}
    report["workflow_release"] = {"source": str(root), "version": json.loads((root / "plugin.json").read_text())["version"]}
    report.setdefault("generated_hashes", {}).update(importer.generated)
    importer.write("migration.json", json.dumps(report, indent=2) + "\n")
    print(f"Refreshed joel-workflow adapters: {len(importer.changed)} changed files")
    if importer.backup.exists():
        print(f"Backups: {importer.backup}")
    return report


if __name__ == "__main__":
    main()
