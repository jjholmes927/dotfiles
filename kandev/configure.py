#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

changes = []


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
    exe = os.path.realpath(shutil.which("claude"))
    env_wanted = {"CLAUDE_CODE_EXECUTABLE": exe}
    env_current = {e["key"]: e.get("value", "") for e in (profile.get("env_vars") or [])}
    patch = {}
    if want.get("auto_approve", True) != profile.get("auto_approve"):
        patch["auto_approve"] = want.get("auto_approve", True)
    if want.get("model") and want["model"] != profile.get("model"):
        patch["model"] = want["model"]
    if any(env_current.get(k) != v for k, v in env_wanted.items()):
        merged = {**env_current, **env_wanted}
        patch["env_vars"] = [{"key": k, "value": v} for k, v in merged.items()]
    if patch:
        api.call("PATCH", f"/api/v1/agent-profiles/{profile['id']}", patch, interlock=True)
        changed(f"claude profile {profile.get('name')}: {sorted(patch)}")
    return profile


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


def workflow_start_step(api, ws, name):
    workflows = api.call("GET", f"/api/v1/workspaces/{ws['id']}/workflows").get("workflows", [])
    wf = next((w for w in workflows if w["name"] == name), None)
    if not wf:
        raise RuntimeError(f"workflow {name!r} not found in workspace")
    steps = api.call("GET", f"/api/v1/workflows/{wf['id']}/workflow/steps").get("steps", [])
    start = next((s for s in steps if s.get("is_start_step")), None) or steps[0]
    return wf, start


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
    try:
        api.call("PATCH", f"/api/v1/executors/{prof['executor_id']}/profiles/{prof['id']}", body)
    except RuntimeError as err:
        if "interlock" not in str(err):
            raise
        api.call("PATCH", f"/api/v1/executors/{prof['executor_id']}/profiles/{prof['id']}", body, interlock=True)
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
            "agentProfileId": profile["id"], "executorProfileId": exec_prof["id"],
            "prompt": watch["prompt"], "pollIntervalSeconds": linear.get("poll_seconds", 60),
            "maxInflightTasks": watch.get("max_inflight", linear.get("max_inflight", 2)),
            "sortBy": "priority", "enabled": True,
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
    profile = ensure_claude_profile(api, conf)
    if conf.get("linear"):
        ensure_linear(api, ws, conf["linear"])
        ensure_watches(api, ws, conf, repos, profile)
    if changes:
        log(f"{len(changes)} change(s) applied")
    else:
        log("no changes; configuration already matches")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        print(f"kandev/configure: {err}", file=sys.stderr)
        sys.exit(1)
