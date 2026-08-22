import calendar
import glob
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
BIN = REPO / "bin"

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

LOGGING_STUB = r'''#!/usr/bin/env python3
import json, os, sys

name = os.path.basename(sys.argv[0])
log_dir = os.environ.get("STUB_LOG_DIR")
if log_dir:
    with open(os.path.join(log_dir, name + ".jsonl"), "a") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
key = "STUB_" + name.upper().replace("-", "_")
sub = sys.argv[1] if len(sys.argv) > 1 else ""
sub = "".join(c if c.isalnum() else "_" for c in sub.upper())
out = os.environ.get(key + "_" + sub + "_OUT") if sub else None
if out is None:
    out = os.environ.get(key + "_OUT", "")
sys.stdout.write(out)
sys.exit(int(os.environ.get(key + "_RC", "0")))
'''

CREATE_WORKTREE_STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys

with open(os.path.join(os.environ["STUB_LOG_DIR"], "create_worktree.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
rc = int(os.environ.get("STUB_CREATE_WORKTREE_RC", "0"))
if rc:
    sys.stderr.write("create_worktree: refusing to provision\n")
    sys.exit(rc)
branch = sys.argv[1]
slug = branch[len("jjholmes927-"):] if branch.startswith("jjholmes927-") else branch
dest = os.environ.get("STUB_CREATE_WORKTREE_DEST", ".worktrees/{slug}").format(slug=slug)
subprocess.check_call(["git", "worktree", "add", dest, branch, "--quiet"])
'''

BACKGROUNDED = "backgrounded · deadbeef · dispatched\n"


def flag_value(argv, flag):
    for index, item in enumerate(argv):
        if item == flag and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(flag + "="):
            return item.split("=", 1)[1]
    return None


def agents_json(*rows):
    return json.dumps(list(rows))


def iso_days_ago(days):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))


class ShellToolCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = os.path.realpath(holder.name)
        self.home = os.path.join(self.root, "home")
        self.eng = os.path.join(self.root, "eng")
        self.stub_bin = os.path.join(self.root, "stub-bin")
        self.log_dir = os.path.join(self.root, "logs")
        self.origins = os.path.join(self.root, "origins")
        for path in (self.home, self.eng, self.stub_bin, self.log_dir, self.origins):
            os.makedirs(path, exist_ok=True)
        self.seeds = {}
        self.env = {
            "PATH": os.pathsep.join([self.stub_bin, str(BIN), os.environ.get("PATH", "/usr/bin:/bin")]),
            "HOME": self.home,
            "ENG_ROOT": self.eng,
            "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
            "STUB_LOG_DIR": self.log_dir,
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "TERM": "dumb",
            "LC_ALL": "C",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "SHELL": "/bin/bash",
        }

    def write_stub(self, name, body=LOGGING_STUB):
        path = os.path.join(self.stub_bin, name)
        with open(path, "w") as fh:
            fh.write(body)
        os.chmod(path, 0o755)
        return path

    def stub_calls(self, name):
        path = os.path.join(self.log_dir, name + ".jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [json.loads(line) for line in fh.read().splitlines() if line.strip()]

    def run_tool(self, name, *args, **kwargs):
        path = BIN / name
        if not path.exists():
            raise AssertionError("missing executable: %s (awaiting the bin conversion)" % path)
        if not os.access(str(path), os.X_OK):
            raise AssertionError("not executable: %s" % path)
        env = dict(self.env)
        env.update(kwargs.pop("env", None) or {})
        return subprocess.run(
            [str(path)] + [str(a) for a in args],
            env=env,
            cwd=kwargs.pop("cwd", self.home),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )

    def git(self, *args, **kwargs):
        return subprocess.run(
            ["git"] + [str(a) for a in args],
            env=self.env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=kwargs.pop("check", True),
            timeout=90,
        )

    def git_out(self, *args):
        return self.git(*args).stdout.strip()

    def configure_repo(self, path):
        with open(os.path.join(path, ".git", "config"), "a") as fh:
            fh.write("[user]\n\tname = Lane Tester\n\temail = lane@example.test\n[commit]\n\tgpgsign = false\n")

    def make_origin(self, name, branch="main"):
        origin = os.path.join(self.origins, name + ".git")
        seed = os.path.join(self.origins, name + "-seed")
        self.git("init", "--bare", "-b", branch, origin)
        self.git("init", "-b", branch, seed)
        self.configure_repo(seed)
        with open(os.path.join(seed, "README.md"), "w") as fh:
            fh.write("seed\n")
        self.git("-C", seed, "add", "-A")
        self.git("-C", seed, "commit", "-m", "seed commit")
        self.git("-C", seed, "remote", "add", "origin", origin)
        self.git("-C", seed, "push", "-u", "origin", branch)
        self.seeds[name] = seed
        return origin

    def clone_lane(self, name, branch="main"):
        origin = os.path.join(self.origins, name + ".git")
        lane = os.path.join(self.eng, name)
        self.git("clone", origin, lane)
        self.configure_repo(lane)
        self.git("-C", lane, "remote", "set-head", "origin", branch)
        return lane

    def make_lane(self, name, branch="main"):
        self.make_origin(name, branch)
        return self.clone_lane(name, branch)

    def push_commit(self, name, message, branch="main"):
        seed = self.seeds[name]
        with open(os.path.join(seed, message.replace(" ", "-") + ".txt"), "w") as fh:
            fh.write(message + "\n")
        self.git("-C", seed, "add", "-A")
        self.git("-C", seed, "commit", "-m", message)
        self.git("-C", seed, "push", "origin", branch)
        return self.git_out("-C", seed, "rev-parse", branch)

    def push_branch(self, name, branch, message, base="main"):
        seed = self.seeds[name]
        self.git("-C", seed, "checkout", "-b", branch)
        sha = self.push_commit(name, message, branch)
        self.git("-C", seed, "checkout", base)
        return sha

    def branch_list(self, lane, pattern):
        out = self.git("-C", lane, "branch", "--list", pattern).stdout.splitlines()
        return [line[2:].split(" ")[0] for line in out if line.strip()]

    def dirty(self, lane):
        with open(os.path.join(lane, "README.md"), "w") as fh:
            fh.write("dirty\n")
        with open(os.path.join(lane, "untracked.txt"), "w") as fh:
            fh.write("scratch\n")


class FleetStatus(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_OUT"] = BACKGROUNDED
        self.session = "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
        self.short = "1a2b3c4d"
        self.env["CLAUDE_CODE_SESSION_ID"] = self.session

    def sidecar_dir(self):
        return os.path.join(self.home, ".claude", "fleet-status")

    def sidecar(self, session=None):
        with open(os.path.join(self.sidecar_dir(), session or self.session)) as fh:
            return fh.read()

    def test_no_arguments_is_usage(self):
        result = self.run_tool("fleet-status")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_one_positional_is_usage(self):
        result = self.run_tool("fleet-status", "complete")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_three_positionals_is_usage(self):
        result = self.run_tool("fleet-status", "complete", "one", "two")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_bad_state_is_rejected(self):
        result = self.run_tool("fleet-status", "finished", "note")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad state: finished", result.stderr)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_unknown_flag_is_rejected(self):
        result = self.run_tool("fleet-status", "--loud", "complete", "note")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown flag: --loud", result.stderr)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_both_session_vars_unset_names_the_env_var(self):
        del self.env["CLAUDE_CODE_SESSION_ID"]
        result = self.run_tool("fleet-status", "complete", "note")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no session id: $CLAUDE_CODE_SESSION_ID unset and no --session given", result.stderr)

    def test_primary_env_var_wins_over_legacy(self):
        self.env["CLAUDE_SESSION_ID"] = "legacy-session"
        result = self.run_tool("fleet-status", "complete", "note")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(sorted(os.listdir(self.sidecar_dir())), [self.session])

    def test_legacy_env_var_is_the_fallback(self):
        del self.env["CLAUDE_CODE_SESSION_ID"]
        self.env["CLAUDE_SESSION_ID"] = "legacy-session"
        result = self.run_tool("fleet-status", "complete", "note")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(sorted(os.listdir(self.sidecar_dir())), ["legacy-session"])

    def test_session_flag_equals_form_overrides_env(self):
        result = self.run_tool("fleet-status", "complete", "note", "--session=chosen-one")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(sorted(os.listdir(self.sidecar_dir())), ["chosen-one"])

    def test_session_flag_space_form_overrides_env(self):
        result = self.run_tool("fleet-status", "--session", "chosen-two", "complete", "note")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(sorted(os.listdir(self.sidecar_dir())), ["chosen-two"])

    def test_session_flag_without_a_value_is_usage(self):
        result = self.run_tool("fleet-status", "complete", "note", "--session")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: fleet-status complete|awaiting", result.stderr)

    def test_double_dash_drains_the_rest_as_positionals(self):
        result = self.run_tool("fleet-status", "complete", "--", "--stop")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.sidecar().rstrip("\n").split("\t")[2], "--stop")
        self.assertNotIn("stop requested", result.stdout)
        self.assertEqual(self.stub_calls("claude"), [])

    def test_traversal_session_id_is_rejected(self):
        result = self.run_tool("fleet-status", "complete", "note", "--session=../evil")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad session id: ../evil", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "evil")))

    def test_dot_session_id_is_rejected(self):
        result = self.run_tool("fleet-status", "complete", "note", "--session=.")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad session id: .", result.stderr)

    def test_nested_session_id_is_rejected(self):
        result = self.run_tool("fleet-status", "complete", "note", "--session=a/b")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad session id: a/b", result.stderr)

    def test_note_control_characters_are_flattened(self):
        result = self.run_tool("fleet-status", "awaiting", "line one\ttwo\nthree\rfour")
        self.assertEqual(result.returncode, 0)
        body = self.sidecar()
        self.assertEqual(body.count("\n"), 1)
        self.assertEqual(body.rstrip("\n").split("\t")[2], "line one two three four")

    def test_sidecar_is_one_tsv_line_with_a_utc_timestamp(self):
        result = self.run_tool("fleet-status", "complete", "shipped PR #17")
        self.assertEqual(result.returncode, 0)
        lines = self.sidecar().splitlines()
        self.assertEqual(len(lines), 1)
        fields = lines[0].split("\t")
        self.assertEqual(len(fields), 3)
        self.assertEqual(fields[0], "complete")
        self.assertRegex(fields[1], TIMESTAMP)
        self.assertEqual(fields[2], "shipped PR #17")
        stamped = calendar.timegm(time.strptime(fields[1], "%Y-%m-%dT%H:%M:%SZ"))
        self.assertLess(abs(stamped - time.time()), 300)

    def test_awaiting_state_is_accepted(self):
        result = self.run_tool("fleet-status", "awaiting", "needs a decision")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.sidecar().split("\t")[0], "awaiting")

    def test_last_write_wins(self):
        self.run_tool("fleet-status", "awaiting", "first note")
        self.run_tool("fleet-status", "complete", "second note")
        lines = self.sidecar().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].split("\t")[0], "complete")
        self.assertEqual(lines[0].split("\t")[2], "second note")

    def test_write_leaves_no_temp_file(self):
        self.run_tool("fleet-status", "complete", "note")
        self.assertEqual(sorted(os.listdir(self.sidecar_dir())), [self.session])

    def test_confirmation_line_uses_the_short_id(self):
        result = self.run_tool("fleet-status", "complete", "note")
        self.assertIn("fleet-status: complete recorded for %s" % self.short, result.stdout)

    def test_stop_calls_claude_with_the_short_id(self):
        result = self.run_tool("fleet-status", "complete", "note", "--stop")
        self.assertEqual(result.returncode, 0)
        self.assertEqual([call["argv"] for call in self.stub_calls("claude")], [["stop", self.short]])
        self.assertIn("fleet-status: stop requested for %s" % self.short, result.stdout)

    def test_stop_failure_is_tolerated(self):
        self.env["STUB_CLAUDE_RC"] = "3"
        result = self.run_tool("fleet-status", "complete", "note", "--stop")
        self.assertEqual(result.returncode, 0)
        self.assertIn("fleet-status: stop requested for %s" % self.short, result.stdout)


class NewAgentArguments(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_OUT"] = BACKGROUNDED

    def test_no_arguments_is_usage(self):
        result = self.run_tool("new-agent")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: new-agent", result.stderr)

    def test_lane_without_prompt_is_usage(self):
        self.make_lane("mn1")
        result = self.run_tool("new-agent", "mn1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: new-agent", result.stderr)

    def test_unknown_flag_is_rejected(self):
        result = self.run_tool("new-agent", "-x", "mn1", "do the thing")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown flag: -x", result.stderr)

    def test_bad_effort_is_rejected(self):
        result = self.run_tool("new-agent", "mn1", "--effort", "turbo", "do the thing")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad --effort: turbo", result.stderr)

    def test_missing_lane_is_reported(self):
        result = self.run_tool("new-agent", "ghost", "do the thing")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no such lane: ghost", result.stderr)

    def test_no_dispatch_happens_on_a_bad_invocation(self):
        self.run_tool("new-agent", "ghost", "do the thing")
        self.assertEqual(self.stub_calls("claude"), [])


class NewAgentWithBranch(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_OUT"] = BACKGROUNDED

    def dispatch(self):
        calls = [call for call in self.stub_calls("claude") if "--bg" in call["argv"]]
        self.assertEqual(len(calls), 1)
        return calls[0]

    def test_branch_is_created_from_fresh_origin_default(self):
        lane = self.make_lane("mn1")
        ahead = self.push_commit("mn1", "second commit")
        result = self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one", "two", "three")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.git_out("-C", lane, "rev-parse", "jjholmes927-add-thing"), ahead)

    def test_worktree_lands_under_the_slug_without_the_prefix(self):
        lane = self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one two three")
        worktree = os.path.join(lane, ".worktrees", "add-thing")
        self.assertTrue(os.path.isdir(worktree))
        self.assertEqual(self.git_out("-C", worktree, "rev-parse", "--abbrev-ref", "HEAD"), "jjholmes927-add-thing")

    def test_dispatch_argv_carries_the_defaults(self):
        lane = self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one", "two", "three")
        call = self.dispatch()
        self.assertEqual(call["cwd"], os.path.join(lane, ".worktrees", "add-thing"))
        self.assertIn("--bg", call["argv"])
        self.assertEqual(flag_value(call["argv"], "--name"), "add-thing")
        self.assertEqual(flag_value(call["argv"], "--effort"), "high")
        self.assertEqual(flag_value(call["argv"], "--permission-mode"), "bypassPermissions")

    def test_prompt_words_are_joined_and_carry_only_the_status_note(self):
        self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one", "two", "three")
        prompt = self.dispatch()["argv"][-1]
        self.assertTrue(prompt.startswith("one two three"))
        self.assertIn("fleet-status complete", prompt)
        self.assertTrue(prompt.endswith("never via a subagent."))
        self.assertNotIn("Workspace note", prompt)

    def test_existing_remote_branch_is_used_as_is(self):
        self.make_origin("mn1")
        sha = self.push_branch("mn1", "jjholmes927-remote-thing", "remote work")
        lane = self.clone_lane("mn1")
        result = self.run_tool("new-agent", "mn1", "jjholmes927-remote-thing", "carry on")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.git_out("-C", lane, "rev-parse", "jjholmes927-remote-thing"), sha)
        self.assertEqual(flag_value(self.dispatch()["argv"], "--name"), "remote-thing")

    def test_existing_local_branch_is_not_moved(self):
        lane = self.make_lane("mn1")
        self.git("-C", lane, "branch", "jjholmes927-local-thing")
        sha = self.git_out("-C", lane, "rev-parse", "jjholmes927-local-thing")
        self.push_commit("mn1", "second commit")
        result = self.run_tool("new-agent", "mn1", "jjholmes927-local-thing", "carry on")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.git_out("-C", lane, "rev-parse", "jjholmes927-local-thing"), sha)

    def test_existing_worktree_path_is_refused(self):
        lane = self.make_lane("mn1")
        os.makedirs(os.path.join(lane, ".worktrees", "add-thing"))
        result = self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one two three")
        self.assertEqual(result.returncode, 1)
        self.assertIn("worktree already exists", result.stderr)
        self.assertEqual(self.stub_calls("claude"), [])

    def test_effort_space_form(self):
        self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "--effort", "low", "one two three")
        self.assertEqual(flag_value(self.dispatch()["argv"], "--effort"), "low")

    def test_effort_equals_form(self):
        self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "--effort=low", "one two three")
        self.assertEqual(flag_value(self.dispatch()["argv"], "--effort"), "low")

    def test_safe_drops_to_auto_mode(self):
        self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "--safe", "one two three")
        self.assertEqual(flag_value(self.dispatch()["argv"], "--permission-mode"), "auto")

    def test_perm_sets_any_other_mode(self):
        self.make_lane("mn1")
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "--perm=plan", "one two three")
        self.assertEqual(flag_value(self.dispatch()["argv"], "--permission-mode"), "plan")


class NewAgentWithoutBranch(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_OUT"] = BACKGROUNDED
        self.lane = self.make_lane("mn1")

    def dispatch(self):
        calls = [call for call in self.stub_calls("claude") if "--bg" in call["argv"]]
        self.assertEqual(len(calls), 1)
        return calls[0]

    def worktrees(self):
        return sorted(glob.glob(os.path.join(self.lane, ".worktrees", "*")))

    def test_worktree_is_detached_on_fresh_origin_default(self):
        ahead = self.push_commit("mn1", "second commit")
        result = self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertEqual(result.returncode, 0)
        made = self.worktrees()
        self.assertEqual(len(made), 1)
        self.assertRegex(os.path.basename(made[0]), r"^fix-the-flaky-login-spec-on-staging-\d{6}$")
        self.assertEqual(self.git_out("-C", made[0], "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")
        self.assertEqual(self.git_out("-C", made[0], "rev-parse", "HEAD"), ahead)

    def test_no_branch_is_created(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertEqual(self.branch_list(self.lane, "jjholmes927-*"), [])

    def test_name_is_lane_plus_four_slug_words(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertEqual(flag_value(self.dispatch()["argv"], "--name"), "mn1/fix-the-flaky-login")

    def test_name_is_capped_at_thirty_characters(self):
        self.run_tool("new-agent", "mn1", "Investigate flaky authentication timeouts in staging")
        name = flag_value(self.dispatch()["argv"], "--name")
        self.assertEqual(name, "mn1/investigate-flaky-authenti")
        self.assertEqual(len(name), 30)

    def test_prompt_carries_both_notes_in_order(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        prompt = self.dispatch()["argv"][-1]
        self.assertTrue(prompt.startswith("Fix the flaky login spec on staging"))
        self.assertIn("Workspace note: you are already inside a dedicated git worktree.", prompt)
        self.assertIn("jjholmes927-<slug>", prompt)
        self.assertIn("fleet-status complete", prompt)
        self.assertLess(prompt.index("Workspace note"), prompt.index("fleet-status complete"))
        self.assertTrue(prompt.endswith("never via a subagent."))

    def test_dispatch_runs_inside_the_new_worktree(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertEqual(self.dispatch()["cwd"], self.worktrees()[0])


class NewAgentCreateWorktree(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_OUT"] = BACKGROUNDED
        self.lane = self.make_lane("mn1")
        os.makedirs(os.path.join(self.lane, "bin"), exist_ok=True)
        hook = os.path.join(self.lane, "bin", "create_worktree")
        with open(hook, "w") as fh:
            fh.write(CREATE_WORKTREE_STUB)
        os.chmod(hook, 0o755)

    def dispatch(self):
        calls = [call for call in self.stub_calls("claude") if "--bg" in call["argv"]]
        self.assertEqual(len(calls), 1)
        return calls[0]

    def provisional(self):
        calls = self.stub_calls("create_worktree")
        self.assertEqual(len(calls), 1)
        return calls[0]

    def test_provisional_branch_is_passed_when_no_branch_given(self):
        result = self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertEqual(result.returncode, 0)
        call = self.provisional()
        self.assertEqual(call["cwd"], self.lane)
        self.assertRegex(call["argv"][0], r"^jjholmes927-fix-the-flaky-login-spec-on-staging-\d{6}$")

    def test_provisional_branch_is_based_on_fresh_origin_default(self):
        ahead = self.push_commit("mn1", "second commit")
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        branch = self.provisional()["argv"][0]
        self.assertEqual(self.git_out("-C", self.lane, "rev-parse", branch), ahead)

    def test_worktree_is_checked_out_on_the_provisional_branch(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        branch = self.provisional()["argv"][0]
        worktree = os.path.join(self.lane, ".worktrees", branch[len("jjholmes927-"):])
        self.assertTrue(os.path.isdir(worktree))
        self.assertEqual(self.git_out("-C", worktree, "rev-parse", "--abbrev-ref", "HEAD"), branch)
        self.assertEqual(self.dispatch()["cwd"], worktree)

    def test_branch_note_is_still_appended_for_a_provisional_branch(self):
        self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        prompt = self.dispatch()["argv"][-1]
        self.assertIn("Workspace note: you are already inside a dedicated git worktree.", prompt)
        self.assertIn("already on a provisional branch", prompt)

    def test_given_branch_is_passed_through_untouched(self):
        result = self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one two three")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.provisional()["argv"], ["jjholmes927-add-thing"])
        self.assertEqual(self.branch_list(self.lane, "jjholmes927-*"), ["jjholmes927-add-thing"])
        self.assertEqual(self.dispatch()["cwd"], os.path.join(self.lane, ".worktrees", "add-thing"))

    def test_worktree_made_elsewhere_is_discovered(self):
        self.env["STUB_CREATE_WORKTREE_DEST"] = "provisioned/{slug}"
        self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one two three")
        self.assertEqual(self.dispatch()["cwd"], os.path.join(self.lane, "provisioned", "add-thing"))

    def test_failure_deletes_the_pre_created_branch(self):
        self.env["STUB_CREATE_WORKTREE_RC"] = "1"
        result = self.run_tool("new-agent", "mn1", "Fix the flaky login spec on staging")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.branch_list(self.lane, "jjholmes927-*"), [])
        self.assertEqual([c for c in self.stub_calls("claude") if "--bg" in c["argv"]], [])

    def test_failure_with_a_given_branch_deletes_it_too(self):
        self.env["STUB_CREATE_WORKTREE_RC"] = "1"
        result = self.run_tool("new-agent", "mn1", "jjholmes927-add-thing", "one two three")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.branch_list(self.lane, "jjholmes927-*"), [])


class LaneSweep(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_AGENTS_OUT"] = "[]"
        self.lane = self.make_lane("mn1")

    def swept(self):
        return sorted(os.path.basename(p) for p in glob.glob(os.path.join(self.lane, ".worktrees", "*")))

    def test_missing_lane_is_reported(self):
        result = self.run_tool("lane-sweep", "ghost")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no such lane: ghost", result.stderr)

    def test_clean_lane_on_default_branch_is_a_noop(self):
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(os.path.isdir(os.path.join(self.lane, ".worktrees")))

    def test_clean_lane_survives_a_missing_claude(self):
        self.env["STUB_CLAUDE_RC"] = "127"
        self.env["STUB_CLAUDE_AGENTS_OUT"] = ""
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_dirty_lane_moves_wip_onto_a_sweep_branch(self):
        self.dirty(self.lane)
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("mn1: WIP moved to .worktrees/jjholmes927-lane-sweep-mn1-", result.stdout)
        made = self.swept()
        self.assertEqual(len(made), 1)
        self.assertRegex(made[0], r"^jjholmes927-lane-sweep-mn1-\d{8}$")

    def test_dirty_lane_root_returns_clean_on_the_default_branch(self):
        self.dirty(self.lane)
        self.run_tool("lane-sweep", "mn1")
        self.assertEqual(self.git_out("-C", self.lane, "branch", "--show-current"), "main")
        self.assertEqual(self.git_out("-C", self.lane, "status", "--porcelain", "-uno"), "")
        with open(os.path.join(self.lane, "README.md")) as fh:
            self.assertEqual(fh.read(), "seed\n")

    def test_wip_lands_in_the_new_worktree(self):
        self.dirty(self.lane)
        self.run_tool("lane-sweep", "mn1")
        worktree = os.path.join(self.lane, ".worktrees", self.swept()[0])
        with open(os.path.join(worktree, "README.md")) as fh:
            self.assertEqual(fh.read(), "dirty\n")
        self.assertTrue(os.path.exists(os.path.join(worktree, "untracked.txt")))

    def test_parked_clean_branch_is_moved_to_a_worktree(self):
        self.git("-C", self.lane, "checkout", "-b", "jjholmes927-parked", "--quiet")
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("mn1: parked branch moved to .worktrees/jjholmes927-parked", result.stdout)
        self.assertEqual(self.git_out("-C", self.lane, "branch", "--show-current"), "main")
        self.assertEqual(self.swept(), ["jjholmes927-parked"])

    def test_live_session_in_the_lane_root_skips(self):
        self.dirty(self.lane)
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "a" * 36, "kind": "interactive", "cwd": self.lane, "name": "hands on"}
        )
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SKIP mn1: live claude session in lane root", result.stderr)
        self.assertNotEqual(self.git_out("-C", self.lane, "status", "--porcelain"), "")
        self.assertFalse(os.path.isdir(os.path.join(self.lane, ".worktrees")))

    def test_background_session_in_the_lane_root_does_not_skip(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "b" * 36, "kind": "background", "cwd": self.lane, "name": "stream"}
        )
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)

    def test_live_session_elsewhere_does_not_skip(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "c" * 36, "kind": "interactive", "cwd": os.path.join(self.eng, "mn9"), "name": "other"}
        )
        result = self.run_tool("lane-sweep", "mn1")
        self.assertEqual(result.returncode, 0)


class GmpAll(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_AGENTS_OUT"] = "[]"

    def test_clean_lane_fast_forwards(self):
        lane = self.make_lane("mn1")
        ahead = self.push_commit("mn1", "second commit")
        self.env["LANES"] = "mn1"
        result = self.run_tool("gmp-all")
        self.assertEqual(result.returncode, 0)
        self.assertIn("mn1: main @ ", result.stdout)
        self.assertIn("second commit", result.stdout)
        self.assertEqual(self.git_out("-C", lane, "rev-parse", "HEAD"), ahead)

    def test_missing_lane_directories_are_ignored(self):
        self.make_lane("mn1")
        self.push_commit("mn1", "second commit")
        self.env["LANES"] = "mn1 ghost"
        result = self.run_tool("gmp-all")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("ghost", result.stdout)
        self.assertNotIn("ghost", result.stderr)

    def test_dirty_lane_with_a_live_session_is_skipped(self):
        self.make_lane("mn1")
        self.push_commit("mn1", "second commit")
        lane2 = self.make_lane("mn2")
        self.dirty(lane2)
        self.env["LANES"] = "mn1 mn2"
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "a" * 36, "kind": "interactive", "cwd": lane2, "name": "hands on"}
        )
        result = self.run_tool("gmp-all")
        self.assertIn("mn1: main @ ", result.stdout)
        self.assertIn("SKIP mn2: needs sweep but a live session is in the lane root", result.stdout)
        self.assertNotEqual(self.git_out("-C", lane2, "status", "--porcelain"), "")

    def test_dirty_lane_without_a_live_session_is_swept_then_pulled(self):
        lane = self.make_lane("mn1")
        ahead = self.push_commit("mn1", "second commit")
        self.dirty(lane)
        self.env["LANES"] = "mn1"
        result = self.run_tool("gmp-all")
        self.assertIn("mn1: WIP moved to .worktrees/jjholmes927-lane-sweep-mn1-", result.stdout)
        self.assertIn("mn1: main @ ", result.stdout)
        self.assertEqual(self.git_out("-C", lane, "rev-parse", "HEAD"), ahead)


class CloneStatus(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.env["STUB_CLAUDE_AGENTS_OUT"] = "[]"

    def row(self, stdout, lane):
        for line in stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == lane:
                return fields
        return []

    def test_header_names_every_column(self):
        self.make_lane("mn1")
        self.env["LANES"] = "mn1"
        result = self.run_tool("clone-status")
        self.assertEqual(result.returncode, 0)
        header = result.stdout.splitlines()[0]
        for column in ("LANE", "BRANCH", "DIRTY", "BEHIND", "WTS", "LIVE"):
            self.assertIn(column, header)

    def test_one_row_per_lane(self):
        self.make_lane("mn1")
        self.make_lane("mn2")
        self.env["LANES"] = "mn1 mn2"
        result = self.run_tool("clone-status")
        self.assertEqual(self.row(result.stdout, "mn1")[:2], ["mn1", "main"])
        self.assertEqual(self.row(result.stdout, "mn2")[:2], ["mn2", "main"])
        self.assertEqual(len(self.row(result.stdout, "mn1")), 6)

    def test_behind_count_shows_after_a_fetch(self):
        self.make_lane("mn1")
        self.push_commit("mn1", "second commit")
        self.env["LANES"] = "mn1"
        result = self.run_tool("clone-status")
        self.assertIn("1", self.row(result.stdout, "mn1")[2:])

    def test_missing_lane_directories_are_ignored(self):
        self.make_lane("mn1")
        self.env["LANES"] = "mn1 ghost"
        result = self.run_tool("clone-status")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.row(result.stdout, "ghost"), [])


class ClosureSweep(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.write_stub("gh")
        self.env["CLOSURE_REPOS"] = "acme/repo"
        self.env["STUB_GH_PR_OUT"] = "[]"
        self.env["STUB_CLAUDE_AGENTS_OUT"] = "[]"

    def pr(self, **overrides):
        row = {
            "number": 42,
            "title": "Fix the flaky thing",
            "updatedAt": iso_days_ago(3),
            "mergeable": "MERGEABLE",
            "isDraft": False,
        }
        row.update(overrides)
        self.env["STUB_GH_PR_OUT"] = json.dumps([row])

    def test_empty_stubs_produce_a_clean_sweep(self):
        result = self.run_tool("closure-sweep")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("── closure sweep "))
        self.assertIn("every line above needs a next action", result.stdout)
        self.assertNotIn("[RED]", result.stdout)
        self.assertNotIn("[AMB]", result.stdout)

    def test_gh_is_asked_for_the_configured_repo(self):
        self.run_tool("closure-sweep")
        calls = self.stub_calls("gh")
        self.assertEqual(len(calls), 1)
        self.assertIn("acme/repo", calls[0]["argv"])

    def test_conflicting_pr_older_than_a_day_is_red(self):
        self.pr(mergeable="CONFLICTING")
        result = self.run_tool("closure-sweep")
        self.assertEqual(result.returncode, 0)
        self.assertIn("[RED] CONFLICTING", result.stdout)
        self.assertIn("acme/repo#42", result.stdout)
        self.assertIn("Fix the flaky thing", result.stdout)

    def test_quiet_open_pr_older_than_two_days_is_amber(self):
        self.pr(number=43, title="Quiet one")
        result = self.run_tool("closure-sweep")
        self.assertIn("[AMB] quiet", result.stdout)
        self.assertIn("acme/repo#43", result.stdout)

    def test_fresh_pr_is_silent(self):
        self.pr(updatedAt=iso_days_ago(0))
        result = self.run_tool("closure-sweep")
        self.assertNotIn("[AMB]", result.stdout)
        self.assertNotIn("[RED]", result.stdout)

    def test_young_draft_is_silent(self):
        self.pr(isDraft=True)
        result = self.run_tool("closure-sweep")
        self.assertNotIn("[AMB]", result.stdout)
        self.assertNotIn("[RED]", result.stdout)

    def test_blocked_background_stream_is_red(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {
                "sessionId": "a" * 36,
                "kind": "background",
                "state": "blocked",
                "name": "mn1/thing",
                "waitingFor": "permission",
                "cwd": "/eng/mn1",
            }
        )
        result = self.run_tool("closure-sweep")
        self.assertIn("[RED] blocked stream", result.stdout)
        self.assertIn("mn1/thing", result.stdout)
        self.assertIn("waiting: permission", result.stdout)

    def test_gh_failure_does_not_abort_the_sweep(self):
        self.env["STUB_GH_RC"] = "1"
        self.env["STUB_GH_PR_OUT"] = ""
        result = self.run_tool("closure-sweep")
        self.assertEqual(result.returncode, 0)
        self.assertIn("every line above needs a next action", result.stdout)

    def test_two_repos_are_both_queried(self):
        self.env["CLOSURE_REPOS"] = "acme/repo acme/infra"
        self.run_tool("closure-sweep")
        repos = [call["argv"] for call in self.stub_calls("gh")]
        self.assertEqual(len(repos), 2)
        self.assertIn("acme/repo", repos[0])
        self.assertIn("acme/infra", repos[1])


class TmuxToolsSurvive(ShellToolCase):
    NAMES = ("deck", "pair", "fleet-toggle")

    def setUp(self):
        super().setUp()
        self.write_stub("claude")
        self.write_stub("tmux")
        self.env["STUB_CLAUDE_AGENTS_OUT"] = "[]"

    def test_scripts_exist_and_are_executable(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                path = BIN / name
                self.assertTrue(path.exists(), "missing executable: %s" % path)
                self.assertTrue(os.access(str(path), os.X_OK), "not executable: %s" % path)

    def test_scripts_parse_under_bash(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                path = BIN / name
                self.assertTrue(path.exists(), "missing executable: %s" % path)
                check = subprocess.run(["bash", "-n", str(path)], capture_output=True, encoding="utf-8")
                self.assertEqual(check.returncode, 0, check.stderr)

    def test_deck_attaches_to_an_existing_session(self):
        result = self.run_tool("deck")
        self.assertEqual(result.returncode, 0)
        subs = [call["argv"][0] for call in self.stub_calls("tmux")]
        self.assertIn("has-session", subs)
        self.assertNotIn("new-session", subs)
        self.assertTrue(any(call["argv"][:2] == ["has-session", "-t"] and "=interpret" in call["argv"] for call in self.stub_calls("tmux")))
        self.assertTrue(any(call["argv"][0] in ("attach", "switch-client") for call in self.stub_calls("tmux")))

    def test_deck_honours_a_session_name(self):
        result = self.run_tool("deck", "scratch")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(any("=scratch" in call["argv"] for call in self.stub_calls("tmux")))

    def test_pair_with_no_match_lists_running_sessions(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "aaaaaaaa-1111-2222-3333-444444444444", "kind": "interactive", "status": "idle", "name": "solo"}
        )
        result = self.run_tool("pair")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no match — running sessions:", result.stdout)
        self.assertIn("aaaaaaaa", result.stdout)
        self.assertIn("solo", result.stdout)
        self.assertEqual(self.stub_calls("tmux"), [])

    def test_pair_with_one_background_match_attaches_in_place(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "abcd1234-1111-2222-3333-444444444444", "kind": "background", "status": "running", "name": "mn1/thing"}
        )
        result = self.run_tool("pair")
        self.assertEqual(result.returncode, 0)
        attaches = [call["argv"] for call in self.stub_calls("claude") if call["argv"][:1] == ["attach"]]
        self.assertEqual(attaches, [["attach", "abcd1234"]])
        self.assertEqual(self.stub_calls("tmux"), [])

    def test_pair_reports_more_than_one_match(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "abcd1234-1111-2222-3333-444444444444", "kind": "background", "status": "running", "name": "one"},
            {"sessionId": "efab5678-1111-2222-3333-444444444444", "kind": "background", "status": "running", "name": "two"},
        )
        result = self.run_tool("pair")
        self.assertEqual(result.returncode, 1)
        self.assertIn("more than one match:", result.stdout)
        self.assertIn("abcd1234", result.stdout)
        self.assertIn("efab5678", result.stdout)

    def test_pair_never_matches_the_calling_session(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "abcd1234-1111-2222-3333-444444444444"
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "abcd1234-1111-2222-3333-444444444444", "kind": "background", "status": "running", "name": "self"}
        )
        result = self.run_tool("pair")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no match — running sessions:", result.stdout)

    def test_pair_matches_on_a_short_id_prefix(self):
        self.env["STUB_CLAUDE_AGENTS_OUT"] = agents_json(
            {"sessionId": "abcd1234-1111-2222-3333-444444444444", "kind": "interactive", "status": "idle", "name": "one"},
            {"sessionId": "efab5678-1111-2222-3333-444444444444", "kind": "background", "status": "running", "name": "two"},
        )
        result = self.run_tool("pair", "abcd")
        self.assertEqual(result.returncode, 0)
        attaches = [call["argv"] for call in self.stub_calls("claude") if call["argv"][:1] == ["attach"]]
        self.assertEqual(attaches, [["attach", "abcd1234"]])

    def test_fleet_toggle_outside_tmux_errors_cleanly(self):
        result = self.run_tool("fleet-toggle")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no 'deck' window in this session", result.stdout)
        self.assertFalse(any(call["argv"][:1] == ["send-keys"] for call in self.stub_calls("tmux")))

    def test_fleet_toggle_rejects_an_unknown_target(self):
        self.env["STUB_TMUX_LIST_PANES_OUT"] = "%1 0 bash\n%2 60 bash\n"
        result = self.run_tool("fleet-toggle", "sideways")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage: fleet-toggle [fleet|native]", result.stdout)

    def test_fleet_toggle_starts_fleet_in_an_idle_pane(self):
        self.env["STUB_TMUX_LIST_PANES_OUT"] = "%1 0 bash\n%2 60 bash\n"
        result = self.run_tool("fleet-toggle", "fleet")
        self.assertEqual(result.returncode, 0)
        self.assertIn("deck inbox: none -> fleet", result.stdout)
        sends = [call["argv"] for call in self.stub_calls("tmux") if call["argv"][:1] == ["send-keys"]]
        self.assertTrue(any("fleet" in argv for argv in sends))
        self.assertTrue(all("%1" in argv for argv in sends))

    def test_fleet_toggle_starts_the_native_view_in_an_idle_pane(self):
        self.env["STUB_TMUX_LIST_PANES_OUT"] = "%1 0 bash\n"
        result = self.run_tool("fleet-toggle", "native")
        self.assertEqual(result.returncode, 0)
        self.assertIn("deck inbox: none -> native", result.stdout)
        sends = [call["argv"] for call in self.stub_calls("tmux") if call["argv"][:1] == ["send-keys"]]
        self.assertTrue(any("claude agents --cwd" in " ".join(argv) for argv in sends))


if __name__ == "__main__":
    unittest.main()
