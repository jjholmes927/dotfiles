# Every-change flow: one loop for every change, principles applied while writing

> **TL;DR** Two new joel-workflow skills. `making-changes` fires on every implementation that isn't pure research: write-time rules, tests, verify, and a fresh review only when the change is risky. e2e calls it for each task. `good-code` becomes the one home for the 13 principles, revealing more detail as risk rises, and both writing and review read it. A findings ledger ships first, so a baseline exists before anything changes and we can prove problems move from review to writing.

## Why

- **Writing gets little of the checklist.** Only #2 small units, #3 reuse and #11 tests shape code as it's written. Everything else waits for `good-code-review` at e2e Stage 6. The `writing-good-tests` check (28 Nov 2026) showed rules given at write time fix problems before review.
- **Small changes miss the safety net.** `verify`, `verify-ui` and good-code only run reliably inside e2e, which pushes small changes into tickets that don't need one.
- **The checklist lives on one laptop.** `life-vault/06-principles/good-code.md` isn't available where the skills run (Codex, Cursor, cloud sessions, maybe the work laptop). A second, hand-kept copy would drift.
- **Opinions evolve.** They need one place to edit, and evidence of whether an edit helped.

## Goals, non-goals, anti-goals

| Goals | Non-goals |
|---|---|
| Every non-research change runs the same loop, in Claude, Codex, Cursor and OpenCode | The visual dashboard itself (project B), beyond the data it needs |
| One home for the principles, read at write time and review time | Rethinking superpowers in the flow (separate discussion) |
| Evidence that problems are caught earlier, without changes getting slower | Changing ship's pipeline or e2e Stage 6's branch review |
| Nothing manual without an automatic reminder | A hook that forces verify (deferred until data shows skipping) |

**Anti-goals** (failure even if it technically works):
- **Every one-line edit waits minutes** for a review.
- **Agents silently skip it**, so invocation stays low.
- **Two copies of the principles drift** apart.
- **The new flow "wins" only because its judge shares its checklist.**

## Approaches

**Where the every-change loop lives**

| Option | Trade-off |
|---|---|
| Instructions only, in each harness's global file | Rejected: text per harness, skimmed mid-session, not portable |
| **A skill plus one synced pointer line (picked)** | One home, installed everywhere by `workflow-sync`; e2e reuses it per task |
| The skill plus a Stop hook that blocks until verify ran | Deferred: Claude-only and may nag; add if the ledger shows verify being skipped |

**Where the principles live**

| Option | Trade-off |
|---|---|
| **One `good-code` skill with progressive disclosure (picked)** | One home, ranking kept, public; detail loads only when the change needs it |
| 13 small skills, one per principle | 13 triggers competing, and "higher principle wins" is lost |
| life-vault stays the source, copied at sync | The copy step can fail silently; content is published anyway |

**How heavy the per-change review is**

| Option | Trade-off |
|---|---|
| Light: self-check only | Fastest; the agent marks its own homework |
| **Risk-triggered (picked)** | Self-check always; a fresh reviewer only where mistakes are costly |
| Heavy: both review lenses on every change | Catches most; minutes on every edit, so it gets dodged |

## Design

### 1. `good-code` skill

- **`SKILL.md`**: the 13 principles in rank order, one line each. Higher-ranked wins a conflict; correctness, security and required behaviour are never traded. The repository's own guide wins where it disagrees. A "read more when" table routes to references by observable triggers.
- **One reference file per principle**, each with two sections: **While writing** (Flag / Write instead rules, the `writing-good-tests` format) and **When reviewing** (the checklist's existing review questions). Plus references for performance habits, every-PR rules, the symptom table and the evidence rules for reviewing.
- **Always read for any code change** (the write-time core): #1 names and no magic values, #2 small units, #3 reuse, #7 validate at the edge, #10 fail loudly, #13 follow the repository's patterns.
- **#13 rule:** find two or three existing examples and follow the best (documented, recent, or in the healthiest code). If they disagree, or the only example breaks a higher principle, don't silently copy or diverge: name both, say which you picked and why, and flag it as uncertain.
- **Read only when triggered:**

| Trigger in the change | Reference |
|---|---|
| Adds or changes a table, migration or saved format | #6 data model |
| Touches permissions, user input, uploads, model output or secrets | #8 trust boundaries |
| Adds jobs, webhooks, retries, payments or form submits | #9 safe to run twice |
| About to build a mechanic that already exists elsewhere | #12 generic core |
| Spans several modules for one feature | #4 keep change local |
| Adds queries, lists or external calls | Performance |

- **Three dials decide what applies:**

| Dial | Decides | Driven by |
|---|---|---|
| What the change touches | Which references load | The trigger table above |
| What the code measures | Going deeper on upkeep (#2, #3, #12, #13) | Quality signals on the changed files: a complex, poorly tested function (crapper), a duplicate touching a changed file (dryer), a file growing past ~300 lines, a new dependency, a second way of doing something the repo already does |
| How risky or big it is | A fresh reviewer (step 7) | Risk triggers or more than ~150 changed lines; a strong quality signal also escalates |

- **Manual override:** naming a principle in the request ("go deep on #12") loads its reference.
- **Migration:** content moves from life-vault, with the Beam/Interpret history removed. life-vault keeps a pointer plus the private history.
- **`good-code-review` reads these files** instead of life-vault. The `$GOOD_CODE_CHECKLIST` override stays.

### 2. `making-changes` skill

- **Fires on** any implementation, fix, refactor, config or docs change. Not on research or questions.
- **The loop, scaled by size:**
  1. **Size it.** Docs or config only: verify and report. Any code: the full loop.
  2. **Load rules:** the `good-code` core plus any triggered references.
  3. **Tests first:** `writing-good-tests`, with superpowers TDD when installed.
  4. **Smallest change:** `ponytail` when installed.
  5. **Verify:** `verify`, which routes UI work to `verify-ui`.
  6. **Self-check:** run `quality-signals.sh` on the changed files, load any upkeep references its signals call for, then check the diff against all loaded rules and fix what it finds.
  7. **Risk review:** if a trigger fired or more than ~150 lines changed, run `good-code-review` in a fresh read-only context, and fix P1 and P2 findings.
  8. **Report:** `Change: <size> · rules <loaded> · tests <K of T seen failing> · verify <verdict> · review <skipped | N findings>`. Commit only when the user or the calling workflow authorised it; otherwise propose the message.
  9. **Log findings** (section 4).
- **e2e:** Stages 3 and 4 become "run `making-changes` for each task". The implementer brief keeps the route, permission and handoff details. Stage 6 is unchanged.
- **e2e A/B test: when the second review happens.**
  - **A, review at the end (default):** each task runs steps 1 to 6, 8 and 9, but not step 7. Stage 6 reviews the whole branch as today.
  - **B, review as you go:** each task also runs step 7 when its risk trigger fires, using e2e's existing per-task review option, with Stage 5's "no reviewers mid-build" rule adjusted to allow it. On the Codex route, where implementers can't start reviewers, the coordinator runs step 7 on the task's commit.
  - **Repairs** during Stage 6 and CI run steps 1 to 6 in both arms.
  - **Assignment is automatic:** e2e alternates A and B by ticket and logs the arm with every finding, plus minutes and tokens per run.
  - **Benchmark:** one multi-task build case runs 5 times in each arm.
  - **Decision:** after 10 tickets or 4 weeks, the weekly job creates a reminder to pick a winner. The losing arm is then deleted.

### Scope (my call)

- **Everywhere the skills are installed**, the work laptop included: it's a general improvement, not a risky experiment like auto-merge.
- **In `wearebeam/magicnotes`, Joel's skills run as they do everywhere else.** `writing-good-tests` drops its magicnotes exclusion and gains one rule: when a repository's CI checks tests against its own rules, those rules win over the repository's docs. Magicnotes' CI `review-pr` checks Beam's 11 test rules, which match rules 1 to 11.
- **One-off check on the work laptop:** compare magicnotes' `docs/testing-ruby.md` and `docs/testing-frontend.md` with the end-to-end rules E1 to E9, and record any conflict.
- **Both laptops are measured**, each compared within its own Honeycomb environment (`joel-personal`, `beam-work`), because Honeycomb can't query across environments.
- **Human review comments are classified on personal and work repositories.** Work-side collection runs from the work laptop with work credentials, not from the personal cloud account, since the `wearebeam` organisation requires single sign-on.

### 3. Portable trigger

- **One pointer line, one source in dotfiles:** "For any change to code, config or docs that isn't pure research, use the `making-changes` skill." `workflow-sync` writes it into each harness's global instructions: Claude, Codex, Cursor and OpenCode.
- **Target:** at least 90% of sessions that edit files invoke `making-changes`.
- **Measured in Claude for v1.** Its hook already logs skill use and its telemetry logs file edits.
- **Follow-ups for other harnesses:**
  - **OpenCode:** a plugin like `opencode/plugins/notifications.js` that logs skill use and file edits.
  - **Codex:** `making-changes` reports its own start, and Codex's logged tool calls identify the sessions that edited files. Check first that Codex logs tool names.
  - **Cursor:** out of scope; its adapters may be removed in a separate cleanup.

### 4. Measurement

- **Findings ledger (ships first).** A `finding-log` command in dotfiles, linked into `~/.local/bin` like `gh-agent`. It takes `--stage` (write, risk-review, e2e-review, ci, bot, human-review, production), `--principle` (1 to 13, tests or other) and `--severity` (P1 to P3), and posts to the Honeycomb `workflow-ledger` dataset with host, harness and repo.
  - **Emitted by:** `making-changes` (self-check and risk review), e2e Stage 6 dispositions, and ship (CI rounds, bot feedback, the production verdict).
  - **Every `making-changes` run also logs a `rules_loaded` event:** the commit, branch, `good-code` version, each principle loaded and the trigger that loaded it.
  - **Miss tracking:** the weekly job joins later findings to the change's `rules_loaded` event by commit. A late finding citing a principle that **wasn't loaded is a trigger miss** (fix the trigger). One citing a principle that **was loaded is a rule miss** (fix the rule's wording).
  - **Callers log, reviewers don't (my call).** `good-code-review` stays read-only, as its own rules require, and whoever invoked it logs its findings. That avoids double counting. Standalone `/good-code-review` runs aren't counted.
  - **Human review comments:** the weekly job classifies them on merged PRs.
- **Baseline:** about two weeks of ledger data from today's flow before `making-changes` ships.
- **Benchmark:** 5 new eval cases in the skills repo's `evals/`, of a new `build` kind. Each is a small fixture app and task with hidden acceptance tests, plus planted traps checked by script, at least one per principle across the set: a tempting swallowed error, a query in a loop, a double submit, a missing permission check and a magic threshold. Each run also records complexity (crapper), test-rule checks, tokens and minutes. Before vs after plugin versions, 5 runs each, in the style of `compare.py`. Anything judged qualitatively uses a different model from the implementer.
- **Weekly numbers (automated):**
  - **Adoption:** the share of editing sessions that invoked the skill.
  - **Findings by stage:** the share caught before the PR opens versus after.
  - **Rework:** CI rounds, fix-up commits after a PR opens, and follow-up bug tickets.
  - **Cost:** minutes and tokens per change.
  - **e2e A/B:** findings by stage, minutes and tokens, compared between arms.
  - **Per principle:** how often it loads and why, where its findings get caught, and its trigger misses and rule misses, split by `good-code` version so an edit to a principle can be judged before vs after.
  - **Rare principles** (such as #9 safe to run twice) may barely appear in real work. The benchmark's planted traps give each principle a catch rate regardless.
  - These feed project B's visual; until it exists, a short weekly report.
- **Reminders:** the weekly job runs without the laptop awake. It creates a Todoist task, "Rate 2 changes", linking two random PRs merged that week and asking "would I merge this as-is?" (1 to 5). It also reminds when the baseline window ends and the benchmark is due.

### Build order

0. `finding-log`, emitters in e2e and ship, the weekly job and the reminder.
1. Benchmark cases, plus a baseline run on the current plugin version.
2. The `good-code` skill (migrated checklist), with `good-code-review` reading it.
3. The `making-changes` skill, the pointer sync, the e2e Stage 3/4 swap and the A/B switch, each with before-and-after agent checks. `writing-good-tests` drops its magicnotes exclusion and gains the CI-rules-win line.
4. After the baseline window: compare benchmark and ledger, and decide on the Stop hook.

## Constraints

- **The skills repo is public:** no Beam or Interpret specifics.
- **Skills reach all four harnesses** through `workflow-sync`. Only the pointer differs per harness, and it's generated.
- **Ship's limit is 500 changed lines per PR**, so this lands as several PRs in the build order.
- **Every skill change gets before-and-after agent checks**, and covered skills need the eval stamp.
- **No code comments** in scripts.
- **At work, the repository's guide wins**, except that a CI test review's own rules win over the repository's docs.

## Left to the builder

- **How reference files split or group**, and the exact rule wording, settled by agent checks.
- **Risk-trigger thresholds:** start at ~150 lines and tune from ledger data.
- **Honeycomb field names**, and the classifier prompt for human review comments.
- **Benchmark fixtures:** stack and size, kept small enough that 5 runs of each arm are affordable.
