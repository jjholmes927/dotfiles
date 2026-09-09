# What shapes the AI output I read

> **TL;DR** Every surface I read from Claude has a written rule set with a hard cap. Chat rules live in an output style. Where content goes and how findings are told live in my global CLAUDE.md. PR bodies, review comments, plans and Linear findings each have their own skill. Five ideas run through all of it: answer first, bold carries the point, cap the length, visual over prose, never trim a warning.

Audited 2026-09-08. Repos: [dotfiles](https://github.com/jjholmes927/dotfiles), [jjholmes927-claude-skills](https://github.com/jjholmes927/jjholmes927-claude-skills), [beam-claude-skills](https://github.com/wearebeam/beam-claude-skills), magicnotes `docs/`.

## The map

| What I read | What shapes it | Cap |
|---|---|---|
| Chat reply | `attention-kind` output style + CLAUDE.md comms rules | Answer in line one, short by default |
| Kandev chat, plans, Linear comments, PR bodies | CLAUDE.md rule 5 + Kandev ADHD theme | One TL;DR blockquote, max 2 emoji |
| Findings and data | CLAUDE.md rule 4 + `investigate` skill | Headline 8 lines, 300 words above `Detail` |
| Reports, designs, audits | CLAUDE.md rules 1 to 3 | Never in chat. Doc or Artifact, chat is 3 to 5 lines + link |
| Implementation plan | CLAUDE.md plan-review rule + `e2e` Stage 1 | Artifact with visual and raw tabs, chat 3 to 5 lines |
| PR description | `writing-pr-descriptions` skill + `docs/pull-requests.md` | What/Why, 3 bullets each, 10 lines total |
| AI Code Review comment | `beam-claude-skills` `/review-pr` | Collapsed per severity, max 10 findings |
| Leadership or non-tech message | `/newspaper` | Headline 10 words, impact 2 sentences, 5 detail bullets |
| Verification report | `/verify` | Three statuses only, evidence pasted, silence banned |
| Morning brief | `/brief` | 200 words, 3 items per section |

## Chat

**Where:** `claude/output-styles/attention-kind.md` in dotfiles, from [attention-span](https://github.com/alexgreensh/attention-span). Set via `outputStyle` in `settings.json`. `/style` swaps to `spartan` or `rundown`.

**Why a style, not CLAUDE.md:** it replaces the default tone instead of fighting it, and swaps per project without touching anything else.

**The rules that do the work:**

- Answer or fix in line one. No preamble.
- Bold lead-in on every point. Reading only the bold must give the whole answer, including any warning.
- Arrow paragraphs with a blank line between, not tight bullets. Terminal markdown squashes lists.
- Short by default. Cut elaboration, never an essential step or a warning.
- Expand only where a mistake would cost me something.
- One question at a time.
- Plain English. Tag jargon in five words. Never assume I remember an acronym.
- No filler openers, no rhetorical questions, no em-dashes.

CLAUDE.md adds the bit the style can't know: the same rules apply to files and Artifacts, not just chat.

## Rendered markdown (Kandev, Linear, PR bodies)

CLAUDE.md rule 5. Open with one `> **TL;DR**` blockquote. A warning is a blockquote starting `*Warning:*`. No other blockquotes. Max two emoji, always next to a text label. Gate questions open `**Decision needed:**` and use only paragraphs, lists and inline bold, because the Kandev question widget renders nothing else.

**Rendering side:** the Kandev ADHD theme (`kandev/plugins/adhd-theme`) gives bold lead-ins an accent colour, turns blockquotes into callouts, widens line spacing and caps text at 72 characters wide. The 72ch measure was the single biggest win. Any surface we control should do the same.

## Findings are a story, not a number

CLAUDE.md rule 4. Order: the user-facing problem, what the feature does, define each domain word once, derive the headline number and show the sum, why it can or can't be trusted, one honest line. Evidence tables after. Never open with "74% accept rate".

The `investigate` skill tightens this for Linear: headline block 8 lines, 300 words above `Detail`, every claim has a link or id or is tagged `not verified`, any source I couldn't reach sits in the headline as `not checked`.

## Plans

Always an Artifact, never a wall of chat. Problem as a diagram, a table of what changes vs what's guarded, task cards with effort badges, audit trail, approve bar top and bottom, plus a "Raw plan" tab with the full markdown. Chat stays 3 to 5 lines.

One exception: small internal plans (no user-facing change, under 3 tasks, nothing graded high) skip the Artifact and go straight to Approve/Revise.

## PR descriptions

**Where:** `writing-pr-descriptions` skill owns the rules. `VOICE.md` next to it holds my tone, mined from 100 PRs and 111 review threads. `docs/pull-requests.md` in magicnotes is the team copy, enforced by Danger at 40 lines or 500 words.

**Format:** `**What**` then `**Why**` as bold inline headers. Each is 3 bullets or 2 to 3 short sentences. Whole body about 10 lines. Bug fixes add numbered repro steps ending "Before: X. After: Y." UI changes get a captioned screenshot. Stacked PRs get one line at the top pointing at the PR that tells the story.

**Rules and why:**

- One idea per sentence. A 70-word sentence passes the cap and fails the reader.
- Outcome, not inventory. The diff already lists the functions.
- No `## Summary`, `## Changes`, test-plan checklists or AI footers. That's raw agent output I forgot to rewrite.
- "Worth noting" only for repro, deploy actions or deferred follow-ups. Otherwise leave it out.
- Ticket in the title bracket, not a "Fixes" footer.

**Two voices, kept apart.** PR bodies are polished and emoji-free. My review comments on other people's PRs are casual, warm, question-framed and full of emoji. Mixing them reads as not me.

## AI Code Review comments

`beam-claude-skills/commands/review-pr.md`. Lives in the team repo because magicnotes CI reads that file as its review instructions. Headline with counts, one collapsed block per severity, three-column table (number, finding with file ref underneath, impact), footer naming which lenses ran. Finding 18 words, impact 25, max 10 findings. Landed after four format rounds on PR #7211; the receipts are in `claude/skill-feedback.md`.

## Newspaper, verify, brief

**`/newspaper`** for anyone non-technical: headline of 10 words that is the outcome, impact in 2 sentences in the reader's terms, up to 5 detail bullets as "detail in thread". Questions in the first two lines. Never adds content the draft didn't have.

**`/verify`**: every promise gets one of three statuses. Verified with the output pasted. Partially verified with what's missing and where it gets proven. Not verifiable with the reason and a post-ship plan. Skipping without saying so is a failure.

**`/brief`**: 200 words, four fixed sections, warnings outrank everything, a blocked person outranks a blocked ticket, third appearance of an item must propose escalation or a kill.

## Start here

Take the output style and the CLAUDE.md "Communication Style" section first. They shape every reply. Then the PR description skill. The rest can follow as each artefact comes up.
