import glob
import json
import os
import subprocess
import unittest

from shell_test import REPO, ShellToolCase
from prod_data_session_test import GCLOUD_STUB

SESSION = REPO / "coder" / "vertex-session"

PROBE = r'''
import json, os, stat
config = os.environ.get("CLOUDSDK_CONFIG", "")
report = {
    "cwd": os.getcwd(),
    "config": config,
    "config_mode": stat.S_IMODE(os.stat(os.path.dirname(config)).st_mode) if config else None,
    "adc": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    "adc_exists": os.path.exists(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")),
}
with open(os.path.join(os.environ["STUB_LOG_DIR"], "probe.json"), "w") as fh:
    json.dump(report, fh)
'''

OPENCODE_STUB = r'''#!/usr/bin/env python3
import json, os, sys

with open(os.path.join(os.environ["STUB_LOG_DIR"], "opencode.json"), "w") as fh:
    json.dump({"argv": sys.argv[1:], "data": os.environ.get("XDG_DATA_HOME"),
               "adc": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")}, fh)
folder = os.path.join(os.environ["HOME"], ".local", "share", "opencode")
os.makedirs(folder, exist_ok=True)
with open(os.path.join(folder, "opencode.db"), "w") as fh:
    fh.write("chat history")
'''


class VertexSession(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("gcloud", GCLOUD_STUB)
        self.tmp = os.path.join(self.root, "tmp")
        self.work = os.path.join(self.root, "repo")
        os.makedirs(self.tmp)
        os.makedirs(self.work)
        self.env.update({"VERTEX_SESSION_TMP": self.tmp})

    def session(self, *command, **env):
        merged = dict(self.env)
        merged.update(env)
        return subprocess.run([str(SESSION)] + list(command), env=merged, cwd=self.work, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)

    def probe(self, extra=""):
        return ("python3", "-c", PROBE + extra)

    def report(self):
        with open(os.path.join(self.log_dir, "probe.json")) as fh:
            return json.load(fh)

    def gcloud_calls(self):
        return [(c["argv"], c["config"]) for c in self.stub_calls("gcloud")]

    def logins_left(self):
        return glob.glob(os.path.join(self.tmp, "vertex-login.*"))

    def test_runs_command_where_you_are_with_a_private_login(self):
        result = self.session(*self.probe())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.report()
        self.assertEqual(report["cwd"], self.work)
        login = os.path.dirname(report["config"])
        self.assertTrue(os.path.basename(login).startswith("vertex-login."))
        self.assertEqual(os.path.dirname(login), os.path.realpath(self.tmp))
        self.assertEqual(report["config_mode"], 0o700)
        self.assertEqual(report["adc"], os.path.join(report["config"], "application_default_credentials.json"))
        self.assertTrue(report["adc_exists"])
        self.assertIn((["auth", "login", "--no-launch-browser", "--update-adc"], report["config"]), self.gcloud_calls())

    def test_revokes_and_removes_the_login_afterwards(self):
        result = self.session(*self.probe("\nimport sys\nsys.exit(7)\n"))
        self.assertEqual(result.returncode, 7)
        config = self.report()["config"]
        calls = self.gcloud_calls()
        self.assertIn((["auth", "application-default", "revoke", "--quiet"], config), calls)
        self.assertIn((["auth", "revoke", "--all", "--quiet"], config), calls)
        self.assertEqual(self.logins_left(), [])

    def test_failed_login_skips_the_command(self):
        result = self.session(*self.probe(), STUB_GCLOUD_LOGIN_RC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.log_dir, "probe.json")))
        self.assertEqual(self.logins_left(), [])

    def test_opencode_gets_a_private_server_and_keeps_its_history(self):
        self.write_stub("opencode", OPENCODE_STUB)
        result = self.session("sh", "-c", "opencode -s ses_1")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.log_dir, "opencode.json")) as fh:
            seen = json.load(fh)
        self.assertEqual(seen["argv"], ["--standalone", "-s", "ses_1"])
        self.assertIsNone(seen["data"])
        self.assertTrue(seen["adc"].endswith("application_default_credentials.json"))
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "share", "opencode", "opencode.db")))
        self.assertEqual(self.logins_left(), [])

    def test_sweeps_leftover_logins_but_leaves_running_ones(self):
        child = subprocess.Popen(["true"])
        child.wait()
        stale = os.path.join(self.tmp, "vertex-login.STALE1")
        live = os.path.join(self.tmp, "vertex-login.LIVE01")
        for path, pid in ((stale, child.pid), (live, os.getpid())):
            os.makedirs(os.path.join(path, "gcloud"))
            with open(os.path.join(path, "pid"), "w") as fh:
                fh.write("%d\n" % pid)
        result = self.session("true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(live))
        self.assertIn((["auth", "revoke", "--all", "--quiet"], os.path.join(stale, "gcloud")), self.gcloud_calls())

    def test_refuses_an_unknown_command_before_asking_for_a_login(self):
        result = self.session("klaude")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("alias", result.stderr)
        self.assertEqual(self.stub_calls("gcloud"), [])
        self.assertEqual(self.logins_left(), [])


if __name__ == "__main__":
    unittest.main()
