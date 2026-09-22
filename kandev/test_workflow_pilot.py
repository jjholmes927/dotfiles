import importlib.util
import contextlib
import io
import json
from pathlib import Path
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
