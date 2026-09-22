#!/usr/bin/env python3

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def inspect_manifest(path, target, selected):
    data = read(path)
    problems = []
    for name, source in data.get("packages", {}).items():
        if name not in selected:
            problems.append(f"{name} is no longer enabled; inspect its plugin selection")
        elif Path(source).resolve() != selected[name].resolve():
            problems.append(f"{name} selected release changed; old cache still exists or was removed")
    if not data.get("packages") or not data.get("generated_hashes") or not data.get("generator_hashes"):
        problems.append("legacy manifest needs a refresh to enable complete drift checks")
    sources = data.get("source_hashes")
    if sources is None:
        sources = {item["source"]: item["sha256"] for item in data["skills"].values()}
    if "commands" in data:
        outputs = {f"commands/{name}.md" for name in data["commands"]}
        outputs.update(f"skills/{name}/SKILL.md" for name in data["skills"])
        inputs = set(data["commands"].values()) | set(data["skills"].values())
        if outputs - data.get("generated_hashes", {}).keys() or inputs - sources.keys():
            problems.append("manifest has incomplete adapter coverage; run a full refresh")
    for label, hashes, base in [
        ("source", sources, Path("/")),
        ("generated file", data.get("generated_hashes", {}), target),
        ("adapter generator", data.get("generator_hashes", {}), ROOT),
    ]:
        for relative, expected in hashes.items():
            actual = digest(base / relative)
            if actual != expected:
                state = "missing" if actual is None else "changed"
                problems.append(f"{label} {state}: {relative}")
    return problems


def audit(home, codex, opencode, cursor=None):
    results = []
    selected = {}
    config = home / ".claude"
    registry = config / "plugins/installed_plugins.json"
    if registry.exists():
        settings = read(config / "settings.json").get("enabledPlugins", {})
        for identity, entries in read(registry).get("plugins", {}).items():
            if settings.get(identity) is not True:
                continue
            entries = [entry for entry in entries if entry.get("scope") == "user"]
            name = identity.split("@")[0]
            if len(entries) != 1 or name in selected:
                results.append(("WARN", name, ["ambiguous user plugin selection"], "Inspect Claude's installed plugin registry"))
                continue
            source = Path(entries[0]["installPath"])
            selected[name] = source
            problems = [] if source.is_dir() else ["selected plugin directory is missing"]
            release = source / "workflow-release.json"
            if release.is_file():
                problems.extend(f"release content changed or missing: {p}" for p, value in read(release)["hashes"].items() if digest(source / p) != value)
            results.append(("WARN" if problems else "OK", f"source/{name}", problems, f"claude plugin update {shlex.quote(identity)}"))
    else:
        results.append(("SKIP", "sources", ["no installed plugin registry"], ""))
    marketplaces = config / "plugins/known_marketplaces.json"
    if marketplaces.exists():
        for name, entry in read(marketplaces).items():
            source = entry.get("source", {})
            if source.get("source") == "directory":
                results.append(("PINNED", name, [f"local source: {source.get('path')}; upstream updates are paused"], ""))
    command_root = shlex.quote(str(ROOT))
    targets = [
        ("codex/personal", codex / "workflow-migration.json", codex, "codex/sync-workflow.py"),
        ("codex/beam", codex / "beam-migration.json", codex, "codex/sync-workflow.py --package beam"),
        ("opencode", opencode / "migration.json", opencode, "opencode/install.py"),
    ]
    cursor = cursor or home / ".cursor"
    for package, manifest in [("personal", "workflow-migration.json"), ("beam", "beam-migration.json")]:
        script = "cursor/install.py" + (" --package beam" if package == "beam" else "")
        targets.append((f"cursor/{package}", cursor / manifest, cursor, script))
    for label, path, target, script in targets:
        repair = f"cd {command_root} && python3 {script}"
        if not target.exists():
            results.append(("SKIP", label, ["harness directory is absent"], ""))
            continue
        if label.startswith("cursor/") and not path.exists():
            skills = ["socratic-codebase-interview", "review-pr"] if label.endswith("/beam") else [
                "e2e", "ship", "verify", "verify-ui", "investigate", "codex-collab", "writing-pr-descriptions",
            ]
            paths = [target / "skills" / name for name in skills]
            if not any(p.exists() or p.is_symlink() for p in paths):
                results.append(("SKIP", label, ["package adapters are not installed"], ""))
                continue
        if label == "codex/beam" and not path.exists() and "beam-claude-skills" not in selected:
            results.append(("SKIP", label, ["optional Beam package is not installed"], ""))
            continue
        try:
            problems = inspect_manifest(path, target, selected)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            problems = [f"cannot inspect manifest: {exc}"]
        results.append(("WARN" if problems else "OK", label, problems, repair))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only local workflow drift checks; no network or automatic updates")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex", type=Path)
    parser.add_argument("--opencode", type=Path)
    parser.add_argument("--cursor", type=Path)
    args = parser.parse_args(argv)
    home = args.home.expanduser().resolve()
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) if home == Path.home() else home / ".config"
    try:
        results = audit(home, args.codex or home / ".codex", args.opencode or config / "opencode", args.cursor)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"WARN plugin registry: {exc}; inspect Claude's local plugin settings")
        return 1
    for status, label, problems, repair in results:
        print(f"{status} {label}")
        for problem in problems[:3]:
            print(f"  {problem}")
        if len(problems) > 3:
            print(f"  ... and {len(problems) - 3} more")
        if status == "WARN" and repair:
            print(f"  Refresh: {repair}")
    print("Local files only; upstream freshness and running-session reloads are not checked.")
    return int(any(status == "WARN" for status, *_ in results))


def after_refresh():
    link = Path.home() / ".local/bin/workflow-doctor"
    source = Path(__file__).resolve()
    if not link.exists() and not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(source)
    elif link.resolve() != source:
        print(f"WARN existing {link} preserved; run python3 {source} for this checkout")
    with contextlib.redirect_stdout(sys.stderr):
        return main([])


if __name__ == "__main__":
    raise SystemExit(main())
