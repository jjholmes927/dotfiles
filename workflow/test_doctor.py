import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import doctor


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.source = self.home / "release-v1"
        self.target = self.home / ".codex"
        self.workflow = self.source / "commands/ship.md"
        self.write(self.workflow, "original source")
        self.generated = self.target / "skills/ship/SKILL.md"
        self.write(self.generated, "generated entry")
        self.identity = "joel-workflow@jjholmes927-claude-skills"
        self.registry = self.home / ".claude/plugins/installed_plugins.json"
        self.select(self.source)
        self.write(self.home / ".claude/settings.json", {"enabledPlugins": {self.identity: True}})
        self.manifest = self.target / "workflow-migration.json"
        self.data = {
            "packages": {"joel-workflow": str(self.source)},
            "skills": {"ship": {"source": str(self.workflow), "sha256": doctor.digest(self.workflow)}},
            "generated_hashes": {"skills/ship/SKILL.md": doctor.digest(self.generated)},
            "generator_hashes": {"codex/sync-workflow.py": doctor.digest(doctor.ROOT / "codex/sync-workflow.py")},
        }
        self.write(self.manifest, self.data)

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict) else content)

    def select(self, source):
        self.write(self.registry, {"plugins": {self.identity: [{"scope": "user", "installPath": str(source)}]}})

    def run_doctor(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = doctor.main(["--home", str(self.home)])
        return code, output.getvalue()

    def test_pinned_healthy_cli_is_read_only(self):
        self.write(self.home / ".claude/plugins/known_marketplaces.json", {"personal": {"source": {"source": "directory", "path": str(self.source)}}})
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", doctor.__file__, "--home", str(self.home)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("PINNED personal", result.stdout)
        self.assertIn("OK codex/personal", result.stdout)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()})

    def test_new_selected_release_warns_even_when_old_cache_survives(self):
        newer = self.home / "release-v2"
        newer.mkdir()
        self.select(newer)
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("selected release changed", output)
        self.assertIn("python3 codex/sync-workflow.py", output)
        self.assertTrue(self.workflow.exists())

    def test_changed_or_missing_inputs_and_outputs_warn(self):
        for path, message in [(self.workflow, "source"), (self.generated, "generated file")]:
            for value in ["edited", None]:
                with self.subTest(path=path, value=value):
                    original = path.read_text()
                    path.unlink() if value is None else path.write_text(value)
                    code, output = self.run_doctor()
                    self.assertEqual(1, code)
                    self.assertIn(message + (" missing" if value is None else " changed"), output)
                    path.write_text(original)

    def test_generator_revision_and_disabled_source_warn(self):
        self.data["generator_hashes"]["codex/sync-workflow.py"] = "older"
        self.write(self.manifest, self.data)
        self.write(self.home / ".claude/settings.json", {"enabledPlugins": {}})
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("adapter generator changed", output)
        self.assertIn("no longer enabled", output)

    def test_legacy_missing_and_malformed_manifests_never_pass(self):
        for content in [{"skills": self.data["skills"]}, "broken", None]:
            with self.subTest(content=content):
                self.manifest.unlink() if content is None else self.write(self.manifest, content)
                code, output = self.run_doctor()
                self.assertEqual(1, code)
                self.assertIn("WARN codex/personal", output)

    def test_partial_opencode_refresh_does_not_certify_untouched_adapters(self):
        installer = runpy.run_path(str(doctor.ROOT / "opencode/install.py"))
        source = self.source
        self.write(source / "plugin.json", {"version": "2.20.1"})
        target = self.home / ".config/opencode"
        other = self.home / "other.md"
        self.write(other, "other source")
        report = {"commands": {"other": str(other)}, "skills": {}, "source_hashes": {str(other): doctor.digest(other)}}
        self.write(target / "migration.json", report)
        other.write_text("source changed after its last import")
        refresh = installer["refresh_workflow"]
        with patch.dict(refresh.__globals__, {"plugins": lambda home: [("joel-workflow", source)]}), contextlib.redirect_stdout(io.StringIO()):
            refresh(self.home, target)
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("incomplete adapter coverage", output)
        self.assertIn("source changed: " + str(other), output)
        self.assertIn("python3 opencode/install.py", output)

    def test_real_codex_import_is_healthy_then_detects_modified_output(self):
        importer = runpy.run_path(str(doctor.ROOT / "codex/sync-workflow.py"))
        self.write(self.source / "plugin.json", {"version": "2.20.2"})
        self.write(self.source / "scripts/resolve-dev-url.py", "resolver")
        for relative in importer["COMMANDS"].values():
            self.write(self.source / relative, "---\ndescription: Fixture workflow\n---\nFull source")
        importer["install"](self.source, self.target)
        self.assertEqual(0, self.run_doctor()[0])
        self.generated.with_name("compat.md").write_text("local change")
        self.assertIn("generated file changed: skills/ship/compat.md", self.run_doctor()[1])

    def test_refresh_registration_preserves_existing_commands(self):
        link = self.home / ".local/bin/workflow-doctor"
        with patch.object(doctor.Path, "home", return_value=self.home), patch.object(doctor, "main", return_value=0), contextlib.redirect_stdout(io.StringIO()):
            doctor.after_refresh()
            self.assertEqual(Path(doctor.__file__).resolve(), link.resolve())
            link.unlink()
            link.write_text("custom command")
            doctor.after_refresh()
            self.assertEqual("custom command", link.read_text())

    def test_full_opencode_import_records_complete_healthy_coverage(self):
        installer = runpy.run_path(str(doctor.ROOT / "opencode/install.py"))["install"]
        target = self.home / ".config/opencode"
        replacements = {"plugins": lambda home: [("joel-workflow", self.source)], "mcp_config": lambda source: ({}, [])}
        with patch.dict(installer.__globals__, replacements), contextlib.redirect_stdout(io.StringIO()):
            installer(self.home, target)
        code, output = self.run_doctor()
        self.assertEqual(0, code, output)
        (target / "commands/ship.md").unlink()
        self.assertIn("generated file missing: commands/ship.md", self.run_doctor()[1])

    def install_cursor(self):
        importer = runpy.run_path(str(doctor.ROOT / "cursor/install.py"))
        self.write(self.source / "plugin.json", {"version": "2.20.3"})
        self.write(self.source / "scripts/resolve-dev-url.py", "resolver")
        for relative in importer["SHARED"]["COMMANDS"].values():
            self.write(self.source / relative, "---\ndescription: Fixture workflow\n---\nFull source")
        return importer, self.home / ".cursor"

    def test_cursor_config_without_managed_skills_is_optional(self):
        self.write(self.home / ".cursor/cli-config.json", {})
        code, output = self.run_doctor()
        self.assertEqual(0, code, output)
        self.assertIn("SKIP cursor/personal", output)
        self.assertIn("SKIP cursor/beam", output)

    def test_real_cursor_import_tracks_source_output_and_generator_changes(self):
        importer, target = self.install_cursor()
        importer["install"](self.source, target)
        self.assertIn("OK cursor/personal", self.run_doctor()[1])
        for relative in ["skills/e2e/compat.md", "skills/e2e/references/workflow.md"]:
            path = target / relative
            original = path.read_text()
            path.unlink()
            code, output = self.run_doctor()
            self.assertEqual(1, code)
            self.assertIn("generated file missing: " + relative, output)
            self.assertIn("python3 cursor/install.py", output)
            path.write_text(original)
        manifest = target / "workflow-migration.json"
        data = json.loads(manifest.read_text())
        data["generator_hashes"]["cursor/compat.md"] = "old"
        self.write(manifest, data)
        self.assertIn("adapter generator changed: cursor/compat.md", self.run_doctor()[1])
        importer["install"](self.source, target)
        newer = self.home / "newer"
        newer.mkdir()
        self.select(newer)
        self.assertIn("WARN cursor/personal", self.run_doctor()[1])

    def test_missing_cursor_manifest_with_surviving_skills_warns(self):
        importer, target = self.install_cursor()
        importer["install"](self.source, target)
        (target / "workflow-migration.json").unlink()
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("WARN cursor/personal", output)

    def test_broken_cursor_skill_link_without_manifest_warns(self):
        link = self.home / ".cursor/skills/ship"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.home / "removed-source")
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("WARN cursor/personal", output)


if __name__ == "__main__":
    unittest.main()
