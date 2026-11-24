import os
import subprocess
import unittest

from shell_test import REPO, ShellToolCase

HELPER = REPO / "coder" / "git-credential-coder"
GH_WRAPPER = REPO / "coder" / "gh"

CODER_STUB = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["STUB_LOG_DIR"], "coder.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:]}) + "\n")
print(os.environ.get("CODER_AGENT_TOKEN", "") + "-tok")
'''

REAL_GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["STUB_LOG_DIR"], "gh.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "token": os.environ.get("GH_TOKEN")}) + "\n")
'''

BEAM = "protocol=https\nhost=github.com\npath=wearebeam/magicnotes.git\n"


class CoderCredentials(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("coder", CODER_STUB)
        self.agent_env("one")

    def agent_env(self, token):
        path = os.path.join(self.home, ".config", "coder-setup", "agent.env")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(f"CODER_AGENT_URL=https://coder.example\nCODER_AGENT_TOKEN={token}\n")

    def helper(self, action, stdin="", **env):
        merged = dict(self.env)
        merged.update(env)
        return subprocess.run([str(HELPER), action], input=stdin, env=merged, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60)

    def test_beam_repo_uses_coder_token(self):
        result = self.helper("get", BEAM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "username=x-access-token\npassword=one-tok\n")
        self.assertEqual([c["argv"] for c in self.stub_calls("coder")], [["external-auth", "access-token", "github"]])

    def test_other_host_is_silent(self):
        result = self.helper("get", "protocol=https\nhost=gitlab.com\npath=a/b.git\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.stub_calls("coder"), [])

    def test_agent_env_read_on_every_call(self):
        first = self.helper("get", BEAM, CODER_AGENT_TOKEN="stale")
        self.agent_env("two")
        second = self.helper("get", BEAM, CODER_AGENT_TOKEN="stale")
        self.assertIn("password=one-tok\n", first.stdout)
        self.assertIn("password=two-tok\n", second.stdout)

    def test_store_and_erase_are_noops(self):
        for action in ("store", "erase"):
            result = self.helper(action, BEAM + "username=x\npassword=y\n")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
        self.assertEqual(self.stub_calls("coder"), [])

    def test_gh_wrapper_sets_fresh_token(self):
        local_bin = os.path.join(self.root, "local-bin")
        real_bin = os.path.join(self.root, "real-bin")
        os.makedirs(local_bin)
        os.makedirs(real_bin)
        os.symlink(GH_WRAPPER, os.path.join(local_bin, "gh"))
        real = os.path.join(real_bin, "gh")
        with open(real, "w") as fh:
            fh.write(REAL_GH_STUB)
        os.chmod(real, 0o755)
        env = dict(self.env)
        env["PATH"] = os.pathsep.join([local_bin, self.stub_bin, real_bin, "/usr/bin", "/bin"])
        env["GH_TOKEN"] = "stale"
        result = subprocess.run(["gh", "pr", "list"], env=env, capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stub_calls("gh"), [{"argv": ["pr", "list"], "token": "one-tok"}])


if __name__ == "__main__":
    unittest.main()
