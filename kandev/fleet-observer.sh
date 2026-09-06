#!/usr/bin/env bash
set -uo pipefail

B="${KANDEV_BASE:-http://127.0.0.1:38429}"
LOG="${KANDEV_OBSERVER_LOG:-$HOME/.kandev/logs/fleet-observer.log}"
INTERVAL="${KANDEV_OBSERVER_INTERVAL:-60}"
mkdir -p "$(dirname "$LOG")"

while true; do
  ts=$(date -u +%FT%TZ)
  python3 - "$B" "$ts" >> "$LOG" 2>&1 <<'PY'
import json, re, sys, urllib.request

B, ts = sys.argv[1], sys.argv[2]
LINEAR_TO_KANDEV = {1: "high", 2: "high", 3: "medium", 4: "low"}


def get(path):
    with urllib.request.urlopen(B + path, timeout=20) as resp:
        return json.load(resp)


def patch(path, body):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode(), method="PATCH")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


try:
    workspaces = get("/api/v1/workspaces").get("workspaces", [])
except Exception as err:
    print(ts, "FETCH-FAILED", err)
    sys.exit()

for ws in workspaces:
    wid = ws["id"]
    try:
        tasks = get(f"/api/v1/workspaces/{wid}/tasks").get("tasks", [])
    except Exception as err:
        print(ts, "| TASKS-FAILED", wid[:8], err)
        continue
    for t in tasks:
        tid = t["id"]
        title = t.get("title") or ""
        try:
            sessions = get(f"/api/v1/tasks/{tid}/sessions").get("sessions", [])
        except Exception:
            sessions = []
        s = sessions[0] if sessions else {}
        q, n, last = "-", 0, ""
        if s:
            try:
                msgs = get(f"/api/v1/agent-sessions/{s['id']}/messages").get("messages", [])
                cl = [m for m in msgs if m.get("type") == "clarification_request"]
                q = ((cl[-1].get("metadata") or {}).get("status") or "?") if cl else "-"
                texts = [m for m in msgs if m.get("type") == "message"]
                last = (str(texts[-1].get("content")) if texts else "")[:90].replace("\n", " ")
                n = len(msgs)
            except Exception:
                n = -1
        print(ts, "|", tid[:8], "|", t.get("state"), "|", s.get("state", "-"), f"| q={q} | n={n} |", title[:45], "|", last)

        ticket = re.match(r"\[([A-Z]+-\d+)\]", title)
        if ticket:
            try:
                issue = get(f"/api/v1/linear/issues/{ticket.group(1)}?workspace_id={wid}")
                issue = issue.get("issue", issue)
                wanted = LINEAR_TO_KANDEV.get(issue.get("priority"))
                if wanted and t.get("priority") != wanted:
                    patch(f"/api/v1/tasks/{tid}", {"priority": wanted})
                    print(ts, "| PRIORITY", tid[:8], ticket.group(1), t.get("priority"), "->", wanted)
            except Exception as err:
                print(ts, "| PRIORITY-SYNC-FAILED", tid[:8], str(err)[:120])
    try:
        for w in get(f"/api/v1/linear/watches/issue?workspace_id={wid}").get("watches", []):
            if w.get("lastError"):
                print(ts, "| WATCH", w["id"][:8], "| error:", w["lastError"][:120])
    except Exception:
        pass
PY
  sleep "$INTERVAL"
done
