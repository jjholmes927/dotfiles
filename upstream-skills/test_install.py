import os
from pathlib import Path
import re
import subprocess
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
        checkout = self.data / "upstream-skills/mattpocock__skills"
        for line in (ROOT / "upstream-skills/skills.txt").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                skill = checkout / line.split()[1]
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(f"---\nname: {skill.name}\n---\n")
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-qm", "seed"], check=True)

    def run_linker(self):
        env = {**os.environ, "HOME": str(self.home), "XDG_DATA_HOME": str(self.data)}
        return subprocess.run([str(LINKER)], env=env, capture_output=True, text=True, check=True).stdout

    def homes(self):
        return [Path(home.replace("$HOME", str(self.home))) for home in HARNESS_HOMES.values()]

    def test_links_each_skill_into_every_present_harness_and_is_idempotent(self):
        for home in self.homes():
            home.mkdir(parents=True)
        self.run_linker()
        self.run_linker()
        for home in self.homes():
            for skill in ("grill-me", "grilling"):
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


if __name__ == "__main__":
    unittest.main()
