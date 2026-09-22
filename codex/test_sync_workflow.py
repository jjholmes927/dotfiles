import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location("sync", Path(__file__).with_name("sync-workflow.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class WorkflowInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "release"
        self.source.mkdir()
        (self.source / "plugin.json").write_text(json.dumps({"version": "2.17.0"}))
        (self.source / "scripts").mkdir()
        (self.source / "scripts/resolve-dev-url.py").write_text("resolver")
        for name, relative in sync.COMMANDS.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'---\ndescription: "Run {name}"\n---\nUse ${{CLAUDE_PLUGIN_ROOT}}/scripts/resolve-dev-url.py\n')
        self.target = self.root / "codex"

    def test_replaces_links_without_writing_to_original_and_is_idempotent(self):
        original = self.root / "original"
        original.mkdir()
        (original / "SKILL.md").write_text("original")
        (self.target / "skills").mkdir(parents=True)
        (self.target / "skills/ship").symlink_to(original)
        first = sync.install(self.source, self.target)
        self.assertEqual("original", (original / "SKILL.md").read_text())
        self.assertFalse((self.target / "skills/ship").is_symlink())
        self.assertTrue((Path(first["backup"]) / "skills/ship").is_symlink())
        self.assertEqual(0, sync.install(self.source, self.target)["changed"])

    def test_reference_contains_full_resolved_source_and_provenance(self):
        sync.install(self.source, self.target)
        for name, relative in sync.COMMANDS.items():
            reference = self.target / "skills" / name / "references/workflow.md"
            expected = (self.source / relative).read_text().replace("${CLAUDE_PLUGIN_ROOT}", str(self.source.resolve()))
            self.assertEqual(expected, reference.read_text())
        manifest = json.loads((self.target / "workflow-migration.json").read_text())
        self.assertEqual("2.17.0", manifest["plugin_version"])
        self.assertEqual(set(sync.COMMANDS), set(manifest["skills"]))

    def test_older_source_is_rejected_before_writing(self):
        (self.source / "scripts/resolve-dev-url.py").unlink()
        with self.assertRaises(ValueError):
            sync.install(self.source, self.target)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
