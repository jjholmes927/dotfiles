import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def prepare(source, destination):
    source = source.resolve()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)
    if dirty.strip():
        raise ValueError("Commit the workflow source before preparing an immutable release")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    version = json.loads((source / "plugin.json").read_text())["version"]
    release = destination / "releases" / f"{version}-{commit[:12]}"
    if release.exists():
        metadata = json.loads((release / "workflow-release.json").read_text())
        if metadata["commit"] != commit:
            raise ValueError("Release provenance mismatch")
        for relative, expected in metadata["hashes"].items():
            if hashlib.sha256((release / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Released content changed: {relative}")
        return release
    release.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=release.parent) as temporary:
        staging = Path(temporary)
        with tempfile.TemporaryFile() as archive:
            subprocess.run(["git", "archive", "--format=tar", commit], cwd=source, stdout=archive, check=True)
            archive.seek(0)
            subprocess.run(["tar", "-xf", "-", "-C", str(staging)], stdin=archive, check=True)
        marketplace = staging / ".claude-plugin/marketplace.json"
        catalog = json.loads(marketplace.read_text())
        entry = next(p for p in catalog["plugins"] if p["name"] == "joel-workflow")
        if catalog["version"] != version or entry["version"] != version:
            raise ValueError("Plugin and marketplace versions must match")
        entry["source"] = "./"
        marketplace.write_text(json.dumps(catalog, indent=2) + "\n")
        shutil.copy2(staging / "plugin.json", staging / ".claude-plugin/plugin.json")
        hashes = {str(p.relative_to(staging)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(staging.rglob("*")) if p.is_file()}
        (staging / "workflow-release.json").write_text(json.dumps({
            "source": str(source), "commit": commit, "version": version, "hashes": hashes,
            "distribution": "Local immutable snapshot; marketplace source rewritten to ./ for local installation",
        }, indent=2) + "\n")
        staging.rename(release)
    return release


def install(release, config, destination):
    backup = destination / "backups" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, mode=0o700)
    for relative in ["settings.json", "plugins/known_marketplaces.json", "plugins/installed_plugins.json"]:
        source = config / relative
        if source.exists():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    env = dict(os.environ)
    if config == (Path.home() / ".claude").resolve():
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = str(config)
    subprocess.run(["claude", "plugin", "marketplace", "add", str(release)], env=env, check=True)
    registry = config / "plugins/installed_plugins.json"
    installed = json.loads(registry.read_text()).get("plugins", {}) if registry.exists() else {}
    operation = "update" if "joel-workflow@jjholmes927-claude-skills" in installed else "install"
    subprocess.run(["claude", "plugin", operation, "joel-workflow@jjholmes927-claude-skills", "--json"], env=env, check=True)
    print(f"Configuration backup: {backup}")


def main():
    parser = argparse.ArgumentParser(description="Prepare or install a committed local workflow release using Claude's CLI")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path.home() / ".local/share/joel-workflow")
    parser.add_argument("--claude-config", type=Path, default=Path.home() / ".claude")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    release = prepare(args.source, destination)
    print(f"Release: {release}", flush=True)
    if args.install:
        install(release, args.claude_config.expanduser().resolve(), destination)


if __name__ == "__main__":
    main()
