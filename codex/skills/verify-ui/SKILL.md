---
name: verify-ui
description: Verify a UI flow against a live dev server using browser automation. Use when the user says verify ui, check the ui, verify a page, or wants a quick non-destructive browser sanity check.
---

# Verify UI

Verify a UI flow against a live dev server.

## Safety

This is read-only verification.

- Do not submit destructive forms.
- Do not click delete, remove, or confirm destructive actions.
- Prefer navigation, viewing, and non-destructive form fills.

## Workflow

1. Check that the dev server is running.
2. Ensure browser automation is available:
   - prefer a local `agent-browser` install if present
   - otherwise use `npx agent-browser`
3. Open the target page on the local dev server.
4. Wait for the page to settle after navigation.
5. Validate the flow the user asked about.
6. Report what worked, what failed, and any screenshots or output paths that matter.

## Commands

Typical flow:

```bash
curl -s -o /dev/null -w '%{http_code}' http://localhost:3000
npx agent-browser open http://localhost:3000/<path>
npx agent-browser wait --load networkidle
npx agent-browser snapshot -i
```

If the dev server is not running, tell the user to start it and stop.
