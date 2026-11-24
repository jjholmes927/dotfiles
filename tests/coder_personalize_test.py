import glob
import os
import stat
import subprocess
import time
import unittest

from shell_test import REPO, ShellToolCase

PERSONALIZE = REPO / "coder" / "personalize"

SETUP_STUB = '''#!/bin/sh
echo "$1" >> "$STUB_LOG_DIR/setup.log"
'''


class Personalize(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.origin = self.make_origin("dotfiles", branch="master")
        seed = self.seeds["dotfiles"]
        os.makedirs(os.path.join(seed, "coder"))
        setup = os.path.join(seed, "coder", "setup.sh")
        with open(setup, "w") as fh:
            fh.write(SETUP_STUB)
        os.chmod(setup, 0o755)
        self.git("-C", seed, "add", "-A")
        self.git("-C", seed, "commit", "-q", "-m", "add setup stub")
        self.git("-C", seed, "push", "-q", "origin", "master")
        self.checkout = os.path.join(self.eng, "dotfiles")
        self.state = os.path.join(self.home, ".local", "state", "coder-setup")
        self.env.update({"DOTFILES_DIR": self.checkout, "DOTFILES_URL": self.origin, "CODER_SETUP_STATE": self.state})

    def personalize(self, **env):
        merged = dict(self.env)
        merged.update(env)
        return subprocess.run([str(PERSONALIZE)], env=merged, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120, stdin=subprocess.DEVNULL)

    def setup_calls(self, want=None):
        path = os.path.join(self.log_dir, "setup.log")
        deadline = time.time() + 5
        while True:
            lines = open(path).read().split() if os.path.exists(path) else []
            if want is None or want in lines or time.time() > deadline:
                return lines
            time.sleep(0.1)

    def status(self):
        with open(os.path.join(self.state, "status")) as fh:
            return fh.read()

    def latest_log(self):
        logs = sorted(glob.glob(os.path.join(self.state, "personalize-*.log")), key=os.path.getmtime)
        with open(logs[-1]) as fh:
            return fh.read()

    def head(self):
        return self.git_out("-C", self.checkout, "rev-parse", "HEAD")

    def test_clones_when_missing_and_runs_both_phases(self):
        result = self.personalize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.checkout, ".git")))
        self.assertEqual(self.setup_calls(want="home"), ["system", "home"])
        self.assertTrue(self.status().startswith("system OK "))

    def test_fast_forwards_clean_master(self):
        self.personalize()
        self.push_commit("dotfiles", "next change", branch="master")
        self.personalize()
        self.assertEqual(self.head(), self.git_out("-C", self.seeds["dotfiles"], "rev-parse", "HEAD"))

    def test_skips_pull_when_dirty(self):
        self.personalize()
        before = self.head()
        with open(os.path.join(self.checkout, "scratch.txt"), "w") as fh:
            fh.write("wip\n")
        self.push_commit("dotfiles", "next change", branch="master")
        self.personalize()
        self.assertEqual(self.head(), before)
        self.assertIn("skip pull: dirty", self.latest_log())
        self.assertEqual(self.setup_calls(want="home").count("system"), 2)

    def test_skips_pull_on_branch(self):
        self.personalize()
        self.git("-C", self.checkout, "checkout", "-q", "-b", "x")
        before = self.head()
        self.push_commit("dotfiles", "next change", branch="master")
        self.personalize()
        self.assertEqual(self.head(), before)
        self.assertIn("skip pull: on x", self.latest_log())

    def test_exit_zero_and_fail_status_when_clone_fails(self):
        result = self.personalize(DOTFILES_URL=os.path.join(self.root, "nonexistent"))
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.status().startswith("system FAIL "))

    def test_agent_env_written_private(self):
        self.personalize(CODER_AGENT_TOKEN="t")
        path = os.path.join(self.home, ".config", "coder-setup", "agent.env")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path) as fh:
            self.assertIn("CODER_AGENT_TOKEN=t\n", fh.read())


if __name__ == "__main__":
    unittest.main()
