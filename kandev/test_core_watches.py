import contextlib
import copy
import io
import unittest

import configure


CODEX = {"agent": "codex-acp", "model": "gpt-6.1-sol"}
CORE_LABELS = ["agent:implement", "agent:investigate", "agent:implement-codex", "agent:investigate-codex"]


def fleet(watches=None, lanes=None, **extra):
    return {
        "workspace": "W",
        "lanes": lanes if lanes is not None else [{"name": "gigme", "path": "/repo/gigme"}],
        "linear": {"team": "NEV", "state": "Todo", "assigned": "me", "poll_seconds": 60, "max_inflight": 4,
                   "watches": watches or []},
        **extra,
    }


class FleetApi:
    def __init__(self, labels=None, watches=None, codex=True):
        self.labels = labels if labels is not None else {name: f"id-{name}" for name in CORE_LABELS}
        self.watches = watches or []
        profiles = [{"name": "claude-acp", "profiles": [{"id": "claude", "name": "Claude", "model": "opus[1m]"}]}]
        if codex:
            profiles.append({"name": "codex-acp", "profiles": [{"id": "codex", "name": "Codex", "model": "gpt-6.1-sol"}]})
        self.agents = profiles

    def call(self, method, path, body=None, interlock=False):
        if method != "GET":
            raise AssertionError(f"read-only check sent {method} {path}")
        routes = {
            "/api/v1/workspaces": {"workspaces": [{"id": "ws", "name": "W"}]},
            "/api/v1/workspaces/ws/repositories": {"repositories": [{"id": "repo", "name": "gigme", "local_path": "/repo/gigme"}]},
            "/api/v1/agents": {"agents": self.agents},
            "/api/v1/linear/labels?team_key=NEV&workspace_id=ws": {"labels": [{"name": n, "id": i} for n, i in self.labels.items()]},
            "/api/v1/linear/states?team_key=NEV&workspace_id=ws": {"states": [{"name": "Todo", "id": "todo"}]},
            "/api/v1/workspaces/ws/workflows": {"workflows": [{"id": "wf", "name": "Development"}]},
            "/api/v1/workflows/wf/workflow/steps": {"steps": [{"id": "start", "is_start_step": True}]},
            "/api/v1/executor-profiles": {"profiles": [{"id": "exec", "executor_type": "worktree", "executor_id": "e"}]},
            "/api/v1/linear/watches/issue?workspace_id=ws": {"watches": copy.deepcopy(self.watches)},
        }
        return copy.deepcopy(routes[path])

    def mutate(self, method, path, body):
        return self.call(method, path, body)


def live(label, profile):
    prompt = "/investigate {{issue.identifier}}" if "investigate" in label else "/e2e {{issue.identifier}}"
    return {
        "id": f"w-{label}", "workflowId": "wf", "workflowStepId": "start", "repositoryId": "repo", "baseBranch": "main",
        "filter": {"teamKey": "NEV", "stateIds": ["todo"], "assigned": "me", "labelIds": [f"id-{label}"]},
        "agentProfileId": profile, "executorProfileId": "exec", "prompt": prompt,
        "pollIntervalSeconds": 60, "maxInflightTasks": 4, "sortBy": "priority", "enabled": True,
    }


def all_live():
    return [live(label, "codex" if label.endswith("-codex") else "claude") for label in CORE_LABELS]


def quiet_drift(api, conf):
    with contextlib.redirect_stdout(io.StringIO()):
        return configure.watch_drift(api, conf)


class FleetWatchTests(unittest.TestCase):
    def test_core_flows_are_added_to_a_machine_that_lists_none(self):
        watches = configure.fleet_watches(fleet())
        self.assertEqual(CORE_LABELS, [w["label"] for w in watches])
        self.assertTrue(all(w["repository"] == "gigme" for w in watches))
        self.assertEqual(CODEX, watches[2]["agent_profile"])

    def test_machine_entries_override_core_fields_and_custom_watches_are_kept(self):
        own = [{"label": "agent:implement", "repository": "gigme", "prompt": "/e2e {{issue.identifier}} --direct", "label_id": "L1"},
               {"label": "bug-bash", "repository": "gigme", "prompt": "/investigate {{issue.identifier}}"}]
        watches = {w["label"]: w for w in configure.fleet_watches(fleet(own))}
        self.assertEqual("/e2e {{issue.identifier}} --direct", watches["agent:implement"]["prompt"])
        self.assertEqual("L1", watches["agent:implement"]["label_id"])
        self.assertFalse(watches["agent:implement"].get("optional"))
        self.assertTrue(watches["agent:implement-codex"]["optional"])
        self.assertIn("bug-bash", watches)

    def test_skip_opts_a_machine_out_of_one_core_flow(self):
        watches = configure.fleet_watches(fleet([{"label": "agent:implement-codex", "skip": True}]))
        self.assertNotIn("agent:implement-codex", [w["label"] for w in watches])

    def test_empty_core_block_opts_out_of_every_core_flow(self):
        self.assertEqual([], configure.fleet_watches(fleet(core_watches=[])))

    def test_matching_fleet_has_no_drift(self):
        self.assertEqual([], quiet_drift(FleetApi(watches=all_live()), fleet()))

    def test_missing_core_watch_is_reported_without_changing_anything(self):
        problems = quiet_drift(FleetApi(watches=all_live()[:2]), fleet())
        self.assertEqual(["watch agent:implement-codex is missing", "watch agent:investigate-codex is missing"], problems)

    def test_changed_watch_reports_which_fields_differ(self):
        watches = all_live()
        watches[2]["agentProfileId"] = "claude"
        self.assertEqual(["watch agent:implement-codex differs: agentProfileId"], quiet_drift(FleetApi(watches=watches), fleet()))

    def test_core_flow_with_no_label_is_skipped_with_the_fix(self):
        labels = {name: f"id-{name}" for name in CORE_LABELS[:2]}
        problems = quiet_drift(FleetApi(labels=labels, watches=all_live()[:2]), fleet())
        self.assertEqual(2, len(problems))
        self.assertIn("core flow agent:implement-codex skipped", problems[0])
        self.assertIn("create label 'agent:implement-codex' in team NEV", problems[0])

    def test_core_flow_with_no_codex_profile_is_skipped(self):
        problems = quiet_drift(FleetApi(watches=all_live()[:2], codex=False), fleet())
        self.assertIn("core flow agent:implement-codex skipped", problems[0])
        self.assertIn("agent_profile", problems[0])

    def test_listed_watch_with_no_label_still_stops(self):
        own = [{"label": "agent:implement-codex", "repository": "gigme", "prompt": "/e2e {{issue.identifier}}", "agent_profile": CODEX}]
        with self.assertRaisesRegex(RuntimeError, "not visible"):
            quiet_drift(FleetApi(labels={}, watches=[]), fleet(own, core_watches=[]))

    def test_core_flow_needs_a_lane_when_there_are_several(self):
        lanes = [{"name": "gigme", "path": "/repo/gigme"}, {"name": "other", "path": "/repo/other"}]
        problems = quiet_drift(FleetApi(watches=[]), fleet(lanes=lanes))
        self.assertIn("set linear.repository", problems[0])

    def test_configure_creates_missing_core_watches(self):
        api = FleetApi(watches=all_live()[:2])
        posts = []
        api.call = wrap_writes(api.call, posts)
        with contextlib.redirect_stdout(io.StringIO()):
            ws = configure.ensure_workspace(api, fleet())
            repos = configure.find_repositories(api, ws, fleet()["lanes"])
            configure.ensure_watches(api, ws, fleet(), repos, {"id": "claude"})
        created = [body["filter"]["labelIds"][0] for method, path, body in posts if method == "POST"]
        self.assertEqual(["id-agent:implement-codex", "id-agent:investigate-codex"], created)
        self.assertEqual({"codex"}, {body["agentProfileId"] for method, _, body in posts if method == "POST"})


def wrap_writes(read, log):
    def call(method, path, body=None, interlock=False):
        if method == "GET":
            return read(method, path)
        log.append((method, path, body))
        return {}
    return call


if __name__ == "__main__":
    unittest.main()
