---
description: "Verify a UI flow using agent-browser against the live dev server. Use when the user says 'verify ui', 'check the ui', or 'verify-ui'."
disable-model-invocation: true
argument-hint: [what to verify, e.g. "the login page renders correctly"]
---

You are verifying a UI flow using `agent-browser` (Vercel's browser automation CLI for AI agents).

Use this for quick visual sanity checks during development. For deterministic regression tests, write a Playwright E2E test instead.

**What to verify:** $ARGUMENTS

**IMPORTANT: This is READ-ONLY verification. Do NOT submit forms that create, update, or delete data. Do NOT click 'Delete', 'Remove', or 'Confirm' on destructive actions. Only interact with navigation, viewing, and non-destructive form fills.**

## Steps

### 0. Verify dev server is running

Check if the dev server is running on port 3000:

```bash
curl -s -o /dev/null -w '%{http_code}' http://localhost:3000 || echo "NOT RUNNING"
```

If not running, tell the user to start it with `bin/dev` and stop.

### 1. Ensure agent-browser is available

Check if agent-browser is available by running `npx agent-browser --version`. If it fails, run `npx agent-browser install`.

### 2. Open the target page

The dev server runs on `http://localhost:3000`. Open the relevant page:

```bash
npx agent-browser open http://localhost:3000/<path>
npx agent-browser wait --load networkidle
```

Always run `wait --load networkidle` after `open` commands — this ensures SPA/Inertia apps have fully hydrated.

If the page requires authentication, navigate through the login flow first. For authentication, use the `agent-browser@test.com` test account. Navigate to `/login`, fill the email, then open `/letter_opener` to click the magic link. See CLAUDE.md for full details.

### 3. Take a snapshot to understand the page

```bash
npx agent-browser snapshot -i
```

Use `snapshot -i` (interactive elements only) as the default to reduce noise. Use bare `snapshot` when you need the full accessibility tree.

This returns an accessibility tree with element refs (`@e1`, `@e2`, etc.). Use these refs for interactions, or use semantic `find` commands. Note that `find` returns element refs you can chain with actions:

```bash
npx agent-browser find role button --name "Submit" click
npx agent-browser find text "Sign In" click
npx agent-browser find label "Email" fill "test@example.com"
```

### 4. Perform the verification

Navigate through the flow described above. Use these commands:

- **Click:** `npx agent-browser click @e2` or `npx agent-browser find text "Button text" click`
- **Fill inputs:** `npx agent-browser fill @e3 "text"` or `npx agent-browser find label "Email" fill "test@example.com"`
- **Check visibility:** `npx agent-browser is visible @e5`
- **Wait for content:** `npx agent-browser wait --text "Expected text"`
- **Get text:** `npx agent-browser get text @e4`

After any page navigation or significant DOM change, take a fresh `snapshot -i` — element refs (`@e1`, `@e2`) go stale after the page changes.

### 5. Take screenshots for evidence

```bash
npx agent-browser screenshot /tmp/verify-ui-step1.png
```

Use timestamped filenames per step (e.g. `/tmp/verify-ui-step1.png`, `/tmp/verify-ui-step2.png`) so earlier screenshots are not overwritten.

Use the `--annotate` flag to get labeled screenshots with element refs overlaid. Use the `--full` flag to capture the full scrollable page, not just the viewport.

Use the Read tool to view the screenshot and confirm visual correctness.

### 6. Report findings

Summarize:
- What was verified
- What passed
- What failed or looked unexpected
- Screenshots taken

### 7. Cleanup

```bash
npx agent-browser close
```

Shut down the browser daemon when verification is complete.

## Error Handling

- If `agent-browser install` fails, report the error and stop.
- If the dev server is not running on port 3000, tell the user to start it with `bin/dev`.
- If an element is not found or a command times out after 10 seconds, take a screenshot of the current state, report what failed, and attempt to continue with remaining checks.
- If you have attempted the same action 3 times without success, take a screenshot, report the failure, and move on.
- After any page navigation or significant DOM change, take a fresh snapshot — element refs (@e1, @e2) go stale.

## Guidelines

- **Use semantic locators** (`find role`, `find text`, `find label`) over refs when possible — they're more readable and resilient
- **Wait for async content** before asserting — use `npx agent-browser wait --text "..."` or `npx agent-browser wait --load networkidle`
- **Take screenshots at key moments** — after page load, after interactions, at the end
- **Don't modify data** — this verifies against the live dev server state. If you need controlled data, use Playwright E2E tests instead
- **Auth flows** — if verification requires a logged-in user, navigate through the login flow or check if there's an active session first
