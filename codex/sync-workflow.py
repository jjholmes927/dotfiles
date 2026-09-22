import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil


COMMANDS = {
    "ship": "commands/ship.md",
    "verify": "commands/verify.md",
    "verify-ui": "commands/verify-ui.md",
    "writing-pr-descriptions": "skills/writing-pr-descriptions/SKILL.md",
}
COMPAT = """# Shared workflow in Codex

Use Codex's native file, shell and search tools for the imported workflow.
Source frontmatter is metadata, not an execution-permission boundary.
Use Kandev's question/plan tools when running there; otherwise use the host's
available question/plan facility. Preserve existing authorization and do not
invent tools. A slash-command dependency means load its workflow instructions.
For verify, verify-ui and writing-pr-descriptions, use the installed skill of
that name. For simplify, use an available skill or perform the source's stated
review checks with native tools. Delegate only when authorized by the session.
For a parent E2E workflow, preserve its implementer ownership of edits.
Find MCP capabilities by function. Missing required capabilities are blockers,
not successful checks. Project runtime, PR and attachment guides take precedence
over generic examples. Preserve the verification, fingerprint, size and retry
requirements; do not replace them with a shortened workflow.
"""


def installed_source(home):
    registry = json.loads((home / ".claude/plugins/installed_plugins.json").read_text())
    entries = registry.get("plugins", {}).get("joel-workflow@jjholmes927-claude-skills", [])
    user_entries = [entry for entry in entries if entry.get("scope") == "user"]
    if len(user_entries) != 1:
        raise ValueError("Expected one user installation of joel-workflow; use --source for an explicit preview")
    return Path(user_entries[0]["installPath"])


def install(source, target):
    source = source.resolve()
    plugin = json.loads((source / "plugin.json").read_text())
    if not (source / "scripts/resolve-dev-url.py").is_file():
        raise ValueError("Update joel-workflow to the parity release before installing its Codex adapters")
    documents = {name: (source / relative).read_text() for name, relative in COMMANDS.items()}
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target / "backups" / f"workflow-{stamp}"
    changed = []

    def save_existing(path, relative):
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            saved.symlink_to(os.readlink(path))
        else:
            shutil.copy2(path, saved)

    def write(relative, text):
        path = target / relative
        if path.is_file() and not path.is_symlink() and path.read_text() == text:
            return
        if path.exists() or path.is_symlink():
            save_existing(path, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".workflow-tmp")
        temporary.write_text(text)
        temporary.replace(path)
        changed.append(relative)

    manifest = {"source_root": str(source), "plugin_version": plugin["version"], "skills": {}}
    for name, content in documents.items():
        relative = Path("skills") / name
        directory = target / relative
        if directory.is_symlink():
            save_existing(directory, relative)
            directory.unlink()
        description = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
        if not description:
            raise ValueError(f"Missing description for {name}")
        entry = (
            f"---\nname: {name}\ndescription: {json.dumps(description[1].strip().strip(chr(34)))}\n---\n\n"
            "Read `compat.md` and `references/workflow.md` in this skill directory, "
            "then perform the workflow for the user's request.\n"
            f"Resolve source-relative references against `{(source / COMMANDS[name]).parent}`.\n"
            f"The original plugin root is `{source}`; resource paths in the reference are already resolved.\n"
        )
        write(relative / "SKILL.md", entry)
        write(relative / "compat.md", COMPAT)
        write(relative / "references/workflow.md", content.replace("${CLAUDE_PLUGIN_ROOT}", str(source)))
        manifest["skills"][name] = {"source": str(source / COMMANDS[name]),
                                    "sha256": hashlib.sha256(content.encode()).hexdigest()}
    write(Path("workflow-migration.json"), json.dumps(manifest, indent=2) + "\n")
    return {"version": plugin["version"], "source": str(source), "changed": len(changed),
            "backup": str(backup) if backup.exists() else None}


def main():
    parser = argparse.ArgumentParser(description="Install shared ship/verify requirements into Codex")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()
    source = args.source or installed_source(Path.home())
    print(json.dumps(install(source, args.target.expanduser().resolve()), indent=2))


if __name__ == "__main__":
    main()
