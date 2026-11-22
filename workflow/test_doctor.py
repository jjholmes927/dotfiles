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

    def test_new_marketplace_skill_cannot_be_hidden_by_an_unmanaged_copy(self):
        self.write(self.source / "skills/new-review/SKILL.md", "New marketplace source")
        self.write(self.target / "skills/new-review/SKILL.md", "Unmanaged local copy")
        code, output = self.run_doctor()
        self.assertEqual(1, code)
        self.assertIn("marketplace skills have no managed adapter: new-review", output)

    def test_shared_instruction_edits_belong_in_marketplace(self):
        guard = runpy.run_path(str(doctor.ROOT / "workflow/check-release.py"))["check_edits"]
        for path in ["codex/skills/shared/SKILL.md", "claude/commands/shared.md"]:
            with patch.object(subprocess, "check_output", return_value=path + "\0"):
                with self.assertRaisesRegex(ValueError, "edit shared instructions"):
                    guard({"shared"}, "base")
        with patch.object(subprocess, "check_output", return_value="codex/skills/shared/compat.md\0claude/commands/style.md\0"):
            guard({"shared"}, "base")

    def test_new_workflows_need_a_deliberate_native_exception_in_every_harness(self):
        guard = runpy.run_path(str(doctor.ROOT / "workflow/check-release.py"))["check_edits"]
        for harness in ["claude", "codex", "cursor", "opencode"]:
            for path in [f"{harness}/skills/new-flow/SKILL.md", f"{harness}/commands/new-flow.md"]:
                with self.subTest(path=path), patch.object(subprocess, "check_output", return_value=path + "\0"):
                    with self.assertRaisesRegex(ValueError, "shared instructions"):
                        guard(set(), "base")

    def test_native_exception_cannot_shadow_a_shared_workflow(self):
        guard = runpy.run_path(str(doctor.ROOT / "workflow/check-release.py"))["check_edits"]
        with patch.object(subprocess, "check_output", return_value="claude/commands/style.md\0"):
            with self.assertRaisesRegex(ValueError, "shared instructions"):
                guard({"style"}, "base")

    def test_referenced_instructions_have_the_same_owner_as_the_skill(self):
        guard = runpy.run_path(str(doctor.ROOT / "workflow/check-release.py"))["check_edits"]
        for harness in ["claude", "codex", "cursor", "opencode"]:
            for name in ["shared", "new-flow"]:
                for document in ["instructions.md", "README.md"]:
                    path = f"{harness}/skills/{name}/references/{document}"
                    with self.subTest(path=path), patch.object(subprocess, "check_output", return_value=path + "\0"):
                        with self.assertRaisesRegex(ValueError, "shared instructions"):
                            guard({"shared"}, "base")

    def test_real_git_diff_rejects_a_new_body_in_a_previously_unchecked_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            self.write(root / "workflow/local-workflows.json", {"claude/commands/native.md": "Uses a native permission-store format"})
            def commit():
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], cwd=root, check=True)
            commit()
            self.write(root / "claude/skills/new-flow-✓/SKILL.md", "A reusable workflow")
            commit()
            guard = runpy.run_path(str(doctor.ROOT / "workflow/check-release.py"))["check_edits"]
            guard.__globals__["ROOT"] = root
            with self.assertRaisesRegex(ValueError, "shared instructions"):
                guard(set(), "HEAD~1")
            (root / "claude/skills/new-flow-✓/SKILL.md").unlink()
            self.write(root / "claude/commands/native.md", "A native workflow")
            commit()
            guard(set(), "HEAD~1")

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
            self.assertEqual(Path(doctor.__file__).resolve().with_name("sync.py"), (self.home / ".local/bin/workflow-sync").resolve())
            link.unlink()
            link.write_text("custom command")
            doctor.after_refresh()
            self.assertEqual("custom command", link.read_text())

    def test_registration_moves_owned_links_from_an_older_checkout(self):
        link = self.home / ".local/bin/workflow-doctor"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.home / "old-checkout/workflow/doctor.py")
        with patch.object(doctor.Path, "home", return_value=self.home), patch.object(doctor, "main", return_value=0):
            doctor.after_refresh()
        self.assertEqual(Path(doctor.__file__).resolve(), link.resolve())

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


class KandevApi:
    def __init__(self, running):
        self.running = running

    def call(self, method, path, body=None, interlock=False):
        if not self.running:
            raise OSError("connection refused")
        if method != "GET":
            raise AssertionError(f"doctor sent {method} {path}")
        return {"workspaces": []}


class KandevDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.conf = Path(self.temporary.name) / "kandev-fleet.json"
        self.conf.write_text(json.dumps({"lanes": [], "linear": {"team": "NEV", "watches": []}}))

    def configure(self, drift=None, running=True):
        def watch_drift(api, conf):
            if isinstance(drift, Exception):
                raise drift
            return drift or []
        configure = {"KANDEV": "http://kandev", "Api": lambda base, timeout: KandevApi(running), "watch_drift": watch_drift}
        return patch.object(doctor, "load_configure", return_value=configure)

    def audit(self, conf=None, **configure):
        with self.configure(**configure):
            return doctor.audit_kandev(conf or self.conf)

    def test_missing_fleet_config_is_skipped(self):
        status, label, _, _ = self.audit(self.conf.with_name("absent.json"))
        self.assertEqual(("SKIP", "kandev"), (status, label))

    def test_stopped_kandev_is_skipped(self):
        status, _, problems, _ = self.audit(running=False)
        self.assertEqual(("SKIP", ["Kandev is not running"]), (status, problems))

    def test_matching_fleet_is_ok(self):
        self.assertEqual("OK", self.audit()[0])

    def test_drift_is_reported_with_the_configure_fix(self):
        status, _, problems, repair = self.audit(drift=["watch agent:implement-codex is missing"])
        self.assertEqual(("DRIFT", ["watch agent:implement-codex is missing"]), (status, problems))
        self.assertIn("python3 kandev/configure.py", repair)

    def test_check_failure_is_drift_not_a_crash(self):
        status, _, problems, _ = self.audit(drift=RuntimeError("workspace 'W' not found"))
        self.assertEqual("DRIFT", status)
        self.assertIn("workspace 'W' not found", problems[0])

    def test_default_loader_finds_the_configure_check(self):
        loaded = doctor.load_configure()
        self.assertTrue(callable(loaded["Api"]) and callable(loaded["watch_drift"]) and loaded["KANDEV"])

    def test_main_reports_kandev_without_a_fleet_config(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            doctor.main(["--home", self.temporary.name])
        self.assertIn("SKIP kandev", output.getvalue())

    def test_kandev_drift_is_printed_but_never_fails_the_doctor(self):
        drift = ("DRIFT", "kandev", ["watch agent:implement-codex is missing"], "fix it")
        with patch.object(doctor, "audit_kandev", return_value=drift), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, doctor.main(["--home", self.temporary.name]))
        self.assertIn("DRIFT kandev\n  watch agent:implement-codex is missing\n  Refresh: fix it", output.getvalue())


class AgentAppDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = Path(self.temporary.name) / ".config"
        self.app = self.config / "jjholmes927-agent/app.json"
        self.app.parent.mkdir(parents=True)
        self.app.write_text(json.dumps({"id": 5878121, "slug": "never-miss-a-bot", "keychain_service": "agent-service"}))
        self.calls = []

    def audit(self, returncode=0, error=None):
        def run(args, **kwargs):
            self.calls.append((args, kwargs))
            if error:
                raise error
            return subprocess.CompletedProcess(args, returncode, b"keychain attributes", b"")
        with patch.object(doctor.subprocess, "run", side_effect=run):
            return doctor.audit_agent_app(self.config)

    def test_machine_without_the_app_is_skipped(self):
        self.app.unlink()
        self.assertEqual(("SKIP", "agent-github-app", ["no agent GitHub app on this machine"], ""), self.audit())
        self.assertEqual([], self.calls)

    def test_app_with_its_keychain_entry_is_ok_without_reading_the_secret(self):
        self.assertEqual(("OK", "agent-github-app", [], ""), self.audit())
        [(args, kwargs)] = self.calls
        self.assertEqual(["security", "find-generic-password", "-s", "agent-service", "-a", "private-key"], args)
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("-w", args)
        self.assertNotIn("-g", args)

    def test_missing_keychain_entry_is_drift_with_the_fix(self):
        for result in [{"returncode": 44}, {"error": FileNotFoundError("security")}]:
            with self.subTest(result=result):
                status, label, problems, repair = self.audit(**result)
                self.assertEqual(("DRIFT", "agent-github-app"), (status, label))
                self.assertIn("no private key in the macOS Keychain (service agent-service", problems[0])
                self.assertIn("security add-generic-password -U -s agent-service -a private-key -w", repair)

    def test_unreadable_app_config_is_drift(self):
        for content in ["broken", json.dumps({"id": 5878121}), json.dumps({"keychain_service": "agent-service"}), "[]"]:
            with self.subTest(content=content):
                self.app.write_text(content)
                status, _, problems, _ = self.audit()
                self.assertEqual("DRIFT", status)
                self.assertIn("cannot read", problems[0])

    def test_main_skips_the_app_on_a_machine_without_it(self):
        self.app.unlink()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            doctor.main(["--home", self.temporary.name])
        self.assertIn("SKIP agent-github-app\n  no agent GitHub app on this machine", output.getvalue())

    def test_app_drift_is_printed_but_never_fails_the_doctor(self):
        drift = ("DRIFT", "agent-github-app", ["no private key in the macOS Keychain"], "store it")
        with patch.object(doctor, "audit_agent_app", return_value=drift), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, doctor.main(["--home", self.temporary.name]))
        self.assertIn("DRIFT agent-github-app\n  no private key in the macOS Keychain\n  Refresh: store it", output.getvalue())


class LspDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.home = base / "home"
        self.plugin = base / "plugin"
        self.plugin.mkdir(parents=True)
        self.repo = base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.track("app/models/user.rb")
        self.identity = "ruby-lsp@official"
        self.write(self.home / ".claude/settings.json", {"enabledPlugins": {self.identity: True}})
        self.write(self.home / ".claude/plugins/installed_plugins.json", {"plugins": {self.identity: [{"scope": "user", "installPath": str(self.plugin)}]}})
        self.server = base / "bin/ruby-lsp"
        self.server_script("echo 0.26.11")

    def write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict) else content)

    def track(self, relative):
        self.write(self.repo / relative, "")
        subprocess.run(["git", "-C", str(self.repo), "add", relative], check=True)

    def server_script(self, body):
        self.write(self.server, f"#!/bin/sh\n{body}\n")
        self.server.chmod(0o755)
        self.write(self.plugin / ".lsp.json", {"ruby-lsp": {"command": str(self.server), "extensionToLanguage": {".rb": "ruby"}}})

    def test_server_that_starts_in_the_repository_is_ok(self):
        self.assertEqual([("OK", "lsp/ruby-lsp", [], "")], doctor.audit_lsp(self.home, self.repo / "app"))

    def test_server_missing_for_the_repository_runtime_is_drift_with_its_install_command(self):
        self.server_script("echo 'rbenv: ruby-lsp: command not found' >&2; exit 127")
        [(status, label, problems, repair)] = doctor.audit_lsp(self.home, self.repo)
        self.assertEqual(("DRIFT", "lsp/ruby-lsp", ["rbenv: ruby-lsp: command not found"]), (status, label, problems))
        self.assertEqual(f"cd {self.repo.resolve()} && gem install ruby-lsp", repair)

    def test_absent_command_is_drift(self):
        self.server.unlink()
        [(status, _, problems, _)] = doctor.audit_lsp(self.home, self.repo)
        self.assertEqual("DRIFT", status)
        self.assertIn("command not found", problems[0])

    def test_server_for_files_the_repository_lacks_is_not_checked(self):
        subprocess.run(["git", "-C", str(self.repo), "rm", "-q", "--cached", "app/models/user.rb"], check=True)
        self.track("script.py")
        self.server_script("exit 1")
        self.assertEqual([("SKIP", "lsp", ["no enabled LSP plugin serves this repository's files"], "")], doctor.audit_lsp(self.home, self.repo))

    def test_disabled_plugin_is_not_checked(self):
        self.write(self.home / ".claude/settings.json", {"enabledPlugins": {self.identity: False}})
        self.assertEqual("SKIP", doctor.audit_lsp(self.home, self.repo)[0][0])

    def test_marketplace_entry_supplies_the_server(self):
        (self.plugin / ".lsp.json").unlink()
        catalog = {"plugins": [{"name": "ruby-lsp", "lspServers": {"ruby-lsp": {"command": str(self.server), "extensionToLanguage": {".rb": "ruby"}}}}]}
        self.write(self.home / ".claude/plugins/marketplaces/official/.claude-plugin/marketplace.json", catalog)
        self.assertEqual("OK", doctor.audit_lsp(self.home, self.repo)[0][0])

    def test_outside_a_git_repository_is_skipped(self):
        outside = Path(self.temporary.name) / "plain"
        outside.mkdir()
        self.assertEqual([("SKIP", "lsp", ["not in a git repository"], "")], doctor.audit_lsp(self.home, outside))

    def test_lsp_drift_is_printed_but_never_fails_the_doctor(self):
        self.server_script("echo 'rbenv: ruby-lsp: command not found' >&2; exit 127")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, doctor.main(["--home", str(self.home), "--repo", str(self.repo)]))
        self.assertIn("DRIFT lsp/ruby-lsp\n  rbenv: ruby-lsp: command not found\n  Refresh: cd ", output.getvalue())


if __name__ == "__main__":
    unittest.main()
