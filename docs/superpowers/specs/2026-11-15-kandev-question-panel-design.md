# Kandev question panel: readable, answerable, reply kept in view

> **TL;DR** ADHD theme 0.5.0 restyles Kandev's question panel (option B) and pins the agent's latest reply, two lines with "Show all", to the top of each question (option D). A CLAUDE.md rule makes every Kandev question stand on its own.

## Why

- **Reading**: the panel is cramped, small and dense.
- **Answering**: option cards, the custom answer box and the "Queue instructions" composer look alike.
- **Flow**: Kandev's tool tells agents to put explanations in chat before the question; every new question then re-opens the panel over that reply, and tool calls push it further away.

## Goals / non-goals

| Goals | Non-goals |
|---|---|
| Bigger, calmer question text and clear option rows | Replacing Kandev's panel or answering through a plugin (Kandev blocks plugin answers) |
| The agent's latest reply readable without closing the panel | Changing when Kandev opens the panel |
| Fail safe: if the pin can't find the reply, the panel is just restyled | Upstream Kandev changes |

## Approaches (picked: B + D)

| Option | Trade-off |
|---|---|
| B: CSS restyle only | Sturdiest; reply still hidden |
| C: B + collapse each new question to a slim bar | One extra click per question |
| D: B + pin the last reply in the panel | **Picked with B.** No extra click; reads the reply from Kandev's messages API, not the page layout |

## Design

- **CSS (`ui/theme.css`)**, scoped to Kandev's stable `data-testid` hooks (`clarification-overlay`, `clarification-question-card`, `clarification-question-title`, `clarification-context`): question title larger, option rows with a number chip, the recommended option tinted purple, custom answer box labelled, queue composer faded while a question is open.
- **Script (`ui/bundle.js`)**: when a clarification overlay appears, read the session id from the chat panel's `data-session-id`, fetch `GET /api/v1/task-sessions/<id>/messages?author_type=agent&sort=desc&limit=40`, take the newest agent `message` before the question, render it at the top of the overlay clamped to two lines with a "Show all" toggle. Any failure renders nothing.
- **Rule (global CLAUDE.md, rule 4)**: a Kandev question must make sense without the chat behind it.
- **Ships as** ADHD theme 0.5.0 via `kandev/plugins/install-plugin.sh adhd-theme` (run by `kandev/install.sh` on every laptop).

## Left to the builder

Exact selectors inside the overlay (option buttons, custom input, queue composer) come from the live DOM; colours reuse the theme's existing tokens.
