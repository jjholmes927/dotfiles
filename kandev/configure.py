#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

changes = []

DEFAULTS = {
    "runtime_flags": {"features.needsYouInbox": True},
    "notifications": {"events": ["session.clarification_requested", "session.permission_requested", "session.failed"]},
    "pr_merged": {"workflow": "Development", "from_steps": ["In Progress", "Review"], "to_step": "Done"},
}


def log(msg):
    print(f"kandev/configure: {msg}")


def changed(msg):
    changes.append(msg)
    log(f"CHANGED {msg}")


class Api:
    def __init__(self, base):
        self.base = base
        self.token = None

    def call(self, method, path, body=None, interlock=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if interlock:
            req.add_header("X-Kandev-Interim-Settings-Interlock", self.interlock_token())
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as err:
            raw = err.read().decode()
            raise RuntimeError(f"{method} {path} -> {err.code}: {raw[:300]}")
        return json.loads(raw) if raw.strip() else {}

    def mutate(self, method, path, body):
        try:
            return self.call(method, path, body)
        except RuntimeError as err:
            if "interlock" not in str(err):
                raise
            return self.call(method, path, body, interlock=True)

    def interlock_token(self):
        if self.token:
            return self.token
        with urllib.request.urlopen(self.base + "/", timeout=30) as resp:
            html = resp.read().decode(errors="replace")
        match = re.search(r'interimSettingsInterlockToken[^A-Za-z0-9_-]+([A-Za-z0-9_-]{20,})', html)
        if not match:
            raise RuntimeError("could not read the settings interlock token from the boot payload")
        self.token = match.group(1)
        return self.token


def settings(conf, key):
    block = conf.get(key, DEFAULTS[key])
    return {} if block.get("enabled") is False else block


def require_kandev(minimum=(0, 98, 0)):
    out = subprocess.run(["kandev", "--version"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    if not match:
        raise RuntimeError(f"could not read the Kandev version from `kandev --version`: {out.strip()!r}")
    if tuple(int(n) for n in match.groups()) < minimum:
        raise RuntimeError(f"Kandev {match.group(0)} is older than {'.'.join(map(str, minimum))}; "
                           "run `brew upgrade kandev` while no task is running, then re-run")
    return match.group(0)


def expand(path):
    return os.path.abspath(os.path.expanduser(path)) if path else path


def keychain_secret(item):
    if not item:
        return ""
    out = subprocess.run(["security", "find-generic-password", "-s", item, "-w"], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def ensure_workspace(api, conf):
    workspaces = api.call("GET", "/api/v1/workspaces").get("workspaces", [])
    wanted = conf.get("workspace")
    for ws in workspaces:
        if not wanted or ws["name"] == wanted:
            return ws
    raise RuntimeError(f"workspace {wanted!r} not found; create it in Kandev first")


def ensure_repositories(api, ws, lanes):
    existing = api.call("GET", f"/api/v1/workspaces/{ws['id']}/repositories").get("repositories", [])
    by_path = {expand(r.get("local_path")): r for r in existing}
    result = {}
    for lane in lanes:
        path = expand(lane["path"])
        desired = {
            "setup_script": expand(lane.get("setup_script", "")) or "",
            "cleanup_script": expand(lane.get("cleanup_script", "")) or "",
            "worktree_branch_template": lane.get("branch_template", "jjholmes927-{title}-{suffix}"),
            "pull_before_worktree": True,
        }
        repo = by_path.get(path)
        if repo is None:
            body = {"name": lane["name"], "source_type": "local", "local_path": path,
                    "default_branch": lane.get("default_branch", "main"), **desired}
            repo = api.call("POST", f"/api/v1/workspaces/{ws['id']}/repositories", body)
            changed(f"registered repository {lane['name']} at {path}")
        else:
            patch = {k: v for k, v in desired.items() if repo.get(k) != v}
            if patch:
                api.call("PATCH", f"/api/v1/repositories/{repo['id']}", patch)
                changed(f"updated repository {lane['name']}: {sorted(patch)}")
        result[lane["name"]] = repo
    return result


def agent_host_name():
    helper = os.path.expanduser("~/.local/bin/agent-host-name")
    if os.access(helper, os.X_OK):
        return subprocess.run([helper], capture_output=True, text=True, check=True).stdout.strip()
    return socket.gethostname().split(".")[0]


def claude_executable():
    native = os.path.expanduser("~/.local/bin/claude")
    path = native if os.access(native, os.X_OK) else shutil.which("claude")
    if not path or "/.nvm/" in path:
        raise RuntimeError(f"claude resolves to {path}; install the native build: curl -fsSL https://claude.ai/install.sh | bash")
    return path


def env_of(profile):
    return {e["key"]: e.get("value", "") for e in (profile.get("env_vars") or [])}


def claude_profiles(api):
    agents = api.call("GET", "/api/v1/agents").get("agents", [])
    return next((a.get("profiles", []) for a in agents if a["name"] == "claude-acp"), None)


def stale_env(profile, wanted):
    current = env_of(profile)
    return sorted(k for k, v in wanted.items() if current.get(k) != v)


def ensure_claude_env(api):
    profiles = claude_profiles(api)
    if profiles is None:
        log("no claude-acp agent; Claude profile env not applied")
        return
    wanted = {"CLAUDE_CODE_EXECUTABLE": claude_executable(), "CLAUDE_CODE_ARTIFACT": "1",
              "OTEL_RESOURCE_ATTRIBUTES": f"host.name={agent_host_name()}"}
    stale = [p for p in profiles if stale_env(p, wanted)]
    for profile in stale:
        merged = {**env_of(profile), **wanted}
        api.call("PATCH", f"/api/v1/agent-profiles/{profile['id']}",
                 {"env_vars": [{"key": k, "value": v} for k, v in merged.items()]}, interlock=True)
        changed(f"claude profile {profile.get('name')}: env {stale_env(profile, wanted)}")
    if stale and any(stale_env(p, wanted) for p in claude_profiles(api) or []):
        raise RuntimeError("Claude profile env did not persist; check Settings > Agents")


def ensure_claude_profile(api, conf):
    agents = api.call("GET", "/api/v1/agents").get("agents", [])
    claude = next((a for a in agents if a["name"] == "claude-acp"), None)
    if not claude:
        raise RuntimeError("claude-acp agent not detected by Kandev; is `claude` on the service's PATH?")
    if claude.get("capability_status") not in (None, "ok"):
        log(f"warning: claude-acp probe status {claude.get('capability_status')}: {str(claude.get('capability_error'))[:160]}")
    profiles = claude.get("profiles", [])
    if not profiles:
        raise RuntimeError("claude-acp has no profile; open Settings > Agents once so Kandev seeds one")
    profile = profiles[0]
    want = conf.get("claude_profile", {})
    patch = {}
    if want.get("auto_approve", True) != profile.get("auto_approve"):
        patch["auto_approve"] = want.get("auto_approve", True)
    if want.get("model") and want["model"] != profile.get("model"):
        patch["model"] = want["model"]
    if patch:
        api.call("PATCH", f"/api/v1/agent-profiles/{profile['id']}", patch, interlock=True)
        changed(f"claude profile {profile.get('name')}: {sorted(patch)}")
    return profile


def ensure_runtime_flags(api, flags):
    states = {f["key"]: f for f in api.call("GET", "/api/v1/runtime-flags").get("flags", [])}
    pending = []
    for key, value in flags.items():
        state = states.get(key)
        if state is None:
            raise RuntimeError(f"runtime flag {key!r} not found in this Kandev")
        if state.get("effective_value") != value:
            if state.get("env_locked"):
                log(f"runtime flag {key} is set by {state.get('env_var')}; leaving it")
                continue
            after = {f["key"]: f for f in api.mutate("PATCH", f"/api/v1/runtime-flags/{key}", {"override": value}).get("flags", [])}
            state = after.get(key, {})
            if state.get("effective_value") != value:
                raise RuntimeError(f"runtime flag {key} did not persist as {value}")
            changed(f"runtime flag {key} set to {value}")
        if state.get("requires_restart_to_apply"):
            pending.append(key)
    return pending


def ensure_notification_events(api, events):
    for provider in api.call("GET", "/api/v1/notification-providers").get("providers", []):
        current = provider.get("events") or []
        if not provider.get("enabled") or set(events) <= set(current):
            continue
        wanted = sorted(set(current) | set(events))
        after = api.mutate("PATCH", f"/api/v1/notification-providers/{provider['id']}", {"events": wanted})
        if sorted(after.get("events") or []) != wanted:
            raise RuntimeError(f"notification provider {provider.get('name')} events did not persist")
        changed(f"notification provider {provider.get('name')}: events {sorted(set(events) - set(current))}")


def select_agent_profile(api, selection):
    agents = api.call("GET", "/api/v1/agents").get("agents", [])
    matches = [p for a in agents for p in a.get("profiles", [])
               if a.get("capability_status") in (None, "ok") and p.get("enabled", True)
               and (not selection.get("agent") or a["name"] == selection["agent"])
               and all(p.get(key) == value for key, value in selection.items() if key != "agent")]
    if not selection or len(matches) != 1:
        raise RuntimeError("agent_profile must identify exactly one existing profile by id or agent/name/model")
    return matches[0]


def ensure_linear(api, ws, linear):
    cfg = api.call("GET", f"/api/v1/linear/config?workspace_id={ws['id']}")
    if not cfg.get("hasSecret"):
        secret = keychain_secret(linear.get("keychain_item", "linear-api-key"))
        if not secret:
            raise RuntimeError(
                f"Linear key missing: add it with `security add-generic-password -a $USER -s "
                f"{linear.get('keychain_item', 'linear-api-key')} -w '<key>' -U` and re-run")
        api.call("POST", f"/api/v1/linear/config?workspace_id={ws['id']}",
                 {"authMethod": "api_key", "defaultTeamKey": linear["team"], "secret": secret})
        changed("Linear connection configured")
    test = api.call("POST", f"/api/v1/linear/config/test?workspace_id={ws['id']}", {})
    if not test.get("ok", True):
        raise RuntimeError(f"Linear connection test failed: {test}")
    log(f"Linear connection OK ({test.get('orgSlug') or cfg.get('orgSlug')}, team {linear['team']})")


def lookup(api, ws, kind, team):
    data = api.call("GET", f"/api/v1/linear/{kind}?team_key={team}&workspace_id={ws['id']}")
    return {item["name"]: item["id"] for item in data.get(kind, [])}


def workflow_steps(api, ws, name):
    workflows = api.call("GET", f"/api/v1/workspaces/{ws['id']}/workflows").get("workflows", [])
    wf = next((w for w in workflows if w["name"] == name), None)
    if not wf:
        return None, []
    return wf, api.call("GET", f"/api/v1/workflows/{wf['id']}/workflow/steps").get("steps", [])


def workflow_start_step(api, ws, name):
    wf, steps = workflow_steps(api, ws, name)
    if not wf:
        raise RuntimeError(f"workflow {name!r} not found in workspace")
    start = next((s for s in steps if s.get("is_start_step")), None) or steps[0]
    return wf, start


def ensure_pr_merged_moves(api, ws, block, explicit):
    if not block:
        return
    by_name = {s["name"]: s for s in workflow_steps(api, ws, block["workflow"])[1]}
    missing = [n for n in [*block["from_steps"], block["to_step"]] if n not in by_name]
    if missing:
        msg = f"pr_merged: {missing} not found in workflow {block['workflow']!r}"
        if explicit:
            raise RuntimeError(msg)
        log(f"{msg}; skipping the default move-to-{block['to_step']}-on-merge")
        return
    move = [{"type": "move_to_step", "config": {"step_id": by_name[block["to_step"]]["id"]}}]
    for name in block["from_steps"]:
        step = by_name[name]
        events = step.get("events") or {}
        if events.get("on_pr_merged") == move:
            continue
        wanted = {**events, "on_pr_merged": move}
        api.mutate("PUT", f"/api/v1/workflow/steps/{step['id']}", {"events": wanted})
        if api.call("GET", f"/api/v1/workflow/steps/{step['id']}").get("step", {}).get("events") != wanted:
            raise RuntimeError(f"step {name} events did not persist after the PUT")
        changed(f"step {name}: move to {block['to_step']} when the PR merges")


def executor_profile(api, executor_type):
    profiles = api.call("GET", "/api/v1/executor-profiles").get("profiles", [])
    prof = next((p for p in profiles if p.get("executor_type") == executor_type), None)
    if not prof:
        raise RuntimeError(f"no executor profile of type {executor_type}")
    return prof


def ensure_executor_path(api, prof):
    current = {e["key"]: e.get("value", "") for e in (prof.get("env_vars") or [])}
    wanted = {k: v for k, v in current.items() if k != "CLAUDE_JOB_DIR"}
    wanted["PATH"] = os.environ.get("PATH", "")
    if wanted == current:
        return
    body = {"env_vars": [{"key": k, "value": v} for k, v in wanted.items()]}
    api.mutate("PATCH", f"/api/v1/executors/{prof['executor_id']}/profiles/{prof['id']}", body)
    note = "; CLAUDE_JOB_DIR removed (worktree isolation is detected from git since joel-workflow 2.15.0)" if "CLAUDE_JOB_DIR" in current else ""
    changed(f"executor profile {prof.get('name')}: PATH set from the current shell{note}")


def ensure_watches(api, ws, conf, repos, profile):
    linear = conf["linear"]
    team = linear["team"]
    labels = lookup(api, ws, "labels", team)
    states = lookup(api, ws, "states", team)
    state_id = states.get(linear.get("state", "Todo"))
    if not state_id:
        raise RuntimeError(f"Linear state {linear.get('state', 'Todo')!r} not found for team {team}")
    wf, step = workflow_start_step(api, ws, conf.get("workflow", "Development"))
    exec_prof = executor_profile(api, conf.get("executor", "worktree"))
    ensure_executor_path(api, exec_prof)
    existing = api.call("GET", f"/api/v1/linear/watches/issue?workspace_id={ws['id']}").get("watches", [])
    for watch in linear.get("watches", []):
        watch_profile = select_agent_profile(api, watch["agent_profile"]) if "agent_profile" in watch else profile
        label_id = watch.get("label_id") or labels.get(watch["label"])
        if not label_id:
            raise RuntimeError(
                f"Linear label {watch['label']!r} not visible to Kandev's team lookup (workspace-level labels are not "
                f"listed); set \"label_id\" for this watch in the config, or create the label as a team label")
        repo = repos.get(watch["repository"])
        if not repo:
            raise RuntimeError(f"watch {watch['label']} names unknown lane {watch['repository']!r}")
        desired = {
            "workflowId": wf["id"], "workflowStepId": step["id"],
            "repositoryId": repo["id"], "baseBranch": repo.get("default_branch", "main"),
            "filter": {"teamKey": team, "stateIds": [state_id], "assigned": linear.get("assigned", "me"), "labelIds": [label_id]},
            "agentProfileId": watch_profile["id"], "executorProfileId": exec_prof["id"],
            "prompt": watch["prompt"], "pollIntervalSeconds": linear.get("poll_seconds", 60),
            "maxInflightTasks": watch.get("max_inflight", linear.get("max_inflight", 2)),
            "sortBy": "priority", "enabled": watch.get("enabled", True),
        }
        current = next((w for w in existing if (w.get("filter") or {}).get("labelIds") == [label_id]), None)
        if current is None:
            api.call("POST", "/api/v1/linear/watches/issue", {"workspaceId": ws["id"], **desired})
            changed(f"created watch for {watch['label']}")
            continue
        patch = {}
        for key in ("prompt", "pollIntervalSeconds", "maxInflightTasks", "sortBy", "enabled", "agentProfileId", "executorProfileId", "repositoryId", "workflowStepId"):
            if current.get(key) != desired[key]:
                patch[key] = desired[key]
        if (current.get("filter") or {}) != desired["filter"]:
            patch["filter"] = desired["filter"]
        if patch:
            api.call("PATCH", f"/api/v1/linear/watches/issue/{current['id']}?workspace_id={ws['id']}", patch)
            changed(f"updated watch for {watch['label']}: {sorted(patch)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conf", default=os.path.expanduser("~/.config/kandev-fleet.json"))
    parser.add_argument("--base", default="http://127.0.0.1:38429")
    args = parser.parse_args()
    with open(args.conf) as fh:
        conf = json.load(fh)
    log(f"kandev {require_kandev()}")
    api = Api(args.base)
    for _ in range(30):
        try:
            api.call("GET", "/api/v1/workspaces")
            break
        except Exception:
            time.sleep(2)
    ws = ensure_workspace(api, conf)
    log(f"workspace {ws['name']} ({ws['id'][:8]})")
    repos = ensure_repositories(api, ws, conf.get("lanes", []))
    profile = select_agent_profile(api, conf["agent_profile"]) if "agent_profile" in conf else ensure_claude_profile(api, conf)
    ensure_claude_env(api)
    pending = ensure_runtime_flags(api, settings(conf, "runtime_flags"))
    ensure_notification_events(api, settings(conf, "notifications").get("events", []))
    ensure_pr_merged_moves(api, ws, settings(conf, "pr_merged"), "pr_merged" in conf)
    if conf.get("linear"):
        ensure_linear(api, ws, conf["linear"])
        ensure_watches(api, ws, conf, repos, profile)
    if changes:
        log(f"{len(changes)} change(s) applied")
    else:
        log("no changes; configuration already matches")
    if pending:
        log(f"{', '.join(pending)} not live yet; restart Kandev when no task is running: KANDEV_RESTART=1 kandev/install.sh")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        print(f"kandev/configure: {err}", file=sys.stderr)
        sys.exit(1)
