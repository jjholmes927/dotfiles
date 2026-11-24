import os
import subprocess
import unittest

from shell_test import REPO, ShellToolCase

ADAPTER = REPO / "magicnotes" / "kandev_worktree_setup.sh"

CREATE_WORKTREE = '''#!/usr/bin/env bash
: WORKTREE_NAME
cat > .env <<'ENV'
WORKTREE_OFFSET=x
PORT=3000
DEV_WEB_PORT=3000
VITE_PORT=3130
WSS_PORT=28080
REDIS_PORT=6379
REDIS_URL=redis://localhost:6379/1
SERVICE_URL=http://localhost:3000
ENV
'''


class WorktreeAdapter(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("lsof")
        self.env["STUB_LSOF_RC"] = "1"
        self.wt = os.path.join(self.root, "tasks", "feat", "repo")
        os.makedirs(os.path.join(self.wt, "bin"))
        self.git("init", "-q", "-b", "main", self.wt)
        script = os.path.join(self.wt, "bin", "create_worktree")
        with open(script, "w") as fh:
            fh.write(CREATE_WORKTREE)
        os.chmod(script, 0o755)

    def sibling(self, port):
        path = os.path.join(self.root, "tasks", "other", "repo")
        os.makedirs(path)
        with open(os.path.join(path, ".env"), "w") as fh:
            fh.write(f"PORT={port}\n")

    def run_adapter(self):
        return subprocess.run(["bash", str(ADAPTER)], cwd=self.wt, env=self.env, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60)

    def env_file(self):
        with open(os.path.join(self.wt, ".env")) as fh:
            return dict(line.split("=", 1) for line in fh.read().splitlines() if "=" in line)

    def assert_slot_one(self):
        self.assertEqual(self.env_file(), {
            "WORKTREE_OFFSET": "kandev-feat", "PORT": "3001", "DEV_WEB_PORT": "3001", "VITE_PORT": "3131",
            "WSS_PORT": "28081", "REDIS_PORT": "6380", "REDIS_URL": "redis://localhost:6380/1",
            "SERVICE_URL": "http://localhost:3001",
        })
        self.assertEqual(sorted(os.listdir(self.wt)), [".env", ".git", "bin"])

    def test_worktree_setup_rewrites_env_with_any_sed(self):
        self.sibling(3002)
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_slot_one()

    def test_first_worktree_with_no_siblings_succeeds(self):
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("kandev-worktree-setup: done", result.stdout)
        self.assert_slot_one()


class HostName(ShellToolCase):
    def test_host_name_on_coder(self):
        result = self.run_tool("agent-host-name", env={"CODER_WORKSPACE_NAME": "x"})
        self.assertEqual(result.stdout, "joel-coder\n")

    def test_host_name_unchanged_off_coder(self):
        self.write_stub("hostname")
        result = self.run_tool("agent-host-name", env={"STUB_HOSTNAME_OUT": "Joel-Holmes-Product-Engineering\n"})
        self.assertEqual(result.stdout, "joel-work-mbp\n")


if __name__ == "__main__":
    unittest.main()
