import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("release", Path(__file__).with_name("install-workflow-release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / ".claude-plugin").mkdir()
        (self.source / "plugin.json").write_text('{"name":"joel-workflow","version":"2.17.0"}')
        (self.source / ".claude-plugin/marketplace.json").write_text(json.dumps({
            "version": "2.17.0", "plugins": [{"name": "joel-workflow", "version": "2.17.0", "source": "remote"}],
        }))
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "add", "."], cwd=self.source, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"], cwd=self.source, check=True)
        self.destination = self.root / "releases"

    def test_snapshot_has_local_metadata_and_retains_committed_source(self):
        snapshot = release.prepare(self.source, self.destination)
        self.assertEqual(snapshot, release.prepare(self.source, self.destination))
        metadata = json.loads((snapshot / "workflow-release.json").read_text())
        self.assertEqual("2.17.0", metadata["version"])
        self.assertEqual("./", json.loads((snapshot / ".claude-plugin/marketplace.json").read_text())["plugins"][0]["source"])
        self.assertEqual("remote", json.loads((self.source / ".claude-plugin/marketplace.json").read_text())["plugins"][0]["source"])
        self.assertEqual((snapshot / "plugin.json").read_bytes(), (snapshot / ".claude-plugin/plugin.json").read_bytes())

    def test_modified_snapshot_is_rejected(self):
        snapshot = release.prepare(self.source, self.destination)
        (snapshot / "plugin.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "Released content changed"):
            release.prepare(self.source, self.destination)

    def test_uncommitted_source_is_rejected(self):
        (self.source / "uncommitted.md").write_text("draft")
        with self.assertRaisesRegex(ValueError, "Commit the workflow source"):
            release.prepare(self.source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_default_config_preserves_normal_cli_state_location(self):
        for custom in [False, True]:
            config = self.root / ("isolated" if custom else ".claude")
            with self.subTest(custom=custom), patch.object(release.Path, "home", return_value=self.root), \
                    patch.dict(release.os.environ, {"CLAUDE_CONFIG_DIR": "inherited"}), \
                    patch.object(release.subprocess, "run") as run, patch("builtins.print"):
                release.install(self.source, config.resolve(), self.destination)
            env = run.call_args.kwargs["env"]
            self.assertEqual(str(config.resolve()) if custom else None, env.get("CLAUDE_CONFIG_DIR"))


if __name__ == "__main__":
    unittest.main()
