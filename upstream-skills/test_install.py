import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINKER = ROOT / "upstream-skills/install.sh"

HARNESS_HOMES = {
    "claude": "$HOME/.claude",
    "codex": "$HOME/.codex",
    "cursor": "$HOME/.cursor",
    "opencode": "$HOME/.config/opencode",
}

NOT_HARNESSES = {
    "bash": "shell profile, not an agent harness",
    "kandev": "launches an installed harness; has no skills folder of its own",
    "upstream-skills": "the linker itself",
    "warp": "terminal themes and appearance, not an agent harness",
}


def installer_dirs():
    return sorted(
        path.name for path in ROOT.iterdir()
        if path.is_dir() and any((path / name).is_file() for name in ("install.sh", "install.py"))
    )


def linker_homes():
    block = re.search(r"HARNESS_HOMES=\((.*?)\)", LINKER.read_text(), re.S).group(1)
    return set(re.findall(r'"([^"]+)"', block))


class EveryHarnessGetsUpstreamSkills(unittest.TestCase):
    def test_every_installer_folder_is_a_known_harness_or_an_exception(self):
        unknown = [name for name in installer_dirs() if name not in HARNESS_HOMES and name not in NOT_HARNESSES]
        self.assertEqual(unknown, [], "New installer folder: add it to HARNESS_HOMES (and hook in the linker) or to NOT_HARNESSES with a reason")

    def test_every_harness_installer_runs_the_linker(self):
        for harness in HARNESS_HOMES:
            with self.subTest(harness=harness):
                sources = [path.read_text() for path in (ROOT / harness).glob("install.*")]
                self.assertTrue(any("upstream-skills/install.sh" in source for source in sources),
                                f"{harness} installer never runs upstream-skills/install.sh")

    def test_linker_links_into_every_harness_home(self):
        self.assertEqual(linker_homes(), set(HARNESS_HOMES.values()))


class LinkerBehaviour(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.pinned = {}
        entries = {}
        for line in (ROOT / "upstream-skills/skills.txt").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                repo, path, *ref = line.split()
                entries.setdefault(repo, []).append(path)
                if ref:
                    self.pinned[repo] = ref[0]
        for repo, paths in entries.items():
            checkout = self.checkout(repo)
            for path in paths:
                skill = checkout / path
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(f"---\nname: {skill.name}\n---\n")
            self.git(checkout, "init", "-q")
            self.commit(checkout, "seed")
            if repo in self.pinned:
                self.git(checkout, "tag", self.pinned[repo])
                (checkout / "AFTER_PIN").write_text("newer upstream work\n")
                self.commit(checkout, "after pin")
            self.git(checkout, "remote", "add", "origin", str(checkout))
        self.tools = []
        for line in (ROOT / "upstream-skills/tools.txt").read_text().splitlines():
            source, name, *_ = line.split()
            if source == "gem":
                continue
            self.tools.append((source, name))
            checkout = self.checkout(source)
            checkout.mkdir(parents=True)
            (checkout / name).write_text(f'#!/bin/sh\necho "{name} ran $*"\n')
            (checkout / name).chmod(0o755)
            self.git(checkout, "init", "-q")
            self.commit(checkout, "seed")
            self.git(checkout, "remote", "add", "origin", str(checkout))
        self.bin = self.home / ".local/bin"
        self.fakes = self.root / "fakes"
        self.fakes.mkdir()
        self.fake_log = self.root / "gem.log"
        (self.fakes / "gem").write_text(f"""#!{sys.executable}
import os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
home = Path(os.environ["GEM_HOME"])
if args[0] == "list":
    sys.exit(0 if (home / "bin" / args[2]).exists() else 1)
bindir = Path(args[args.index("--bindir") + 1])
bindir.mkdir(parents=True, exist_ok=True)
(bindir / args[1]).write_text("fake")
""")
        (self.fakes / "ruby").write_text("#!/bin/sh\nprintf /fake/ruby\n")
        for fake in ("gem", "ruby"):
            (self.fakes / fake).chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "XDG_DATA_HOME": str(self.data),
                    "PATH": str(self.fakes) + os.pathsep + os.environ["PATH"], "FAKE_LOG": str(self.fake_log)}

    def checkout(self, repo):
        return self.data / "upstream-skills" / repo.replace("/", "__")

    def git(self, checkout, *args):
        return subprocess.run(["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, checkout, message):
        self.git(checkout, "add", ".")
        self.git(checkout, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)

    def run_linker(self):
        return subprocess.run([str(LINKER)], env=self.env, capture_output=True, text=True, check=True).stdout

    def homes(self):
        return [Path(home.replace("$HOME", str(self.home))) for home in HARNESS_HOMES.values()]

    def test_links_each_skill_into_every_present_harness_and_is_idempotent(self):
        for home in self.homes():
            home.mkdir(parents=True)
        self.run_linker()
        self.run_linker()
        for home in self.homes():
            for skill in ("grill-me", "grilling", "ponytail", "ponytail-review"):
                link = home / "skills" / skill
                self.assertTrue(link.is_symlink(), link)
                self.assertTrue((link / "SKILL.md").is_file(), link)

    def test_skips_missing_harnesses_and_leaves_existing_skills_alone(self):
        claude = self.home / ".claude"
        (claude / "skills/grill-me").mkdir(parents=True)
        output = self.run_linker()
        self.assertFalse((claude / "skills/grill-me").is_symlink())
        self.assertIn("left alone", output)
        self.assertTrue((claude / "skills/grilling").is_symlink())
        self.assertFalse((self.home / ".codex").exists())

    def test_pinned_repo_is_checked_out_at_its_ref(self):
        self.assertTrue(self.pinned, "skills.txt has no pinned entries to test")
        self.run_linker()
        for repo, ref in self.pinned.items():
            with self.subTest(repo=repo):
                checkout = self.checkout(repo)
                self.assertEqual(self.git(checkout, "rev-parse", "HEAD"), self.git(checkout, "rev-parse", f"{ref}^{{commit}}"))
                self.assertFalse((checkout / "AFTER_PIN").exists())

    def test_conflicting_refs_for_one_repo_stop_the_install(self):
        manifest = (ROOT / "upstream-skills/skills.txt").read_text()
        linker = self.root / "upstream-skills/install.sh"
        linker.parent.mkdir()
        linker.write_text(LINKER.read_text())
        linker.chmod(0o755)
        (linker.parent / "skills.txt").write_text(manifest + "DietrichGebert/ponytail skills/ponytail-audit v9.9.9\n")
        (linker.parent / "tools.txt").write_text((ROOT / "upstream-skills/tools.txt").read_text())
        result = subprocess.run([str(linker)], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("same ref", result.stderr)

    def test_tools_get_working_wrappers_and_a_rerun_changes_nothing(self):
        self.run_linker()
        first = {path.name: path.read_text() for path in self.bin.iterdir()}
        output = self.run_linker()
        self.assertEqual(first, {path.name: path.read_text() for path in self.bin.iterdir()})
        for source, name in self.tools:
            with self.subTest(tool=name):
                self.assertIn(f"✓ {self.bin / name}", output)
                ran = subprocess.run([str(self.bin / name), "--changed"], capture_output=True, text=True, check=True).stdout
                self.assertEqual(f"{name} ran --changed\n", ran)
        self.assertIn('exec "/fake/ruby"', first["rubycritic"])
        installs = [line for line in self.fake_log.read_text().splitlines() if line.startswith("install ")]
        self.assertEqual(1, len(installs))

    def test_an_existing_command_with_a_tool_name_is_left_alone(self):
        self.bin.mkdir(parents=True)
        (self.bin / "crapper").write_text("#!/bin/sh\necho mine\n")
        output = self.run_linker()
        self.assertEqual("#!/bin/sh\necho mine\n", (self.bin / "crapper").read_text())
        self.assertIn("left alone", output)


if __name__ == "__main__":
    unittest.main()
