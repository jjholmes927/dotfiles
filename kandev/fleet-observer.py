#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

B, ts = sys.argv[1], sys.argv[2]
WS_SEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ws-send.mjs")
STATE_FILE = os.environ.get("KANDEV_QUOTA_STATE", os.path.expanduser("~/.kandev/logs/quota-resume.json"))
FALLBACK_WAIT = int(os.environ.get("KANDEV_QUOTA_FALLBACK_SECONDS", "1800"))
RESET_BUFFER = 90
LINEAR_TO_KANDEV = {1: "high", 2: "high", 3: "medium", 4: "low"}
QUOTA_RE = re.compile(r"(?i)usage limit|limit reached|rate.?limit|too many requests|quota exceeded|\b429\b")
CONTINUE_PROMPT = ("You can continue now. Continue the task you were working on when the usage limit was reached; "
                   "do not repeat work that is already complete.")
STALL_STATES = {"WAITING_FOR_INPUT", "IDLE", "FAILED", "COMPLETED"}
DONE_TASK_STATES = {"COMPLETED", "CANCELLED"}


def get(path):
    with urllib.request.urlopen(B + path, timeout=20) as resp:
        return json.load(resp)


def patch(path, body):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode(), method="PATCH")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def out(*parts):
    print(ts, "|", *parts)


def parse_reset(text, now=None):
    now = now if now is not None else time.time()
    m = re.search(r"\|(\d{10})(?:\d{3})?\b", text) or re.search(r"(?i)reset[_ ]?(?:time|at)[:\s\"]+(\d{10})(?:\d{3})?\b", text)
    if m:
        return int(m.group(1)) + RESET_BUFFER
    m = re.search(r"(?i)retry.?after[:\s]+(\d+)\b", text)
    if m:
        return now + int(m.group(1)) + RESET_BUFFER
    m = re.search(r"(?i)resets?\s+in\s+(?:(\d+)\s*(?:d|day)s?\s*)?(?:(\d+)\s*(?:h|hr|hour)s?\s*)?(?:(\d+)\s*(?:m|min|minute)s?)?", text)
    if m and any(m.groups()):
        d, h, mi = (int(g or 0) for g in m.groups())
        return now + d * 86400 + h * 3600 + mi * 60 + RESET_BUFFER
    m = re.search(r"(?i)resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        lt = time.localtime(now)
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, minute, 0, 0, 0, -1))
        if target <= now:
            target += 86400
        return target + RESET_BUFFER
    return None


def load_state():
    try:
        with open(STATE_FILE) as fh:
            return json.load(fh)
    except Exception:
        return {"stalled": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE + ".tmp", "w") as fh:
        json.dump(state, fh, indent=1)
    os.replace(STATE_FILE + ".tmp", STATE_FILE)


def send_continue(task_id, session_id):
    res = subprocess.run(["node", WS_SEND, task_id, session_id, CONTINUE_PROMPT], capture_output=True, text=True, timeout=30)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout).strip()[:200])


def quota_check(state, task, session, msgs):
    stalled = state.setdefault("stalled", {})
    sid = session.get("id")
    if not sid:
        return
    turn = [m for m in msgs if m.get("type") in ("error", "message")]
    latest = turn[-1] if turn else None
    entry = stalled.get(sid)
    if session.get("state") in ("RUNNING", "STARTING"):
        if entry:
            out("QUOTA-RESUMED", task["id"][:8], sid[:8])
            del stalled[sid]
        return
    if not latest or latest.get("type") != "error" or not QUOTA_RE.search(str(latest.get("content") or "")):
        return
    if session.get("state") not in STALL_STATES or task.get("state") in DONE_TASK_STATES:
        return
    if entry and entry.get("error_msg_id") == latest.get("id"):
        return
    content = str(latest.get("content") or "")
    reset_at = parse_reset(content)
    parsed = reset_at is not None
    if reset_at is None:
        reset_at = time.time() + FALLBACK_WAIT
    stalled[sid] = {"task_id": task["id"], "error_msg_id": latest.get("id"), "reset_at": reset_at,
                    "parsed": parsed, "seen_at": time.time(), "sent_at": None, "attempts": entry.get("attempts", 0) + 1 if entry else 1}
    out("QUOTA-STALLED", task["id"][:8], sid[:8], "resume at", time.strftime("%H:%M", time.localtime(reset_at)),
        "(parsed)" if parsed else f"(unparsed, retry in {FALLBACK_WAIT // 60}m)", "|", content[:100].replace("\n", " "))


def quota_resume(state, live_sessions):
    stalled = state.setdefault("stalled", {})
    now = time.time()
    for sid in list(stalled):
        entry = stalled[sid]
        if sid not in live_sessions:
            del stalled[sid]
            continue
        if entry.get("sent_at") or now < entry["reset_at"]:
            continue
        try:
            send_continue(entry["task_id"], sid)
            entry["sent_at"] = now
            out("QUOTA-CONTINUE", entry["task_id"][:8], sid[:8], "attempt", entry.get("attempts"))
        except Exception as err:
            entry["reset_at"] = now + 300
            out("QUOTA-CONTINUE-FAILED", entry["task_id"][:8], sid[:8], str(err)[:160])


def main():
    try:
        workspaces = get("/api/v1/workspaces").get("workspaces", [])
    except Exception as err:
        out("FETCH-FAILED", err)
        return
    state = load_state()
    live_sessions = set()
    for ws in workspaces:
        wid = ws["id"]
        try:
            tasks = get(f"/api/v1/workspaces/{wid}/tasks").get("tasks", [])
        except Exception as err:
            out("TASKS-FAILED", wid[:8], err)
            continue
        for t in tasks:
            tid = t["id"]
            title = t.get("title") or ""
            try:
                sessions = get(f"/api/v1/tasks/{tid}/sessions").get("sessions", [])
            except Exception:
                sessions = []
            s = sessions[0] if sessions else {}
            q, n, last, msgs = "-", 0, "", []
            if s:
                live_sessions.add(s.get("id"))
                try:
                    msgs = get(f"/api/v1/agent-sessions/{s['id']}/messages").get("messages", [])
                    cl = [m for m in msgs if m.get("type") == "clarification_request"]
                    q = ((cl[-1].get("metadata") or {}).get("status") or "?") if cl else "-"
                    texts = [m for m in msgs if m.get("type") == "message"]
                    last = (str(texts[-1].get("content")) if texts else "")[:90].replace("\n", " ")
                    n = len(msgs)
                except Exception:
                    n = -1
            out(tid[:8], "|", t.get("state"), "|", s.get("state", "-"), f"| q={q} | n={n} |", title[:45], "|", last)
            if s and msgs:
                try:
                    quota_check(state, t, s, msgs)
                except Exception as err:
                    out("QUOTA-CHECK-FAILED", tid[:8], str(err)[:120])

            ticket = re.match(r"\[([A-Z]+-\d+)\]", title)
            if ticket:
                try:
                    issue = get(f"/api/v1/linear/issues/{ticket.group(1)}?workspace_id={wid}")
                    issue = issue.get("issue", issue)
                    wanted = LINEAR_TO_KANDEV.get(issue.get("priority"))
                    if wanted and t.get("priority") != wanted:
                        patch(f"/api/v1/tasks/{tid}", {"priority": wanted})
                        out("PRIORITY", tid[:8], ticket.group(1), t.get("priority"), "->", wanted)
                except Exception as err:
                    out("PRIORITY-SYNC-FAILED", tid[:8], str(err)[:120])
        try:
            for w in get(f"/api/v1/linear/watches/issue?workspace_id={wid}").get("watches", []):
                if w.get("lastError"):
                    out("WATCH", w["id"][:8], "| error:", w["lastError"][:120])
        except Exception:
            pass
    quota_resume(state, live_sessions)
    save_state(state)


if __name__ == "__main__":
    main()
