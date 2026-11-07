import importlib.util
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import configure


spec = importlib.util.spec_from_file_location("pilot", Path(__file__).with_name("workflow-pilot.py"))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class ReadOnlyApi:
    def call(self, method, path):
        if (method, path) != ("GET", "/api/v1/agents"):
            raise AssertionError("Profile selection must not mutate configuration")
        return {"agents": [
            {"name": "codex-acp", "profiles": [{"id": "codex", "name": "Default", "model": "selected"}]},
            {"name": "opencode-acp", "profiles": [{"id": "opencode", "name": "Default", "model": "selected"}]},
        ]}


class ClaudeProfileApi:
    def __init__(self, *envs):
        self.agents = [
            {"name": "claude-acp", "profiles": [{"id": f"claude{i}", "name": "Claude", "auto_approve": True, "env_vars": env} for i, env in enumerate(envs)]},
            {"name": "codex-acp", "profiles": [{"id": "codex", "name": "Codex", "env_vars": []}]},
        ]
        self.patches = []
        self.persist = True

    def call(self, method, path, body=None, interlock=False):
        if method == "PATCH":
            self.patches.append((path, body))
            if self.persist:
                next(p for a in self.agents for p in a["profiles"] if path.endswith("/" + p["id"])).update(copy.deepcopy(body))
            return {}
        return {"agents": copy.deepcopy(self.agents)}


INBOX = "features.needsYouInbox"


def flag(effective=False, override=None, pending=False, locked=False):
    return {"key": INBOX, "effective_value": effective, "override_value": override,
            "requires_restart_to_apply": pending, "env_locked": locked, "env_var": "KANDEV_FEATURES_NEEDS_YOU_INBOX"}


class SettingsApi(configure.Api):
    def __init__(self, flags=(), providers=()):
        self.flags = copy.deepcopy(list(flags))
        self.providers = copy.deepcopy(list(providers))
        self.writes = []
        self.persist = True

    def call(self, method, path, body=None, interlock=False):
        if method == "GET":
            return {"flags": copy.deepcopy(self.flags), "providers": copy.deepcopy(self.providers)}
        self.writes.append((method, path, body))
        if path.startswith("/api/v1/runtime-flags/"):
            if self.persist:
                next(f for f in self.flags if path.endswith(f["key"])).update(override_value=body["override"], effective_value=body["override"], requires_restart_to_apply=True)
            return {"flags": copy.deepcopy(self.flags)}
        provider = next(p for p in self.providers if path.endswith("/" + p["id"]))
        if self.persist:
            provider.update(copy.deepcopy(body))
        return copy.deepcopy(provider)


def kandev_version(text):
    return patch.object(configure.subprocess, "run", return_value=subprocess.CompletedProcess(["kandev"], 0, stdout=text, stderr=""))


def quietly(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def env_of(profile):
    return {e["key"]: e["value"] for e in profile["env_vars"]}


def run_main(api, conf, *patches):
    with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
        path = Path(temporary) / "fleet.json"
        path.write_text(json.dumps(conf))
        stack.enter_context(patch("sys.argv", ["configure", "--conf", str(path)]))
        stack.enter_context(patch.object(configure, "Api", return_value=api))
        stack.enter_context(patch.object(configure, "ensure_workspace", return_value={"id": "w", "name": "W"}))
        stack.enter_context(patch.object(configure, "ensure_repositories", return_value={}))
        stack.enter_context(patch.object(configure, "ensure_runtime_flags", return_value=[]))
        stack.enter_context(patch.object(configure, "ensure_notification_events"))
        for item in patches:
            stack.enter_context(item)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        configure.main()


class PilotTests(unittest.TestCase):
    def test_prepare_uses_portable_display_name_and_permission_mode(self):
        selected = {"id": "codex", "agent_display_name": "Codex", "model": "selected", "mode": "agent-full-access"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "pilot.json"
            args = ["pilot", "--agent", "codex-acp", "--model", "selected", "--output", str(output)]
            with patch("sys.argv", args), patch.object(pilot, "ensure_workspace", return_value={"id": "workspace"}), patch.object(pilot, "select_agent_profile", return_value=selected), contextlib.redirect_stdout(io.StringIO()):
                pilot.main()
            workflow = json.loads(output.read_text())["workflows"][0]
            expected = {"agent_name": "Codex", "model": "selected", "mode": "agent-full-access"}
            self.assertEqual(expected, workflow["agent_profile"])
            self.assertTrue(all(step["agent_profile"] == expected for step in workflow["steps"]))

    def test_profile_selection_is_exact_and_does_not_mutate(self):
        api = ReadOnlyApi()
        self.assertEqual("opencode", configure.select_agent_profile(api, {"agent": "opencode-acp", "model": "selected"})["id"])
        self.assertEqual("codex", configure.select_agent_profile(api, {"id": "codex"})["id"])
        for selection in [{}, {"name": "Default"}, {"agent": "missing"}]:
            with self.assertRaises(RuntimeError):
                configure.select_agent_profile(api, selection)

    def test_claude_profile_gets_the_machine_name_for_telemetry(self):
        api = ClaudeProfileApi([{"key": "KEEP", "value": "1"}])
        with patch.object(configure, "agent_host_name", return_value="test-host"), patch.object(configure, "claude_executable", return_value="/bin/claude"), contextlib.redirect_stdout(io.StringIO()):
            configure.ensure_claude_env(api)
            configure.ensure_claude_env(api)
        env = env_of(api.agents[0]["profiles"][0])
        self.assertEqual("host.name=test-host", env["OTEL_RESOURCE_ATTRIBUTES"])
        self.assertEqual("1", env["KEEP"])
        self.assertEqual(1, len(api.patches))

    def test_claude_executable_prefers_native_link_unresolved(self):
        with patch.object(configure.os.path, "expanduser", return_value="/h/.local/bin/claude"), patch.object(configure.os, "access", return_value=True), patch.object(configure.os.path, "realpath", side_effect=AssertionError):
            self.assertEqual("/h/.local/bin/claude", configure.claude_executable())

    def test_claude_executable_keeps_which_path_unresolved(self):
        with patch.object(configure.os, "access", return_value=False), patch.object(configure.shutil, "which", return_value="/opt/homebrew/bin/claude"), patch.object(configure.os.path, "realpath", side_effect=AssertionError):
            self.assertEqual("/opt/homebrew/bin/claude", configure.claude_executable())

    def test_claude_executable_refuses_nvm(self):
        with patch.object(configure.os, "access", return_value=False), patch.object(configure.shutil, "which", return_value="/h/.nvm/versions/node/v24.15.0/bin/claude"):
            with self.assertRaisesRegex(RuntimeError, "claude.ai/install.sh"):
                configure.claude_executable()

    def test_claude_env_applies_when_another_profile_is_selected(self):
        api = ClaudeProfileApi([{"key": "KEEP", "value": "1"}])
        with patch.object(configure, "claude_executable", return_value="/h/.local/bin/claude"), patch.object(configure, "agent_host_name", return_value="h"), contextlib.redirect_stdout(io.StringIO()):
            configure.ensure_claude_env(api)
        env = {e["key"]: e["value"] for e in api.patches[0][1]["env_vars"]}
        self.assertEqual({"KEEP": "1", "CLAUDE_CODE_EXECUTABLE": "/h/.local/bin/claude", "CLAUDE_CODE_ARTIFACT": "1", "OTEL_RESOURCE_ATTRIBUTES": "host.name=h"}, env)
        self.assertNotIn("CLAUDE_CODE_ENABLE_CFC", env)

    def test_claude_env_read_back_mismatch_stops(self):
        api = ClaudeProfileApi([])
        api.persist = False
        with patch.object(configure, "claude_executable", return_value="/bin/claude"), patch.object(configure, "agent_host_name", return_value="h"), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "did not persist"):
                configure.ensure_claude_env(api)

    def test_main_applies_claude_env_with_a_codex_selection(self):
        api = ClaudeProfileApi([], [{"key": "KEEP", "value": "1"}])
        run_main(api, {"workspace": "W", "agent_profile": {"agent": "codex-acp"}},
                 patch.object(configure, "require_kandev", return_value="0.99.1"),
                 patch.object(configure, "claude_executable", return_value="/h/.local/bin/claude"),
                 patch.object(configure, "agent_host_name", return_value="h"))
        self.assertEqual(["/api/v1/agent-profiles/claude0", "/api/v1/agent-profiles/claude1"], [path for path, _ in api.patches])
        for profile in api.agents[0]["profiles"]:
            self.assertEqual("/h/.local/bin/claude", env_of(profile)["CLAUDE_CODE_EXECUTABLE"])
            self.assertEqual("1", env_of(profile)["CLAUDE_CODE_ARTIFACT"])
        self.assertEqual("1", env_of(api.agents[0]["profiles"][1])["KEEP"])
        self.assertEqual([], api.agents[1]["profiles"][0]["env_vars"])

    def test_mutate_retries_with_the_interlock_only_when_refused(self):
        class InterlockApi(configure.Api):
            def __init__(self):
                self.attempts = []

            def call(self, method, path, body=None, interlock=False):
                self.attempts.append(interlock)
                if not interlock:
                    raise RuntimeError(f"{method} {path} -> 403: interim settings interlock required")
                return {"ok": True}

        api = InterlockApi()
        self.assertEqual({"ok": True}, api.mutate("PATCH", "/x", {}))
        self.assertEqual([False, True], api.attempts)

    def test_flag_already_set_is_not_patched(self):
        api = SettingsApi([flag(effective=True, override=True)])
        self.assertEqual([], quietly(configure.ensure_runtime_flags, api, {INBOX: True}))
        self.assertEqual([], api.writes)

    def test_flag_override_is_patched_and_restart_reported(self):
        api = SettingsApi([flag()])
        self.assertEqual([INBOX], quietly(configure.ensure_runtime_flags, api, {INBOX: True}))
        self.assertEqual([("PATCH", "/api/v1/runtime-flags/features.needsYouInbox", {"override": True})], api.writes)

    def test_pending_restart_is_reported_without_a_patch(self):
        api = SettingsApi([flag(effective=True, override=True, pending=True)])
        self.assertEqual([INBOX], quietly(configure.ensure_runtime_flags, api, {INBOX: True}))
        self.assertEqual([], api.writes)

    def test_env_locked_flag_is_left_alone(self):
        api = SettingsApi([flag(locked=True)])
        self.assertEqual([], quietly(configure.ensure_runtime_flags, api, {INBOX: True}))
        self.assertEqual([], api.writes)

    def test_unknown_flag_stops(self):
        with self.assertRaisesRegex(RuntimeError, "features.missing"):
            quietly(configure.ensure_runtime_flags, SettingsApi([flag()]), {"features.missing": True})

    def test_notification_events_are_added_not_replaced(self):
        api = SettingsApi(providers=[
            {"id": "desktop", "name": "Desktop", "enabled": True, "events": ["session.clarification_requested", "office.inbox_item"]},
            {"id": "complete", "name": "Complete", "enabled": True, "events": ["session.failed", "session.permission_requested", "system.update_available"]},
            {"id": "off", "name": "Off", "enabled": False, "events": []},
        ])
        quietly(configure.ensure_notification_events, api, ["session.permission_requested", "session.failed"])
        self.assertEqual([("PATCH", "/api/v1/notification-providers/desktop", {"events": ["office.inbox_item", "session.clarification_requested", "session.failed", "session.permission_requested"]})], api.writes)

    def test_settings_read_back_mismatch_stops(self):
        api = SettingsApi([flag()], [{"id": "desktop", "name": "Desktop", "enabled": True, "events": []}])
        api.persist = False
        with self.assertRaisesRegex(RuntimeError, "did not persist"):
            quietly(configure.ensure_runtime_flags, api, {INBOX: True})
        with self.assertRaisesRegex(RuntimeError, "did not persist"):
            quietly(configure.ensure_notification_events, api, ["session.failed"])

    def test_existing_config_without_blocks_gets_defaults(self):
        self.assertEqual({"features.needsYouInbox": True}, configure.settings({"workspace": "W"}, "runtime_flags"))
        self.assertEqual(["session.clarification_requested", "session.permission_requested", "session.failed"], configure.settings({"workspace": "W"}, "notifications")["events"])
        self.assertEqual({"features.other": False}, configure.settings({"runtime_flags": {"features.other": False}}, "runtime_flags"))
        self.assertEqual({}, configure.settings({"notifications": {"enabled": False}}, "notifications"))

    def test_old_kandev_is_refused_before_any_change(self):
        api = ClaudeProfileApi([])
        with self.assertRaisesRegex(RuntimeError, "brew upgrade kandev"):
            run_main(api, {"workspace": "W", "agent_profile": {"agent": "codex-acp"}}, kandev_version("v0.97.2\n"),
                     patch.object(configure, "claude_executable", return_value="/bin/claude"),
                     patch.object(configure, "agent_host_name", return_value="h"))
        self.assertEqual([], api.patches)
        with kandev_version("v0.99.1\n"):
            self.assertEqual("0.99.1", configure.require_kandev())

    def test_only_evidence_gated_work_can_advance_automatically(self):
        data = pilot.document("codex-acp", "selected")
        self.assertEqual(1, data["version"])
        workflow = data["workflows"][0]
        self.assertEqual({"agent_name": "codex-acp", "model": "selected"}, workflow["agent_profile"])
        self.assertEqual(1, sum(s["is_start_step"] for s in workflow["steps"]))
        for step in workflow["steps"]:
            self.assertTrue(step["auto_advance_requires_signal"])
            self.assertFalse(step["cancel_triggers_turn_complete"])
            self.assertFalse(step["events"].get("on_enter"))
            self.assertFalse(step["events"].get("on_turn_start"))
        self.assertEqual({"on_turn_complete": [{"type": "move_to_next"}]}, workflow["steps"][0]["events"])
        self.assertTrue(all(not s["events"] for s in workflow["steps"][1:]))


if __name__ == "__main__":
    unittest.main()
