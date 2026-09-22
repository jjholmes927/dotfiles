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
        (self.source / "plugin.json").write_text(json.dumps({"version": "2.20.0"}))
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
        self.assertEqual("2.20.0", manifest["plugin_version"])
        self.assertEqual(set(sync.COMMANDS), set(manifest["skills"]))

    def test_older_source_is_rejected_before_writing(self):
        (self.source / "scripts/resolve-dev-url.py").unlink()
        with self.assertRaises(ValueError):
            sync.install(self.source, self.target)
        self.assertFalse(self.target.exists())

    def beam_source(self):
        source = self.root / "beam"
        (source / ".claude-plugin").mkdir(parents=True)
        (source / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "beam-claude-skills", "version": "1.26.0"}))
        workflow = source / "skills/socratic-codebase-interview/SKILL.md"
        workflow.parent.mkdir(parents=True)
        workflow.write_text('---\nname: socratic-codebase-interview\ndescription: Test understanding against source\n---\nAsk one question and wait.\n')
        review = source / "commands/review-pr.md"
        review.parent.mkdir()
        review.write_text('---\ndescription: Review with four lenses\n---\nReport evidence.\n')
        return source

    def test_legacy_e2e_source_is_rejected_before_writing(self):
        (self.source / "plugin.json").write_text('{"version":"2.18.1"}')
        with self.assertRaisesRegex(ValueError, "2.20.0"):
            sync.install(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_beam_import_preserves_personal_skills_and_source(self):
        sync.install(self.source, self.target)
        personal = {p.relative_to(self.target): p.read_bytes() for p in self.target.rglob("*") if p.is_file()}
        source = self.beam_source()
        workflow = source / "skills/socratic-codebase-interview/SKILL.md"
        content = workflow.read_text()
        sync.install(source, self.target, "beam")
        reference = self.target / "skills/socratic-codebase-interview/references/workflow.md"
        self.assertEqual(content, reference.read_text())
        self.assertEqual(content, workflow.read_text())
        for relative, original in personal.items():
            self.assertEqual(original, (self.target / relative).read_bytes())
        manifest = json.loads((self.target / "beam-migration.json").read_text())
        self.assertEqual(str(source.resolve()), manifest["source_root"])
        self.assertEqual({"socratic-codebase-interview", "review-pr"}, set(manifest["skills"]))
        self.assertEqual(sync.REVIEW_COMPAT, (self.target / "skills/review-pr/compat.md").read_text())
        self.assertEqual(0, sync.install(source, self.target, "beam")["changed"])

    def test_optional_beam_source_and_registry_ambiguity(self):
        self.assertIsNone(sync.installed_source(self.root, "beam", optional=True))
        config = self.root / ".claude"
        (config / "plugins").mkdir(parents=True)
        registry = config / "plugins/installed_plugins.json"
        identity = sync.PACKAGES["beam"]["id"]
        entry = {"scope": "user", "installPath": str(self.beam_source())}
        registry.write_text(json.dumps({"plugins": {identity: [entry]}}))
        self.assertIsNone(sync.installed_source(self.root, "beam", optional=True))
        with self.assertRaisesRegex(ValueError, "Enable"):
            sync.installed_source(self.root, "beam")
        (config / "settings.json").write_text(json.dumps({"enabledPlugins": {identity: True}}))
        self.assertEqual(Path(entry["installPath"]), sync.installed_source(self.root, "beam"))
        registry.write_text(json.dumps({"plugins": {identity: [entry, entry]}}))
        with self.assertRaisesRegex(ValueError, "Expected one user installation"):
            sync.installed_source(self.root, "beam", optional=True)

    def test_invalid_beam_source_is_rejected_before_writing(self):
        source = self.beam_source()
        metadata = source / ".claude-plugin/plugin.json"
        metadata.write_text('{"name":"unrelated-plugin","version":"1"}')
        with self.assertRaisesRegex(ValueError, "Expected Beam"):
            sync.install(source, self.target, "beam")
        self.assertFalse(self.target.exists())
        metadata.write_text('{"name":"beam-claude-skills","version":"1.26.0"}')
        (source / "skills/socratic-codebase-interview/SKILL.md").write_text("No description")
        with self.assertRaisesRegex(ValueError, "Missing description"):
            sync.install(source, self.target, "beam")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
