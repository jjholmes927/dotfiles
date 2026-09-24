import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = runpy.run_path(str(ROOT / "cursor/install.py"))
SHARED = ADAPTER["SHARED"]


class CursorInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / ".cursor"
        self.source = self.root / "personal"
        self.write(self.source / "plugin.json", {"name": "joel-workflow", "version": "2.20.2"})
        self.write(self.source / "scripts/resolve-dev-url.py", "resolver")
        for name, relative in SHARED["COMMANDS"].items():
            self.write(self.source / relative, f'---\ndescription: "Use {name}"\n---\nFull workflow at ${{CLAUDE_PLUGIN_ROOT}}/scripts/tool.py\n')

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict) else content)

    def test_real_cli_installs_cursor_rules_and_complete_sources_then_no_changes(self):
        command = [sys.executable, "-B", str(ROOT / "cursor/install.py"), "--source", str(self.source), "--target", str(self.target)]
        first = subprocess.run(command, text=True, capture_output=True, check=True)
        self.assertGreater(json.loads(first.stdout)["changed"], 0)
        for name, relative in SHARED["COMMANDS"].items():
            directory = self.target / "skills" / name
            self.assertEqual((ROOT / "cursor/compat.md").read_text(), (directory / "compat.md").read_text())
            expected = (self.source / relative).read_text().replace("${CLAUDE_PLUGIN_ROOT}", str(self.source.resolve()))
            self.assertEqual(expected, (directory / "references/workflow.md").read_text())
        again = subprocess.run(command, text=True, capture_output=True, check=True)
        self.assertEqual(0, json.loads(again.stdout)["changed"])

    def test_backups_preserve_symlink_source_and_unrelated_configuration(self):
        original = self.root / "original"
        self.write(original / "SKILL.md", "existing custom skill")
        (self.target / "skills").mkdir(parents=True)
        (self.target / "skills/ship").symlink_to(original)
        preserved = {"mcp.json": "existing MCP", "cli-config.json": "existing model/permissions", "skills/custom/SKILL.md": "custom"}
        for relative, content in preserved.items():
            self.write(self.target / relative, content)
        result = ADAPTER["install"](self.source, self.target)
        self.assertTrue((Path(result["backup"]) / "skills/ship").is_symlink())
        self.assertEqual("existing custom skill", (original / "SKILL.md").read_text())
        for relative, content in preserved.items():
            self.assertEqual(content, (self.target / relative).read_text())

    def test_beam_and_personal_imports_coexist_and_record_both_generators(self):
        ADAPTER["install"](self.source, self.target)
        personal = (self.target / "workflow-migration.json").read_bytes()
        beam = self.root / "beam"
        self.write(beam / ".claude-plugin/plugin.json", {"name": "beam-claude-skills", "version": "1.26.0"})
        for relative in SHARED["PACKAGES"]["beam"]["commands"].values():
            self.write(beam / relative, "---\ndescription: Beam workflow\n---\nKeep full Beam source")
        ADAPTER["install"](beam, self.target, "beam")
        self.assertEqual(personal, (self.target / "workflow-migration.json").read_bytes())
        manifest = json.loads((self.target / "beam-migration.json").read_text())
        self.assertEqual(set(ADAPTER["GENERATORS"]), set(manifest["generator_hashes"]))
        self.assertEqual({"socratic-codebase-interview", "review-pr"}, set(manifest["skills"]))
        self.assertEqual(0, ADAPTER["install"](beam, self.target, "beam")["changed"])

    def test_invalid_source_fails_before_any_live_files_change(self):
        self.write(self.target / "cli-config.json", "preserved")
        (self.source / "skills/e2e/SKILL.md").unlink()
        with self.assertRaises(FileNotFoundError):
            ADAPTER["install"](self.source, self.target)
        self.assertEqual(["cli-config.json"], [p.name for p in self.target.iterdir()])


if __name__ == "__main__":
    unittest.main()
