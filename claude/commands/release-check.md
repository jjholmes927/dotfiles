---
description: "Release-readiness audit before a feature or flag rollout: tests, observability, alerts, Sentry, flag state, rollback. Run from the product repo before anything goes past internal."
argument-hint: <feature / PR / flag name>
---

# Release Check — /release-check <feature>

Goal: **the next incident is caught by an alert, not by commercial.** Verify every row with real evidence (run the command, query the system) — never from memory.

| # | Check | How |
|---|-------|-----|
| 1 | **Tests** | Suite green on main; new behaviour actually covered — name the test files |
| 2 | **Observability** | Spans/metrics exist for the new path — query Honeycomb for the new span/attribute; nothing emitting = ❌ |
| 3 | **Alerts** | A trigger/SLO would fire if this breaks — name it. If none exists, draft one and propose it (create nothing without approval) |
| 4 | **Sentry** | New/unresolved issues in the affected area this week; triage owner assigned |
| 5 | **Flag state** | LaunchDarkly: flag exists, rollout plan (internal → % → all), any stale flags to clean up |
| 6 | **Rollback** | One-line rollback path: flag off / revert / migration-safe? |
| 7 | **Comms** | Does support/commercial need a heads-up? If yes, draft it via /newspaper |

Output:
- ✅/⚠️/❌ table with one line of evidence per row
- Verdict: **SHIP / SHIP WITH FOLLOW-UPS / DON'T SHIP YET**
- A ≤6-line newspaper-style summary Joel can paste to the team channel
- If a checker (Honeycomb/Sentry/LaunchDarkly) is unreachable, mark the row ⚠️ UNVERIFIED — never silently skip it.
