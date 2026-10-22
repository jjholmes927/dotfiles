import fcntl
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER = runpy.run_path(str(ROOT / "codex/sync-workflow.py"))
IDENTITY = "joel-workflow@jjholmes927-claude-skills"


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.plugins = self.home / ".claude/plugins"
        self.release = self.home / "release"
        self.write(self.release / "plugin.json", {"name": "joel-workflow", "version": "2.24.0"})
        self.write(self.release / "scripts/resolve-dev-url.py", "resolver")
        for name in [*IMPORTER["COMMANDS"], "ui-component-review"]:
            self.write(self.release / "skills" / name / "SKILL.md", f"---\nname: {name}\ndescription: Use {name}\n---\nPublished {name} source")
        self.write(self.plugins / "installed_plugins.json", {"plugins": {IDENTITY: [{"scope": "user", "version": "2.24.0", "installPath": str(self.release)}]}})
        self.write(self.plugins / "known_marketplaces.json", {"jjholmes927-claude-skills": {"source": {"source": "github", "repo": "jjholmes927/jjholmes927-claude-skills"}}})
        self.write(self.home / ".claude/settings.json", {"enabledPlugins": {IDENTITY: True}})
        self.write(self.home / ".codex/config.toml", "preserve my configuration")
        fake = self.home / "bin/claude"
        self.write(fake, f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\np=Path(os.environ['CLAUDE_CONFIG_DIR'])/'calls'\nwith p.open('a') as log: log.write(' '.join(sys.argv[1:])+'\\n')\nsys.exit(int(os.environ.get('FAKE_FAIL','0')))\n")
        fake.chmod(0o755)
        self.environment = {**os.environ, "PATH": str(fake.parent) + os.pathsep + os.defpath}

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict) else content)

    def run_sync(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(ROOT / "workflow/sync.py"), "--home", str(self.home), *arguments],
                              env=self.environment, capture_output=True, text=True)

    def test_cli_refreshes_every_installed_harness_then_daily_run_skips(self):
        self.write(self.home / ".cursor/cli-config.json", "preserve cursor config")
        self.write(self.home / ".config/opencode/opencode.json", {"model": "keep/me", "permission": {"edit": "ask"}})
        result = self.run_sync()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        calls = (self.home / ".claude/calls").read_text()
        self.assertEqual(["plugin marketplace update jjholmes927-claude-skills", "plugin update " + IDENTITY], calls.splitlines())
        for directory in [".codex", ".cursor"]:
            target = self.home / directory
            data = json.loads((target / "workflow-migration.json").read_text())
            self.assertEqual("2.24.0", data["plugin_version"])
            self.assertEqual(str(self.release / "skills/ui-component-review/SKILL.md"), data["skills"]["ui-component-review"]["source"])
        report = json.loads((self.home / ".config/opencode/migration.json").read_text())
        self.assertEqual(str(self.release / "skills/ui-component-review/SKILL.md"), report["skills"]["ui-component-review"])
        self.assertEqual("preserve my configuration", (self.home / ".codex/config.toml").read_text())
        self.assertEqual("preserve cursor config", (self.home / ".cursor/cli-config.json").read_text())
        config = json.loads((self.home / ".config/opencode/opencode.json").read_text())
        self.assertEqual("keep/me", config["model"])
        self.assertEqual("ask", config["permission"]["edit"])
        self.assertEqual(0, self.run_sync("--daily").returncode)
        self.assertEqual(calls, (self.home / ".claude/calls").read_text())
        before = {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        again = self.run_sync("--refresh-only")
        self.assertEqual(0, again.returncode, again.stdout + again.stderr)
        self.assertEqual(before, {p.relative_to(self.home): p.read_bytes() for p in self.home.rglob("*") if p.is_file()})
        reference = self.home / ".codex/skills/ui-component-review/references/workflow.md"
        expected = reference.read_text()
        reference.write_text("Manual edit after today's successful sync")
        repaired = self.run_sync("--daily")
        self.assertEqual(0, repaired.returncode, repaired.stdout + repaired.stderr)
        self.assertEqual(expected, reference.read_text())

    def test_plugin_update_failure_leaves_adapters_and_daily_marker_untouched(self):
        self.write(self.plugins / ".workflow-sync-date", "previous successful update")
        self.environment["FAKE_FAIL"] = "17"
        result = self.run_sync()
        self.assertEqual(1, result.returncode)
        self.assertIn("Workflow sync failed", result.stderr)
        self.assertFalse((self.plugins / ".workflow-sync-date").exists())
        self.assertFalse((self.home / ".codex/workflow-migration.json").exists())
        self.environment.pop("FAKE_FAIL")
        self.assertEqual(0, self.run_sync().returncode)

    def test_local_marketplace_pin_is_rejected_before_any_update(self):
        self.write(self.plugins / "known_marketplaces.json", {"jjholmes927-claude-skills": {"source": {"source": "directory", "path": str(self.release)}}})
        result = self.run_sync()
        self.assertEqual(1, result.returncode)
        self.assertIn("published GitHub marketplace", result.stderr)
        self.assertFalse((self.home / ".claude/calls").exists())

    def test_missing_harnesses_are_skipped_and_doctor_failures_propagate(self):
        result = self.run_sync("--refresh-only")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SKIP cursor: not installed", result.stdout)
        self.assertFalse((self.home / ".cursor").exists())
        self.write(self.home / ".codex/beam-migration.json", "broken")
        result = self.run_sync()
        self.assertEqual(1, result.returncode)
        self.assertIn("Workflow drift remains", result.stderr)
        self.assertFalse((self.plugins / ".workflow-sync-date").exists())

    def test_concurrent_sync_cannot_write_adapters(self):
        with (self.plugins / ".workflow-sync.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_sync()
        self.assertEqual(1, result.returncode)
        self.assertFalse((self.home / ".codex/workflow-migration.json").exists())


if __name__ == "__main__":
    unittest.main()
