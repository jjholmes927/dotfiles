import glob
import json
import os
import re
import subprocess
import unittest

from shell_test import REPO, ShellToolCase

SESSION = REPO / "coder" / "prod-data-session"

GCLOUD_STUB = r'''#!/usr/bin/env python3
import json, os, sys

with open(os.path.join(os.environ["STUB_LOG_DIR"], "gcloud.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "config": os.environ.get("CLOUDSDK_CONFIG")}) + "\n")
if sys.argv[1:3] == ["auth", "login"]:
    rc = int(os.environ.get("STUB_GCLOUD_LOGIN_RC", "0"))
    if rc == 0:
        with open(os.path.join(os.environ["CLOUDSDK_CONFIG"], "application_default_credentials.json"), "w") as fh:
            fh.write("{}")
    sys.exit(rc)
'''

OPENCODE_STUB = r'''#!/usr/bin/env python3
import json, os, sys

with open(os.path.join(os.environ["STUB_LOG_DIR"], "opencode.json"), "w") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(),
               "data": os.environ.get("XDG_DATA_HOME"), "state": os.environ.get("XDG_STATE_HOME"),
               "tmp": os.environ.get("TMPDIR")}, fh)
for key in ("XDG_DATA_HOME", "XDG_STATE_HOME"):
    folder = os.path.join(os.environ[key], "opencode")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "opencode.db"), "w") as fh:
        fh.write("secret transcript")
'''

PROBE = r'''
import json, os, stat, sys
cwd = os.getcwd()
session = os.path.dirname(cwd)
report = {
    "cwd": cwd,
    "session_mode": stat.S_IMODE(os.stat(session).st_mode),
    "adc": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    "config": os.environ.get("CLOUDSDK_CONFIG"),
    "data_dir": os.environ.get("PROD_DATA_DIR"),
    "adc_exists": os.path.exists(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")),
    "xdg_data": os.environ.get("XDG_DATA_HOME"),
    "xdg_state": os.environ.get("XDG_STATE_HOME"),
}
with open(os.path.join(os.environ["STUB_LOG_DIR"], "probe.json"), "w") as fh:
    json.dump(report, fh)
'''


def encode(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path)


class ProdDataSession(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("gcloud", GCLOUD_STUB)
        self.tmp = os.path.join(self.root, "tmp")
        os.makedirs(self.tmp)
        self.env.update({"PROD_DATA_TMP": self.tmp})

    def session(self, *command, **env):
        merged = dict(self.env)
        merged.update(env)
        return subprocess.run([str(SESSION)] + list(command), env=merged, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60, stdin=subprocess.DEVNULL)

    def probe(self, extra=""):
        return ("python3", "-c", PROBE + extra)

    def report(self):
        with open(os.path.join(self.log_dir, "probe.json")) as fh:
            return json.load(fh)

    def gcloud_calls(self):
        return [(c["argv"], c["config"]) for c in self.stub_calls("gcloud")]

    def sessions_left(self):
        return glob.glob(os.path.join(self.tmp, "prod-data.*"))

    def make_session_dir(self, name, pid):
        path = os.path.join(self.tmp, "prod-data." + name)
        os.makedirs(os.path.join(path, "gcloud"))
        os.makedirs(os.path.join(path, "work"))
        with open(os.path.join(path, "pid"), "w") as fh:
            fh.write("%d\n" % pid)
        return path

    def dead_pid(self):
        child = subprocess.Popen(["true"])
        child.wait()
        return child.pid

    def test_runs_command_in_a_private_folder_with_the_session_login(self):
        result = self.session(*self.probe())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.report()
        session = os.path.dirname(report["cwd"])
        self.assertTrue(os.path.basename(session).startswith("prod-data."))
        self.assertEqual(os.path.dirname(session), os.path.realpath(self.tmp))
        self.assertEqual(report["session_mode"], 0o700)
        self.assertEqual(report["data_dir"], report["cwd"])
        self.assertEqual(report["config"], os.path.join(session, "gcloud"))
        self.assertEqual(report["adc"], os.path.join(session, "gcloud", "application_default_credentials.json"))
        self.assertTrue(report["adc_exists"])
        self.assertIn((["auth", "login", "--no-launch-browser", "--update-adc"], report["config"]), self.gcloud_calls())

    def test_revokes_the_login_and_deletes_the_folder_afterwards(self):
        self.session(*self.probe())
        config = self.report()["config"]
        calls = self.gcloud_calls()
        self.assertIn((["auth", "application-default", "revoke", "--quiet"], config), calls)
        self.assertIn((["auth", "revoke", "--all", "--quiet"], config), calls)
        self.assertEqual(self.sessions_left(), [])

    def test_keeps_the_command_exit_code_and_still_cleans_up(self):
        result = self.session(*self.probe("\nsys.exit(7)\n"))
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.sessions_left(), [])
        self.assertIn(["auth", "revoke", "--all", "--quiet"], [argv for argv, _ in self.gcloud_calls()])

    def test_failed_login_skips_the_command_and_cleans_up(self):
        result = self.session(*self.probe(), STUB_GCLOUD_LOGIN_RC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.log_dir, "probe.json")))
        self.assertEqual(self.sessions_left(), [])

    def test_deletes_agent_history_for_the_session_folder(self):
        record = '''
claude = os.path.join(os.environ["HOME"], ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", cwd))
os.makedirs(claude)
open(os.path.join(claude, "chat.jsonl"), "w").write("secret transcript")
codex = os.path.join(os.environ["HOME"], ".codex", "sessions", "2026", "11", "25")
os.makedirs(codex)
open(os.path.join(codex, "rollout-a.jsonl"), "w").write(json.dumps({"cwd": cwd}))
'''
        other_claude = os.path.join(self.home, ".claude", "projects", "-home-coder-engineering-mn1")
        os.makedirs(other_claude)
        other_codex = os.path.join(self.home, ".codex", "sessions", "2026", "11", "24")
        os.makedirs(other_codex)
        with open(os.path.join(other_codex, "rollout-b.jsonl"), "w") as fh:
            fh.write(json.dumps({"cwd": "/home/coder/engineering/mn1"}))
        result = self.session("python3", "-c", "import json, os, re\ncwd = os.getcwd()\n" + record)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.listdir(os.path.join(self.home, ".claude", "projects")), ["-home-coder-engineering-mn1"])
        self.assertFalse(os.path.exists(os.path.join(self.home, ".codex", "sessions", "2026", "11", "25", "rollout-a.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(other_codex, "rollout-b.jsonl")))

    def test_sweeps_leftover_sessions_but_leaves_running_ones(self):
        stale = self.make_session_dir("STALE1", self.dead_pid())
        live = self.make_session_dir("LIVE01", os.getpid())
        projects = os.path.join(self.home, ".claude", "projects")
        real_tmp = os.path.realpath(self.tmp)
        orphan = os.path.join(projects, encode(os.path.join(real_tmp, "prod-data.GONE99", "work")))
        live_chat = os.path.join(projects, encode(os.path.join(real_tmp, "prod-data.LIVE01", "work")))
        os.makedirs(orphan)
        os.makedirs(live_chat)
        codex = os.path.join(self.home, ".codex", "sessions", "2026", "11", "25")
        os.makedirs(codex)
        orphan_codex = os.path.join(codex, "rollout-gone.jsonl")
        live_codex = os.path.join(codex, "rollout-live.jsonl")
        with open(orphan_codex, "w") as fh:
            fh.write(json.dumps({"cwd": os.path.join(real_tmp, "prod-data.GONE99", "work")}))
        with open(live_codex, "w") as fh:
            fh.write(json.dumps({"cwd": os.path.join(real_tmp, "prod-data.LIVE01", "work")}))
        result = self.session("true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(live))
        self.assertFalse(os.path.exists(orphan))
        self.assertTrue(os.path.exists(live_chat))
        self.assertFalse(os.path.exists(orphan_codex))
        self.assertTrue(os.path.exists(live_codex))
        stale_config = os.path.join(real_tmp, "prod-data.STALE1", "gcloud")
        self.assertIn((["auth", "revoke", "--all", "--quiet"], stale_config), self.gcloud_calls())


    def test_finds_the_box_gcloud_when_the_shell_path_is_stale(self):
        sdk_bin = os.path.join(self.home, ".local", "google-cloud-sdk", "bin")
        os.makedirs(sdk_bin)
        os.rename(os.path.join(self.stub_bin, "gcloud"), os.path.join(sdk_bin, "gcloud"))
        result = self.session(*self.probe(), PATH=os.pathsep.join([self.stub_bin, "/usr/bin", "/bin"]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.report()["adc_exists"])

    def test_keeps_opencode_history_inside_the_session_folder(self):
        self.write_stub("opencode", OPENCODE_STUB)
        result = self.session("sh", "-c", "opencode run hi")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.log_dir, "opencode.json")) as fh:
            seen = json.load(fh)
        session = os.path.dirname(seen["cwd"])
        self.assertEqual(seen["argv"], ["run", "hi"])
        self.assertTrue(seen["data"].startswith(session + os.sep), seen)
        self.assertTrue(seen["state"].startswith(session + os.sep), seen)
        self.assertTrue(seen["tmp"].startswith(session + os.sep), seen)
        self.assertEqual(self.sessions_left(), [])
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local", "share", "opencode")))

    def test_leaves_other_tools_on_their_normal_data_folders(self):
        self.write_stub("opencode", OPENCODE_STUB)
        result = self.session(*self.probe())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.report()
        self.assertIsNone(report["xdg_data"])
        self.assertIsNone(report["xdg_state"])

    def test_refuses_an_unknown_command_before_asking_for_a_login(self):
        result = self.session("klaude")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("klaude", result.stderr)
        self.assertIn("alias", result.stderr)
        self.assertEqual(self.stub_calls("gcloud"), [])
        self.assertEqual(self.sessions_left(), [])

if __name__ == "__main__":
    unittest.main()
