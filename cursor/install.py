#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]
SHARED = runpy.run_path(str(ROOT / "codex/sync-workflow.py"))
GENERATORS = ["codex/sync-workflow.py", "cursor/install.py", "cursor/compat.md"]


def install(source, target, package="personal"):
    return SHARED["install"](
        source, target, package,
        compatibility=(ROOT / "cursor/compat.md").read_text(),
        generators=GENERATORS,
    )


def main():
    parser = argparse.ArgumentParser(description="Import shared personal or Beam workflows into Cursor")
    parser.add_argument("--package", choices=SHARED["PACKAGES"], default="personal")
    parser.add_argument("--if-installed", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path, default=Path.home() / ".cursor")
    args = parser.parse_args()
    source = args.source or SHARED["installed_source"](Path.home(), args.package, args.if_installed)
    if source is None:
        print(f"Skipped {args.package}: no enabled source installation; existing adapters were not removed")
        return
    target = args.target.expanduser().resolve()
    print(json.dumps(install(source.expanduser(), target, args.package), indent=2))


if __name__ == "__main__":
    main()
