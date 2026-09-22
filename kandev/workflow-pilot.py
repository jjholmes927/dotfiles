import argparse
import json
from pathlib import Path

from configure import Api, ensure_workspace, select_agent_profile


def document(agent, model, mode=None):
    profile = {"agent_name": agent, "model": model}
    if mode:
        profile["mode"] = mode
    work_prompt = (
        "Use the installed /e2e workflow with --execution direct --review codex. "
        "Use Kandev's plan and question tools. The plan approval must explicitly "
        "authorize the separate read-only review route before invoking it; if "
        "permission is missing, stop at that decision. Record requested models "
        "and actual identities where observable. Read E2E_REVIEWER_MODEL from "
        "the task's explicit selection or the user's configured Codex model and "
        "pass it explicitly. Same-model review is fresh-context, not model diversity. "
        "On resume read the approved plan, current Git state and .e2e/handoff.md. "
        "Only call step_complete_kandev after every intended PR has its own "
        "verification/size/readiness evidence, required CI result and findings "
        "disposition, and all authorized ticket moves are read back. No pending "
        "question, missing review, cancelled work or failed required check is "
        "completion. Do not merge or deploy."
    )
    steps = []
    for position, (name, prompt) in enumerate([
        ("E2E", work_prompt),
        ("PR review", "Human review boundary. Report PR evidence and outstanding decisions. Do not auto-merge, auto-deploy or move to Done; a human chooses the next action."),
        ("Done", "Record the actual merge/release outcome when authorized and evidenced. A PR-ready report alone does not establish deployment or production success."),
    ]):
        steps.append({
            "name": name, "position": position, "color": "blue" if position == 0 else "gray",
            "prompt": prompt, "is_start_step": position == 0,
            "show_in_command_panel": True, "allow_manual_move": True,
            "agent_profile": profile,
            "auto_advance_requires_signal": True, "cancel_triggers_turn_complete": False,
            "events": {"on_turn_complete": [{"type": "move_to_next"}]} if position == 0 else {},
        })
    return {"version": 1, "type": "kandev_workflow", "workflows": [{
        "name": "Portable E2E pilot", "description": "Opt-in evidence-gated delivery; no automatic intake or merge.",
        "agent_profile": profile, "steps": steps,
    }]}


def main():
    parser = argparse.ArgumentParser(description="Prepare an opt-in Kandev workflow without changing the default or watches")
    parser.add_argument("--base", default="http://127.0.0.1:38429")
    parser.add_argument("--workspace", default="Default Workspace")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    api = Api(args.base)
    workspace = ensure_workspace(api, {"workspace": args.workspace})
    selection = {"agent": args.agent, "model": args.model}
    if args.mode:
        selection["mode"] = args.mode
    selected = select_agent_profile(api, selection)
    data = document(selected["agent_display_name"], selected["model"], selected.get("mode"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    if args.apply:
        existing = api.call("GET", f"/api/v1/workspaces/{workspace['id']}/workflows").get("workflows", [])
        if any(w["name"] == data["workflows"][0]["name"] for w in existing):
            raise RuntimeError("Pilot already exists; inspect it before replacing any configuration")
        result = api.call("POST", f"/api/v1/workspaces/{workspace['id']}/workflows/import", data)
        workflows = api.call("GET", f"/api/v1/workspaces/{workspace['id']}/workflows")["workflows"]
        created = next(w for w in workflows if w["name"] == data["workflows"][0]["name"])
        steps = api.call("GET", f"/api/v1/workflows/{created['id']}/workflow/steps")["steps"]
        if len(steps) != 3 or any(s.get("agent_profile_id") != selected["id"] or not s.get("auto_advance_requires_signal") or s.get("cancel_triggers_turn_complete") for s in steps):
            raise RuntimeError("Pilot imported but profile/signal read-back differs; do not start tasks until corrected")
        print(json.dumps(result, indent=2))
    else:
        print(f"Prepared {args.output}; no Kandev configuration changed")


if __name__ == "__main__":
    main()
