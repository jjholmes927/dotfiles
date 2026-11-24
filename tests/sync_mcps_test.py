import glob
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
SYNC = REPO / "claude" / "sync-mcps.sh"
SENTRY_SCOPED = "https://mcp.sentry.dev/mcp/beam-eu/magic-notes"
LINEAR = {"type": "http", "url": "https://mcp.linear.app/mcp", "headers": {"Authorization": "Bearer k"}}


class SyncMcps(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.home = pathlib.Path(os.path.realpath(holder.name))
        self.overrides = self.home / ".config" / "coder-setup" / "mcp-overrides.json"
        self.env = {"HOME": str(self.home), "PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin"}

    def sync(self):
        result = subprocess.run(["bash", str(SYNC)], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def servers(self):
        return json.loads((self.home / ".claude.json").read_text())["mcpServers"]

    def write_overrides(self):
        self.overrides.parent.mkdir(parents=True)
        self.overrides.write_text(json.dumps({"sentry": {"type": "http", "url": SENTRY_SCOPED}, "linear-server": LINEAR}))

    def test_overrides_win_over_repo_servers(self):
        self.write_overrides()
        self.sync()
        servers = self.servers()
        self.assertEqual(servers["sentry"]["url"], SENTRY_SCOPED)
        self.assertEqual(servers["linear-server"], LINEAR)
        self.assertEqual(servers["honeycomb"]["url"], "https://mcp.eu1.honeycomb.io/mcp")

    def test_second_run_with_overrides_changes_nothing(self):
        self.write_overrides()
        self.sync()
        second = self.sync()
        self.assertIn("already up to date", second.stdout)
        self.assertEqual(glob.glob(str(self.home / ".claude.json.backup-*")), [])

    def test_no_overrides_file_keeps_repo_servers(self):
        self.sync()
        self.assertEqual(self.servers()["sentry"]["url"], "https://mcp.sentry.dev/mcp")
        self.assertNotIn("headers", self.servers()["linear-server"])


if __name__ == "__main__":
    unittest.main()
