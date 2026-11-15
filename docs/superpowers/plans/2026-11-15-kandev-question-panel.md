# Kandev question panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Kandev's question panel readable and answerable, and keep the agent's reply to your last answer in view, via ADHD theme 0.5.0 plus one CLAUDE.md rule.

**Architecture:** CSS in `ui/theme.css` keyed on Kandev's `data-testid` hooks. `ui/bundle.js` gains two pure helpers (reply selection, markdown-to-text) and DOM wiring that pins the replies above each open question. Replies come from `GET /api/v1/task-sessions/<id>/messages?sort=desc&limit=100`; any failure renders nothing.

**Tech Stack:** plain browser JS (Kandev plugin bundle), CSS, Node's built-in `node:test` + `node:vm` for the pure helpers.

**Spec:** `docs/superpowers/specs/2026-11-15-kandev-question-panel-design.md`

## Global Constraints

- No code comments (repo rule).
- Plugin id `jjholmes927-adhd-theme`; manifest `version: "0.5.0"`.
- Reply text renders with `textContent` only, never `innerHTML`.
- The messages API rejects `author_type=agent`; filter client side.
- Colours reuse theme tokens: `--adhd-ask` (purple), `--adhd-tldr` (green).

## Review Focus

- **First question after long autonomous work** (no earlier answer or user message within 100 messages): no pin. Test in Task 1.
- **Several agent messages since the answer**: collapsed shows the newest; "Show all" lists every one, oldest first. Test in Task 1.
- **Question replaced by a new one in the same overlay**: the pin refreshes, keyed on the question text. Live check in Task 3.
- **API error or no session id**: no pin, no console error. Test in Task 1 (empty input) and live check in Task 3.
- **No pending question**: the queue composer is not faded. Live check in Task 3.

---

### Task 1: Reply selection helpers + pin wiring

**Files:**
- Modify: `kandev/plugins/adhd-theme/ui/bundle.js`
- Test: `kandev/plugins/adhd-theme/test/bundle.test.mjs`
- Modify: `.github/workflows/tests.yml` (job `adhd-theme`: checkout, `node --test kandev/plugins/adhd-theme/test/bundle.test.mjs`)

**Interfaces:**
- Produces: `repliesSinceLastAnswer(messagesNewestFirst) -> string[]` (agent `message` contents between the newest `clarification_request` and the next older `clarification_request` or user message, oldest first; `[]` when either end is missing). `toPlainText(markdown) -> string` (drops `**`, `__`, backticks, leading `#`/`>`, keeps link text, keeps line breaks). DOM: `.adhd-pin`, `.adhd-pin-head`, `.adhd-pin-body`, `.adhd-pin-toggle`, `.adhd-pin.adhd-pin-open`; options get `.adhd-recommended` when their label contains "recommended"; `.adhd-own-label` before `[data-testid="clarification-custom-input"]`.

- [ ] **Step 1: Write failing tests** loading `bundle.js` into a `vm` context with stub `window.registerKandevPlugin`, `document`, `MutationObserver`, `requestAnimationFrame`, `localStorage`:
  - `replies between answer and question, oldest first`: `[q(pending), msg("b"), tool, msg("a"), q(answered)]` → `["a","b"]`
  - `stops at a user message`: `[q, msg("b"), user("go"), msg("a")]` → `["b"]`
  - `no earlier boundary means no pin`: `[q, msg("a"), msg("b")]` → `[]`
  - `no question means no pin`: `[msg("a"), q]`… newest item not reachable → uses newest question; `[]` input → `[]`
  - `toPlainText("**Done:** see [plan](http://x) \`a\`")` → `"Done: see plan a"`
- [ ] **Step 2:** `node --test kandev/plugins/adhd-theme/test/bundle.test.mjs` → FAIL (functions undefined)
- [ ] **Step 3:** implement both helpers, then `pinReplies(document)` called from `schedule()`/`initialize()`: per overlay, key = question card text; if key changed, fetch, build pin, insert before `clarification-context` (else first question card); "Show all"/"Show less" toggles `.adhd-pin-open`; `destroy()` removes pins and labels.
- [ ] **Step 4:** tests PASS
- [ ] **Step 5:** commit `feat: Pin the agent's replies above Kandev questions`

### Task 2: Restyle the panel + ship 0.5.0

**Files:**
- Modify: `kandev/plugins/adhd-theme/ui/theme.css`, `kandev/plugins/adhd-theme/manifest.yaml` (0.5.0, description mentions the question panel), `docs/kandev-setup.md` (theme paragraph), `claude/CLAUDE.md` (rule 4: a Kandev question must make sense without the chat behind it)

- [ ] **Step 1:** CSS: overlay top border `--adhd-ask`; context 15px/1.6, max 72ch; title as small uppercase purple label; prompt 19px semibold; options min-height 52px, radius 10px, centred; `kbd` as a 26px chip; label 16px; description 14px; `.adhd-recommended` tinted purple; submit button purple; `.adhd-own-label`; `[data-session-id]:has([data-testid="clarification-overlay"]) [data-testid="chat-input-editor-shell"]` at 0.55 opacity, full on `:focus-within`; `.adhd-pin` green-tinted card, body clamped to 2 lines, open state scrolls at 40vh max.
- [ ] **Step 2:** `kandev/plugins/install-plugin.sh adhd-theme` → "staged jjholmes927-adhd-theme@0.5.0", "enabled"
- [ ] **Step 3:** commit `feat: Restyle Kandev's question panel in the ADHD theme (0.5.0)`

### Task 3: Verify in the live Kandev

- [ ] Before/after screenshots of the NEV-268 pending question (read only, never click an option).
- [ ] Live checks from Review Focus: pin absent on NEV-268 (first gate), present on a session whose question follows an answer; composer fades only with a question open; no console errors.
