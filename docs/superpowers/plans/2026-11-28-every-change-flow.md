# Every-change flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **TL;DR** 14 tasks in 5 parts, shipped as about 8 PRs. Part 1 logs findings from day one. Part 2 builds a benchmark and records today's numbers. Part 3 moves the checklist into a `good-code` skill. Part 4 adds `making-changes` and wires it into every harness and into e2e with an A/B test. Part 5 automates the weekly report and reminders.

**Goal:** Every non-research change runs one loop (`making-changes`) that applies the `good-code` principles while writing, and logs findings so we can see where problems get caught.

**Architecture:** Skills live in the public `jjholmes927-claude-skills` repo: new `good-code` and `making-changes`, edits to `e2e`, `ship`, `good-code-review`, `writing-good-tests` and `evals`, plus a shared `scripts/ledger-log.sh` built on the existing `skills/e2e/scripts/ledger.sh`. Dotfiles gets the pointer line, its drift test and the weekly-review prompt. A claude.ai scheduled routine runs the weekly report and the Todoist reminders.

**Tech Stack:** Markdown skills; Bash and Python 3 standard library; `unittest`; the Honeycomb events API through the existing ledger; Codex CLI through the existing `evals/run.py`; claude.ai routines with the Honeycomb and Todoist connectors.

**Spec:** `docs/superpowers/specs/2026-11-28-every-change-flow-design.md` (this branch).

**Deviations from the spec (builder calls):**
- **Findings logging reuses `skills/e2e/scripts/ledger.sh`**, which already posts to `workflow-ledger` and writes a local TSV. A new `scripts/ledger-log.sh` replaces the spec's dotfiles `finding-log` command, because the spec's own principle #3 says reuse first.
- **The pointer line is a copy, guarded by a test.** It lives in `claude/CLAUDE.md` (OpenCode loads this too) and `codex/AGENTS.md`, checked against one source file, instead of `workflow-sync` writing it.
- **No 2-week ledger baseline:** everything ships before the take-home. The before-vs-after evidence comes from the benchmark, which reruns the old plugin version. The ledger starts the day Part 1 merges.
- **Benchmark fixtures are small Python standard-library apps**, so 5 runs per arm stay cheap.

## Global Constraints

- The skills repo is public: no Beam, Interpret or magicnotes internals in content or examples.
- No code comments in any script, test or fixture.
- Each PR has at most 500 changed lines (ship's gate). Every skills-repo PR bumps `plugin.json` and both versions in `.claude-plugin/marketplace.json` together.
- Every skill change gets a before-and-after agent check. Skills covered by eval cases need the eval stamp in the PR body.
- A ledger call never fails or blocks the workflow that calls it.
- Branches start `jjholmes927-`. Commits are imperative, with no AI attribution.
- At work the repository's guide wins, except that a CI test review's own rules win over the repository's docs.

## Review Focus

1. **No Honeycomb key, offline, or `E2E_LEDGER=off`:** `ledger-log.sh` exits 0 and still writes the local TSV. Pinned in Task 1.
2. **Not a git repository, or a detached HEAD:** ledger fields fall back to `branch=none`, and `making-changes` skips quality signals but still verifies. Pinned in Tasks 1 and 8.
3. **Uncommitted edits and brand-new untracked files:** `quality-signals.sh --worktree` sees both. Pinned in Task 7.
4. **The base plugin version lacks the new skill files:** the benchmark's before arm runs with no workflow documents instead of crashing, and a CLI error counts as an error, not a failure. Pinned in Tasks 3 and 5.
5. **A docs-only or config-only change:** sized as docs or config, so verify and report only, with no signals and no review. Pinned in Task 8 by the `docs-only` benchmark case.

## File map

| Repo | Files |
|---|---|
| Skills | `scripts/ledger-log.sh`, `scripts/test_ledger_log.py` (new) |
| Skills | `skills/e2e/SKILL.md`, `skills/e2e/scripts/quality-signals.sh`, `skills/e2e/scripts/test-quality-signals.sh` |
| Skills | `skills/ship/SKILL.md` |
| Skills | `evals/run.py`, `evals/test_run.py`, `evals/bench.py`, `evals/test_bench.py` (new), `evals/cases.json`, `evals/fixtures/build/*` (new) |
| Skills | `skills/good-code/SKILL.md`, `skills/good-code/references/*.md` (new) |
| Skills | `skills/good-code-review/SKILL.md` |
| Skills | `skills/making-changes/SKILL.md`, `skills/making-changes/README.md` (new) |
| Skills | `skills/writing-good-tests/SKILL.md`, `skills/writing-good-tests/README.md` |
| Skills | `README.md`, `plugin.json`, `.claude-plugin/marketplace.json`, `benchmarks/*.md` |
| Dotfiles | `workflow/always-on.md`, `workflow/weekly-review.md` (new), `claude/CLAUDE.md`, `codex/AGENTS.md`, `tests/always_on_test.py` (new), `.github/workflows/tests.yml`, `docs/agent-setup.md` |
| Life-vault | `06-principles/good-code.md` |

---

## Part 1: Findings ledger (skills PR 1, version 2.36.0)

### Task 1: `ledger-log.sh` [low]

**Files:**
- Create: `scripts/ledger-log.sh`
- Test: `scripts/test_ledger_log.py`

**Interfaces:**
- Consumes: `emit <event> key=value…` from `skills/e2e/scripts/ledger.sh`. It adds `event`, `repo`, `head` and `host.name`, appends to `${XDG_STATE_HOME:-~/.local/state}/e2e/ledger.tsv`, and posts unless `E2E_LEDGER=off`.
- Produces:
  - `ledger-log.sh finding --stage <write|risk-review|e2e-review|ci|bot|human-review|production> --principle <1-13|tests|other> --severity <P1|P2|P3> [--pr <n>] [--arm <A|B>] [--by <skill>]` emits event `finding`.
  - `ledger-log.sh rules --principles <csv> --triggers <csv> --size <docs|config|code> --review <ran|skipped|unavailable> [--arm <A|B>]` emits event `rules_loaded`, adding `good_code_version` from the `plugin.json` two levels above the script.
  - `ledger-log.sh e2e-run --arm <A|B> --ticket <id|none>` emits event `e2e_run`.
  - Every event adds `branch` (`git branch --show-current`, or `none`) and `harness` (`$E2E_HARNESS`, or `unknown`).
  - Bad arguments: usage on stderr, exit 2, nothing written. Any posting failure: exit 0.

- [ ] **Step 1: Write the failing tests** (each runs the script with `XDG_STATE_HOME` set to a temp dir and `E2E_LEDGER=off`, inside a temp git repo on branch `jjholmes927-t`, unless noted)
  - `test_finding_writes_event`: the last TSV line's JSON has `event == "finding"`, `stage == "ci"`, `principle == "10"`, `severity == "P2"`, `branch == "jjholmes927-t"`.
  - `test_rules_loaded_records_version`: `good_code_version` equals `json.load(plugin.json)["version"]`, and `triggers == "core,touches:migration"`.
  - `test_rejects_unknown_stage`: `--stage lunch` exits 2 and no TSV line appears.
  - `test_outside_git_repo`: run in a non-git temp dir; exits 0 with `branch == "none"`.
  - `test_no_honeycomb_key`: `E2E_LEDGER` unset, with `PATH` stubs for `security` (exit 44) and `curl` (logs its call); exits 0, the TSV line is written, and curl is never called.
- [ ] **Step 2:** Run `python -B -m unittest discover -s scripts -p 'test_ledger_log.py' -v`. Expected: FAIL, the script is missing.
- [ ] **Step 3:** Implement `scripts/ledger-log.sh` in Bash. It sources `../skills/e2e/scripts/ledger.sh` and validates with `case` patterns.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `Add ledger-log for findings and rules events`.

### Task 2: Log findings from e2e and ship [low]

**Files:**
- Modify: `skills/e2e/SKILL.md` (Stage 6 merge paragraph), `skills/ship/SKILL.md` (Steps 7, 8 and 10), `plugin.json`, `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the Task 1 CLI, invoked as `bash "${CLAUDE_PLUGIN_ROOT}/scripts/ledger-log.sh" …` (one shell line, the same pattern as Stage 6's `advisory_review.py` call).

- [ ] **Step 1: Stage 6:** after the merged list is final, run one `finding --stage e2e-review --by e2e` per accepted finding, with its principle and severity.
- [ ] **Step 2: Ship Step 7:** each failed CI round logs one `finding --stage ci --severity P2 --by ship`, with the closest principle or `other`.
- [ ] **Step 3: Ship Step 8:** each comment judged valid logs one finding, with `--stage bot` for bot authors and `--stage human-review` for people.
- [ ] **Step 4: Ship Step 10:** a 🔴 verdict logs `--stage production --severity P1`; a 🟡 verdict logs `--severity P2`.
- [ ] **Step 5: Agent check:** one subagent gets ship Step 8 plus a fixture list of 2 bot comments and 1 human comment, all valid. It must emit exactly 3 `ledger-log.sh finding` lines with the right stages. Run it before the edit (expect 0 lines) and after (expect 3).
- [ ] **Step 6:** Bump to 2.36.0, commit `Log findings from e2e and ship`, and open PR 1 with `/ship`.

## Part 2: Benchmark (skills PRs 2a and 2b, versions 2.37.0 and 2.37.1)

### Task 3: A `build` kind in `run.py` [medium]

**Files:**
- Modify: `evals/run.py`
- Test: `evals/test_run.py`

**Interfaces:**
- Produces:
  - **Case shape:** `{"id": "build-<name>", "kind": "build", "fixture": "<dir under evals/fixtures/build>", "sources": [<skill files>], "task": "<text>"}`.
  - **Response schema:** `{"action": "implemented", "report_line": string, "summary": string}`.
  - **`prepare()` for build cases:**
    - Copy `<fixture>/app/` into the workspace.
    - Copy only the `sources` that exist under `--source-root`, and record the rest as `missing_sources` in `state.json`.
    - Prompt with "Follow the workflow documents as your working method", replacing the "material under evaluation" sentence.
    - Run in the `workspace-write` sandbox.
  - **`grade()` for build cases:**
    - `hidden_tests`: `python3 -I -B -m unittest discover -s <fixture>/hidden -t <workspace>` exits 0.
    - One `trap_<name>` check per `<fixture>/traps/<name>.py <workspace>`; exit 0 means the trap was avoided.
    - `scope_preserved`: changes stay inside the workspace's app files.
    - The `seconds` value is kept.
    - Each fixture may add a `report_checks.json` of `{check: substring}` pairs that must appear in `report_line`.

- [ ] **Step 1: Write the failing tests**, using a stub fixture under a temp `FIXTURES`:
  - `test_build_prepare_skips_missing_sources`: `missing_sources` lists the absent file, and the prompt omits it.
  - `test_build_grade_runs_hidden_tests`: a passing hidden test gives `hidden_tests: True`; a failing one gives `False`.
  - `test_build_trap_failure_fails_case`: a trap script exiting 1 makes `status == "fail"`.
  - `test_build_report_checks`: `report_checks {"size_docs": "size docs"}` passes only when `report_line` contains "size docs".
- [ ] **Step 2:** Run `python -B -m unittest discover -s evals -p 'test_run.py' -v`. Expected: the 4 new tests FAIL.
- [ ] **Step 3:** Implement the build branches in `prepare()`, `schema_for()`, `grade()` and the `main()` sandbox choice.
- [ ] **Step 4:** Run the same command. Expected: PASS, with the existing tests still green.
- [ ] **Step 5:** Commit `Add a build kind to the eval runner`.

### Task 4: Six build fixtures [high]

**Files:**
- Create: `evals/fixtures/build/<name>/{app/, hidden/, traps/, report_checks.json?}` for each fixture below
- Modify: `evals/cases.json` (6 cases)

| Fixture | Task given to the agent | Traps (principle) |
|---|---|---|
| `delivery-fee` | Add free delivery from £50 | `magic_threshold` (#1), `missing_boundary_test` (tests, rule 12), `long_function` (#2) |
| `refund-webhook` | Mark refunds from the provider's webhook | `duplicate_delivery` (#9), `swallowed_error` (#10), `unsigned_payload` (#8) |
| `notes-access` | Endpoint to read a note by id | `other_users_note` (#8), `unvalidated_id` (#7), `bypasses_authorize_helper` (#13) |
| `report-export` | Export open orders to CSV | `query_in_loop` (performance), `ignores_csv_helper` (#3), `second_retry_loop` (#12) |
| `saved-settings` | Add a field to saved settings | `fails_on_old_record` (#6), `edits_unrelated_module` (#4), `half_built_settings` (#7) |
| `docs-only` | Fix a typo in `README.md` | `report_checks.json`: `{"size_docs": "size docs", "no_review": "review skipped"}` |

- **Every case's `sources`:** `skills/making-changes/SKILL.md`, `skills/good-code/SKILL.md`, every `skills/good-code/references/*.md` listed by name, `skills/writing-good-tests/SKILL.md` and `skills/writing-good-tests/references/rules.md`.
- **Traps are behavioural probes** wherever possible (call the webhook twice, read another user's note, count fake-database queries, load an old record). Static checks (AST or grep) are allowed only for #1, #2, #3 and #12.

- [ ] **Step 1:** For each fixture, write `app/` (one small module, its existing tests, and an existing helper where the trap needs one to reuse), then `hidden/` and `traps/`.
- [ ] **Step 2:** For each fixture, apply a hand-written correct solution in a temp copy. Expected: hidden tests PASS and every trap exits 0.
- [ ] **Step 3:** For each fixture, apply a trap-hitting solution in a temp copy. Expected: each targeted trap exits non-zero.
- [ ] **Step 4:** Commit `Add build benchmark fixtures`. Split 3 and 3 across two commits if the PR would pass 500 lines.

### Task 5: `bench.py` and the baseline [medium]

**Files:**
- Create: `evals/bench.py`, `evals/test_bench.py`, `benchmarks/2026-11-28-every-change-baseline.md`

**Interfaces:**
- Consumes: Task 3's `run.py run --case <id> --source-root <dir> --output <dir> --model <id>`.
- Produces: `python3 -B evals/bench.py --base <ref> --head <ref> --runs 5 --model <id> [--arm base|head|both] [--case <id or prefix*>…]`.
  - It makes a temp `git worktree` for each ref and passes it as `--source-root`. `run.py`, `cases.json` and the fixtures always come from the current checkout, so only the skill sources differ between arms.
  - A trailing `*` in `--case` matches by prefix, so `build-*` means every build case.
  - It runs every case `--runs` times per arm and prints a markdown table: case · check · base passes/runs · head passes/runs · mean seconds per arm.
  - Error runs are counted separately and excluded from pass rates.

- [ ] **Step 1: Write the failing tests** on synthetic `results.json` files:
  - `test_aggregates_checks_across_runs`: 3 runs with `trap_x` True, False, True give `2/3`.
  - `test_table_counts_errors_separately`: an `error` run is excluded from the denominator and shown in an `errors` column.
- [ ] **Step 2:** Run `python -B -m unittest discover -s evals -p 'test_bench.py' -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `bench.py`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Bump the version, commit `Add the before-and-after benchmark runner`, and open PR 2a with `/ship`.
- [ ] **Step 6: Baseline, once Task 4's fixtures exist (PR 2b):** run `python3 -B evals/bench.py --base 17fc2ea --arm base --runs 5 --model <the model in ~/.codex/config.toml> --case 'build-*'` and save the table, the model and the date to `benchmarks/2026-11-28-every-change-baseline.md`. Commit it in PR 2b.

## Part 3: `good-code` skill (skills PRs 3a and 3b, versions 2.38.0 and 2.38.1)

### Task 6: The `good-code` skill [high]

**Files:**
- Create: `skills/good-code/SKILL.md`; `skills/good-code/references/01-write-for-the-reader.md` through `13-follow-the-good-patterns.md`; `references/performance.md`, `references/every-pr.md`, `references/reviewing.md`, `references/symptoms.md`
- Modify: `README.md` (row), `plugin.json` (description)

**Content contract:**
- **`SKILL.md`, at most 80 lines:**
  - A TL;DR, then the 13 ranked one-liners.
  - "Higher wins; correctness, security and required behaviour are never traded; the repository's guide wins, and a CI test review's rules win over the repository's docs."
  - The spec's three-dials table and trigger table, verbatim.
  - "Always read for any code change: 01, 02, 03, 07, 10, 13."
  - The manual override line.
- **Each principle file:** `## While writing` (at least 2 Flag / Write instead rules with generic examples, in the `writing-good-tests` format), then `## When reviewing` (the checklist's review questions for that principle, from life-vault `good-code.md`).
- **`13-follow-the-good-patterns.md`** carries the spec's #13 rule verbatim.

- [ ] **Step 1:** Write `SKILL.md` and the core references (01, 02, 03, 07, 10, 13). This is PR 3a.
- [ ] **Step 2:** Write the triggered references (04, 06, 08, 09, 12), the remaining ones (05, 11) and the 4 supporting files. This is PR 3b.
- [ ] **Step 3:** Run `grep -riE 'beam|interpret|magicnotes|talk squad' skills/good-code`. Expected: no output.
- [ ] **Step 4: Agent check:** run `bench.py --arm head --runs 3 --case build-refund-webhook --case build-notes-access` from a branch where `making-changes` doesn't exist yet. Only the `good-code` and `writing-good-tests` sources load. Expected: trap avoidance at or above the baseline on every trap, recorded in the PR body.
- [ ] **Step 5:** Commit `Add the good-code principles skill` (3a) and `Add good-code's triggered references` (3b).

### Task 7: `good-code-review` reads the skill; `quality-signals --worktree` [medium]

**Files:**
- Modify: `skills/good-code-review/SKILL.md` (description, Step 1), `skills/e2e/scripts/quality-signals.sh`
- Test: `skills/e2e/scripts/test-quality-signals.sh`
- Modify (life-vault repo): `06-principles/good-code.md`

**Interfaces:**
- Produces:
  - **`good-code-review` Step 1:** read `$GOOD_CODE_CHECKLIST` if it's set. Otherwise read `${CLAUDE_PLUGIN_ROOT}/skills/good-code/SKILL.md` plus every reference its triggers select; the `## When reviewing` sections are the questions. The "checklist unavailable" stop line is unchanged.
  - **`quality-signals.sh --worktree`:** changed files are `git diff --name-only --diff-filter=AM HEAD` plus `git ls-files --others --exclude-standard`. Line ranges come from `git diff -U0 HEAD`, and untracked files count whole. Output paths are unchanged (`.e2e/quality-signals.md`).

- [ ] **Step 1: Write the failing tests** in `test-quality-signals.sh`:
  - `worktree mode scores an uncommitted edit`
  - `worktree mode scores an untracked file`
  - `base mode ignores uncommitted edits` (pins today's behaviour)
- [ ] **Step 2:** Run `bash skills/e2e/scripts/test-quality-signals.sh`. Expected: the 2 worktree tests FAIL.
- [ ] **Step 3:** Implement `--worktree` in `quality-signals.sh`.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Edit `good-code-review` Step 1 and its description, and run its existing eval cases with `evals/compare.py`. Expected: no drops. Paste the eval stamp.
- [ ] **Step 6:** In life-vault, replace `good-code.md`'s body with a pointer to the public skill, keeping the private "Where it's come from" history. Commit there separately.
- [ ] **Step 7:** Commit `Read good-code from its skill and score uncommitted changes`, and open the PR with `/ship`.

## Part 4: `making-changes` (skills PRs 4 and 5, versions 2.39.0 and 2.40.0; dotfiles PR)

### Task 8: The `making-changes` skill [high]

**Files:**
- Create: `skills/making-changes/SKILL.md`, `skills/making-changes/README.md`
- Modify: `README.md` (row), `plugin.json` (description)

**Content contract:**
- **Description:** "Use when implementing, fixing, refactoring or changing any code, config or docs, in any repository: every change that isn't pure research or answering a question. Also used by e2e for each task."
- **Step 1, size:** docs means only `*.md`, `*.txt` or files under `docs/`. Config means only `*.json`, `*.yml`, `*.yaml` or `*.toml`. Anything else is code.
- **Step 6, self-check:**
  - Run `bash "${CLAUDE_PLUGIN_ROOT}/skills/e2e/scripts/quality-signals.sh" --worktree`. If it's not a git repository, skip this and say so.
  - Map signals to references: CRAP ≥ 30 on a changed function → 02; a duplicate touching a changed file → 03 and 12; a file over 300 lines that grew → 02 and 04; a new dependency in a manifest → 03; a second way of doing something → 13.
  - CRAP ≥ 30 or a duplicate also triggers step 7.
- **Step 7, risk review:**
  - Triggered by trigger-table rows #6, #8 or #9; more than 150 changed lines (tracked plus untracked); or a strong signal.
  - Runs `good-code-review` in a fresh read-only context: a native subagent when one is available, otherwise `e2e-codex.sh audit`. If neither is available, the report says `review unavailable`.
  - Inside e2e, arm A skips step 7 and arm B runs it (Task 10).
- **Step 8, report line, exact format:** `Change: size <docs|config|code> · rules <csv> · tests <K> of <T> seen failing · verify <verdict> · review <skipped|ran: N findings|unavailable>`. Commit only when the user or the calling workflow authorised it.
- **Step 9, logging:** one `ledger-log.sh finding --stage write|risk-review --by making-changes` per fixed finding, and one `ledger-log.sh rules …` per run.

- [ ] **Step 1:** Write the skill and its README.
- [ ] **Step 2: Agent check:** run `bench.py --base 17fc2ea --head HEAD --runs 5 --model <same model> --case 'build-*'`. Expected:
  - Hidden-test pass rate at least the baseline.
  - Trap avoidance up on at least 4 of the 5 code fixtures.
  - `docs-only` passes `size_docs` and `no_review` in at least 4 of 5 runs.
  - Mean seconds per code case at most 2× the baseline.
- [ ] **Step 3:** Save the table to `benchmarks/2026-11-28-every-change-after.md`, commit `Add the making-changes loop`, and open PR 4 with `/ship`.

### Task 9: The always-on pointer (dotfiles) [low]

**Files:**
- Create: `workflow/always-on.md`, `tests/always_on_test.py`
- Modify: `claude/CLAUDE.md` (under "Commands and Skills"), `codex/AGENTS.md`, `.github/workflows/tests.yml` (matrix row `{ dir: tests, module: always_on_test }`), `docs/agent-setup.md` (inventory rows for `writing-good-tests`, `good-code`, `making-changes`)

**Pointer text, verbatim:** "For any change to code, config or docs that isn't pure research, use the `making-changes` skill."

- [ ] **Step 1: Write the failing tests:** `test_claude_md_contains_pointer` and `test_codex_agents_contains_pointer` each assert the exact stripped text of `workflow/always-on.md` appears in the file.
- [ ] **Step 2:** Run `cd tests && python -m unittest -v always_on_test`. Expected: FAIL.
- [ ] **Step 3:** Add the line to both files and the CI matrix row.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `Point every harness at making-changes`. It ships together with Task 12's prompt file and this plan and spec.

### Task 10: e2e uses `making-changes`, with the A/B test [medium]

**Files:**
- Modify: `skills/e2e/SKILL.md`, `evals/cases.json` (2 decision cases)

**Interfaces:**
- Consumes: Task 1's `e2e-run` event and Task 8's step numbers.
- Produces:
  - **Arm rule at Stage 2:**
    - A `--arm A|B` argument wins.
    - Otherwise use the ticket's number: even means A, odd means B.
    - Otherwise use the first character of `printf %s "$branch" | shasum`: `0` to `7` means A, `8` to `f` means B.
    - Record the arm in `.e2e/handoff.md` and log `ledger-log.sh e2e-run --arm <X> --ticket <id|none>`.

- [ ] **Step 1: Stage 3:** the implementer runs `making-changes` for the task, given by installed path on delegated routes. The route, retry and checkpoint lines stay; the duplicated TDD, ponytail and no-comments brief moves out, because `making-changes` carries it.
- [ ] **Step 2: Stage 4:** remove it. The self-check is now `making-changes` step 6.
- [ ] **Step 3: Stage 5:** arm A keeps today's text. In arm B, step 7 runs per risky task; on the Codex route the coordinator runs `good-code-review` on the task's commit; at most one fix round per task.
- [ ] **Step 4: Stage 6 and ship's CI repairs:** repairs run `making-changes` steps 1 to 6.
- [ ] **Step 5: Add 2 decision cases:**
  - `e2e-arm-a-risky-task`: arm A, task commit touches a migration, next action → `continue`.
  - `e2e-arm-b-risky-task`: arm B, same task → `reviewed`.
- [ ] **Step 6:** Run `python3 -B evals/compare.py origin/master --model claude-opus-5-5`. Expected: no drops on existing e2e cases, and both new cases pass. Paste the stamp.
- [ ] **Step 7:** Commit `Run making-changes per e2e task and A/B the review timing`, and open PR 5 with `/ship`.

### Task 11: `writing-good-tests` update [low]

**Files:**
- Modify: `skills/writing-good-tests/SKILL.md`, `skills/writing-good-tests/README.md`

- [ ] **Step 1:** Remove the magicnotes exclusion from the description, the Scope section and the README's Key Patterns row.
- [ ] **Step 2:** Under "Which rules win", add verbatim: "When a repository's CI checks tests against its own rules, those rules win over the repository's docs."
- [ ] **Step 3: Agent check:** rerun the 28 Nov unit-test fixture with the edited skill. Expected: rules 4, 5, 6 and 7 still followed, and the report line present.
- [ ] **Step 4:** Commit `Apply writing-good-tests everywhere and let CI test rules win`. It ships in PR 4.

## Part 5: Weekly loop and reminders

### Task 12: Weekly review routine (personal) [medium]

**Files:**
- Create (dotfiles): `workflow/weekly-review.md`, the routine's prompt, kept under version control

**Prompt contract:**
- **Query Honeycomb `workflow-ledger`** (`joel-personal`) for the last 7 days:
  - `rules_loaded` by principle and trigger
  - `finding` by stage and principle
  - `e2e_run` by arm
- **Adoption:** Claude sessions with file-edit tool events vs sessions with `skill_invoked` = `making-changes`.
- **Miss tracking:** join findings to `rules_loaded` by repo and branch (by `head` when the branch is the default). A principle that wasn't loaded is a trigger miss; one that was loaded is a rule miss.
- **From GitHub (personal repositories):** CI failure rounds, commits after a PR opened, bug issues that reference merged PRs, and human review comments classified by principle.
- **Output to Todoist:**
  - A task "Weekly flow report <date>" of at most 15 lines.
  - A task "Rate 2 changes" linking two random PRs merged that week, asking "Would I merge this as-is? 1–5".
  - A task "Decide the e2e A/B winner" once each arm has 5 `e2e_run` events, or 4 weeks after 2026-11-28.
  - A task "Run the after benchmark" 2 weeks after PR 5 merges.

- [ ] **Step 1:** Write `workflow/weekly-review.md`.
- [ ] **Step 2:** Authenticate the claude.ai Honeycomb connector. It isn't authenticated today.
- [ ] **Step 3:** Create the routine with the `schedule` skill: Mondays at 09:00 Europe/London, with the Honeycomb and Todoist connectors and the personal repositories.
- [ ] **Step 4:** Trigger one run by hand. Expected: the report task and the "Rate 2 changes" task appear in Todoist.

### Task 13: Work laptop (run on the work laptop) [low]

- [ ] **Step 1:** Run `workflow-sync`, then `bash <plugin root>/scripts/ledger-log.sh finding --stage write --principle other --severity P3`. Expected: the event appears in the `beam-work` environment.
- [ ] **Step 2:** Set up the same weekly prompt with environment `beam-work` and the `wearebeam` repositories, as a Kandev watch or a local launchd job, run with work credentials. Classifying colleagues' review comments is included.
- [ ] **Step 3:** Compare magicnotes' `docs/testing-ruby.md` and `docs/testing-frontend.md` with E1 to E9. Record any conflict as a `writing-good-tests` follow-up.

### Task 14: After-ship comparison [low]

- [ ] **Step 1:** When the Task 12 reminder fires, run `bench.py --base 17fc2ea --head origin/master --runs 5 --model <same model>` and save the table to `benchmarks/<date>-every-change-after-2w.md`.
- [ ] **Step 2:** Read the ledger's findings by stage and the e2e A/B numbers. Decide the A/B winner and delete the losing arm's text. Decide whether the Stop hook is needed.

---

## PR order

| PR | Repo | Tasks | Version |
|---|---|---|---|
| 1 | Skills | 1, 2 | 2.36.0 |
| 2a | Skills | 3, 5 (runner) | 2.37.0 |
| 2b | Skills | 4 (fixtures, one PR or two), 5 Step 6 (baseline) | 2.37.1 |
| 3a | Skills | 6 (skill and core references) | 2.38.0 |
| 3b | Skills | 6 (triggered references), 7 | 2.38.1 |
| 4 | Skills | 8, 11 | 2.39.0 |
| 5 | Skills | 10 | 2.40.0 |
| D | Dotfiles | 9, 12 prompt, spec and plan | n/a |

The baseline run (Task 5, Step 5) must happen before PR 3a merges, so the "before" arm has no `good-code` files.
