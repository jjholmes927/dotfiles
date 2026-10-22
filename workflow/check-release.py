#!/usr/bin/env python3

import argparse
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def check_edits(workflows, base):
    changed = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=ACMRT", base, "HEAD",
                                       "--", "codex/skills", "claude/commands"], cwd=ROOT, text=True)
    for filename in changed.splitlines():
        path = Path(filename)
        name = path.parent.name if path.name == "SKILL.md" else path.stem if path.parent == Path("claude/commands") else None
        if name in workflows:
            raise ValueError(f"{filename}: edit shared instructions in jjholmes927-claude-skills, then run workflow-sync")


def check(source, base=None):
    source = source.resolve()
    metadata = json.loads((source / "plugin.json").read_text())
    catalog = json.loads((source / ".claude-plugin/marketplace.json").read_text())
    entry = next(p for p in catalog["plugins"] if p["name"] == "joel-workflow")
    if metadata["version"] != catalog["version"] or metadata["version"] != entry["version"]:
        raise ValueError("Plugin and marketplace versions must match")
    workflows = {p.stem: p for p in (source / "commands").glob("*.md") if p.stem.lower() != "readme"}
    workflows.update({p.parent.name: p for p in (source / "skills").glob("*/SKILL.md")})
    if not workflows:
        raise ValueError("The release has no workflows")
    if base:
        check_edits(workflows, base)
    codex = runpy.run_path(str(ROOT / "codex/sync-workflow.py"))
    cursor = runpy.run_path(str(ROOT / "cursor/install.py"))
    opencode = runpy.run_path(str(ROOT / "opencode/install.py"))
    doctor = runpy.run_path(str(ROOT / "workflow/doctor.py"))
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary)
        registry = home / ".claude/plugins/installed_plugins.json"
        registry.parent.mkdir(parents=True)
        identity = "joel-workflow@jjholmes927-claude-skills"
        registry.write_text(json.dumps({"plugins": {identity: [{"scope": "user", "installPath": str(source)}]}}))
        (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {identity: True}}))
        opencode["install"].__globals__["mcp_config"] = lambda config: ({}, [])
        targets = [("codex", codex, "workflow-migration.json"),
                   ("cursor", cursor, "workflow-migration.json"),
                   ("opencode", opencode, "migration.json")]
        for name, adapter, manifest_name in targets:
            target = home / name
            with contextlib.redirect_stdout(io.StringIO()):
                if name == "opencode":
                    adapter["install"](home, target)
                else:
                    adapter["install"](source, target)
            manifest = target / manifest_name
            problems = doctor["inspect_manifest"](manifest, target, {"joel-workflow": source})
            if problems:
                raise ValueError(f"{name}: " + "; ".join(problems))
            data = json.loads(manifest.read_text())
            for skill, path in workflows.items():
                imported = data["skills"][skill]
                origin = imported if name == "opencode" else imported["source"]
                if Path(origin) != path:
                    raise ValueError(f"{name}/{skill}: wrong source {origin}")
                if name != "opencode":
                    actual = (target / "skills" / skill / "references/workflow.md").read_text()
                    if actual != path.read_text().replace("${CLAUDE_PLUGIN_ROOT}", str(source)):
                        raise ValueError(f"{name}/{skill}: source content differs")
            before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            with contextlib.redirect_stdout(io.StringIO()):
                if name == "opencode":
                    adapter["install"](home, target)
                else:
                    adapter["install"](source, target)
            after = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            if before != after:
                raise ValueError(f"{name}: repeated import changed files")
            print(f"OK {name}: {len(workflows)} marketplace workflows; source parity and repeat import verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify a marketplace release against all local harness adapters")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", help="Reject changes to duplicate shared instructions in this dotfiles diff")
    args = parser.parse_args()
    check(args.source, args.base)
