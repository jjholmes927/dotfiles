import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("installer", Path(__file__).with_name("install.py"))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class MigrationTests(unittest.TestCase):
    def test_install_preserves_local_config_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "opencode"
            target.mkdir()
            original = {"model": "provider/model", "permission": {"edit": "ask"},
                        "mcp": {"private": {"type": "remote", "url": "https://example.test/mcp"}}}
            (target / "opencode.json").write_text(json.dumps(original))
            (target / "opencode.jsonc").write_text('// local override\n{"autoupdate": false}\n')
            (target / "AGENTS.md").write_text("Previous instructions\n")
            with patch.object(installer, "plugins", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                installer.install(Path(temporary), target)
                snapshots = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
                installer.install(Path(temporary), target)
            config = json.loads((target / "opencode.json").read_text())
            self.assertEqual(config["model"], original["model"])
            self.assertEqual(config["permission"]["edit"], "ask")
            self.assertIn("private", config["mcp"])
            self.assertEqual(snapshots, {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()})
            backups = list((target / "backups").glob("*/AGENTS.md"))
            self.assertEqual(backups[0].read_text(), "Previous instructions\n")

    def test_replacing_symlink_does_not_modify_its_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_text("original")
            target = root / "opencode"
            target.mkdir()
            (target / "AGENTS.md").symlink_to(source)
            writer = installer.Installer(target)
            writer.write("AGENTS.md", "new")
            self.assertEqual(source.read_text(), "original")
            self.assertFalse((target / "AGENTS.md").is_symlink())
            self.assertTrue((writer.backup / "AGENTS.md").is_symlink())

    def test_mcp_conversion_retains_arguments_and_environment(self):
        servers, notes = installer.mcp_config({
            "remote": {"type": "http", "url": "https://example.test/mcp"},
            "local": {"type": "stdio", "command": "missing-tool", "args": ["mcp", "a b"], "env": {"MODE": "trial"}},
        }, check_local=False)
        self.assertEqual(servers["remote"]["type"], "remote")
        self.assertEqual(servers["local"]["command"], ["missing-tool", "mcp", "a b"])
        self.assertEqual(servers["local"]["environment"], {"MODE": "trial"})
        self.assertEqual(notes, [])
        with patch.object(installer.shutil, "which", return_value=None):
            servers, notes = installer.mcp_config({"local": {"type": "stdio", "command": "missing"}})
        self.assertFalse(servers["local"]["enabled"])
        self.assertTrue(notes)

    def test_wrappers_preserve_source_and_plugin_resource_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "SKILL.md"
            source.write_text('---\nname: example\ndescription: "A useful workflow"\n---\nRun script.')
            result = installer.wrapper("example", source, Path(temporary), skill=True)
            self.assertIn("name: example", result)
            self.assertIn(str(source), result)
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", result)
            self.assertNotIn("Invocation arguments", result)

    def test_plugin_refresh_replaces_only_managed_plugin_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "opencode"
            target.mkdir()
            (target / "opencode.json").write_text(json.dumps({
                "plugin": ["file:///old/superpowers.js", "my-own-plugin"],
                "instructions": ["/chosen/style.md"],
            }))
            (target / "migration.json").write_text(json.dumps({
                "native_plugins": ["file:///old/superpowers.js"],
            }))
            native = root / "superpowers/.opencode/plugins/superpowers.js"
            native.parent.mkdir(parents=True)
            native.write_text("export default {}")
            with patch.object(installer, "plugins", return_value=[("superpowers", root / "superpowers")]), contextlib.redirect_stdout(io.StringIO()):
                installer.install(root, target)
            config = json.loads((target / "opencode.json").read_text())
            self.assertEqual(config["plugin"], ["my-own-plugin", native.as_uri()])
            self.assertIn("/chosen/style.md", config["instructions"])
            self.assertFalse(any("attention-kind" in p for p in config["instructions"]))


if __name__ == "__main__":
    unittest.main()
