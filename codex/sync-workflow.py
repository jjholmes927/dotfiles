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
    "e2e": "skills/e2e/SKILL.md",
    "investigate": "skills/investigate/SKILL.md",
    "codex-collab": "skills/codex-collab/SKILL.md",
}
COMPAT = """# Shared workflow in Codex

Use Codex's native file, shell and search tools for the imported workflow.
Source frontmatter is metadata, not an execution-permission boundary.
Use Kandev's question/plan tools when running there; otherwise use the host's
available question/plan facility. Preserve existing authorization and do not
invent tools. A slash-command dependency means load its workflow instructions.
In Kandev, pending or timed-out questions are hard waiting barriers: end the
turn without dependent work. Only completed answers establish a decision.
Native delegation is optional and needs explicit session authorization.
Use the task's selected E2E route; a Codex host does not imply launching Codex
recursively. A delegated child receives a bounded brief, never the E2E workflow.
For verify, verify-ui and writing-pr-descriptions, use the installed skill of
that name. For simplify, use an available skill or perform the source's stated
review checks with native tools. Delegate only when authorized by the session.
For a parent E2E workflow, preserve its implementer ownership of edits.
Find MCP capabilities by function. Missing required capabilities are blockers,
not successful checks. Project runtime, PR and attachment guides take precedence
over generic examples. Preserve the verification, fingerprint, size and retry
requirements; do not replace them with a shortened workflow.
"""

REVIEW_COMPAT = """# Beam review in Codex

Use native tools and the repository's applicable guides. Preserve the source's
four review lenses, evidence requirements, severity and incomplete outcomes.
When delegation is not authorized, apply the lenses sequentially and report
that execution mode; do not claim independent agents ran. A required independent
review in a parent workflow still needs its approved separate-context route.
Review only the exact requested PR/base/head; do not edit or switch the checkout.
For a branch without a PR, use its explicit base/head and report locally.
Do not infer permission to post from authorship. Show findings locally unless
the session explicitly authorized publication; use a body file for an authorized
GitHub comment. A failed or skipped required lens remains incomplete.
"""

INTERVIEW_COMPAT = """# Socratic interview in Codex

Use native read/search tools to establish the source-grounded interview.
Testing understanding does not authorize code changes or extra deliverables.
Preserve the source's question ladder, grading, corrections, detours and ending.
Do not turn a request to explain a system into an interview.

In Kandev, use ask_user_question_kandev for one question at a time. Put the
verdict, evidence-backed corrections and optional soundbite in context_paragraphs,
and the numbered next question in prompt. Invite an answer in the custom text
field. When the schema requires options, provide interview controls such as
"Skip this question" and "End interview", never candidate answers or hints.
A skip is not assessed, not an incorrect answer. An end/rejection closes with
the source's scorecard based only on answers actually received.
Follow the question tool's waiting contract: do not continue work or grade
without a completed answer. A pending/timeout result ends the turn; it is not
an answer. Outside Kandev, ask the one question in the reply and end the turn
to wait. Never invent the user's answer or continue the interview autonomously.
"""
PACKAGES = {
    "personal": {
        "id": "joel-workflow@jjholmes927-claude-skills",
        "metadata": "plugin.json", "commands": COMMANDS,
        "compat": COMPAT, "manifest": "workflow-migration.json",
    },
    "beam": {
        "id": "beam-claude-skills@beam-claude-skills",
        "metadata": ".claude-plugin/plugin.json",
        "commands": {
            "socratic-codebase-interview": "skills/socratic-codebase-interview/SKILL.md",
            "review-pr": "commands/review-pr.md",
        },
        "compat": INTERVIEW_COMPAT, "manifest": "beam-migration.json",
    },
}


def installed_source(home, package="personal", optional=False):
    identity = PACKAGES[package]["id"]
    registry_path = home / ".claude/plugins/installed_plugins.json"
    if optional and not registry_path.exists():
        return None
    registry = json.loads(registry_path.read_text())
    entries = registry.get("plugins", {}).get(identity, [])
    user_entries = [entry for entry in entries if entry.get("scope") == "user"]
    if not user_entries and optional:
        return None
    if len(user_entries) != 1:
        raise ValueError(f"Expected one user installation of {identity}; use --source for an explicit preview")
    if package == "beam" or optional:
        settings_path = home / ".claude/settings.json"
        settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        if settings.get("enabledPlugins", {}).get(identity) is not True:
            if optional:
                return None
            raise ValueError(f"Enable {identity} before importing it, or use --source for an explicit preview")
    return Path(user_entries[0]["installPath"])


def install(source, target, package="personal"):
    source = source.resolve()
    config = PACKAGES[package]
    commands = config["commands"]
    plugin = json.loads((source / config["metadata"]).read_text())
    if package == "beam" and plugin.get("name") != "beam-claude-skills":
        raise ValueError("Expected Beam plugin metadata for the interview adapter")
    if package == "personal" and not (source / "scripts/resolve-dev-url.py").is_file():
        raise ValueError("Update joel-workflow to the parity release before installing its Codex adapters")
    documents = {name: (source / relative).read_text() for name, relative in commands.items()}
    descriptions = {}
    for name, content in documents.items():
        description = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
        if not description:
            raise ValueError(f"Missing description for {name}")
        descriptions[name] = description[1].strip().strip(chr(34))
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
        entry = (
            f"---\nname: {name}\ndescription: {json.dumps(descriptions[name])}\n---\n\n"
            "Read `compat.md` and `references/workflow.md` in this skill directory, "
            "then perform the workflow for the user's request.\n"
            f"Resolve source-relative references against `{(source / commands[name]).parent}`.\n"
            f"The original plugin root is `{source}`; resource paths in the reference are already resolved.\n"
        )
        write(relative / "SKILL.md", entry)
        compatibility = REVIEW_COMPAT if package == "beam" and name == "review-pr" else config["compat"]
        write(relative / "compat.md", compatibility)
        write(relative / "references/workflow.md", content.replace("${CLAUDE_PLUGIN_ROOT}", str(source)))
        manifest["skills"][name] = {"source": str(source / commands[name]),
                                    "sha256": hashlib.sha256(content.encode()).hexdigest()}
    write(Path(config["manifest"]), json.dumps(manifest, indent=2) + "\n")
    return {"version": plugin["version"], "source": str(source), "changed": len(changed),
            "backup": str(backup) if backup.exists() else None}


def main():
    parser = argparse.ArgumentParser(description="Install selected shared workflow sources into Codex")
    parser.add_argument("--package", choices=PACKAGES, default="personal")
    parser.add_argument("--if-installed", action="store_true", help="Skip an absent or disabled optional source package")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()
    source = args.source or installed_source(Path.home(), args.package, args.if_installed)
    if source is None:
        print(f"Skipped {args.package}: no enabled source installation; existing adapters were not removed")
        return
    print(json.dumps(install(source, args.target.expanduser().resolve(), args.package), indent=2))


if __name__ == "__main__":
    main()
