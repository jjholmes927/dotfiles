# Agent control-plane audit

**TL;DR.** Adopt Kandev as the task/agent control plane, keep the lanes and `/e2e`+`/ship`+`/verify` underneath it, borrow HAR's tree-hash evidence rule without HAR, retire Fleet's plumbing. Conditional on Experiment 1 (§23): `/e2e --dry-run` must run inside a Kandev task with its skills, plan gate and resumption intact; if not, fix the four cheap defects (§5) and keep today's system. Sol reached the same verdict blind (§26). Sections: 1 conclusion · 5 friction · 9 capability matrix · 13 READY contract · 16 attention policy · 17 completion contract · 22 keep/replace/delete · 23 experiments · 24 migration.

Audit of the Operator/Fleet workflow against the north star of an agent-agnostic, autonomous engineering execution system, and against Kandev and HAR as candidate infrastructure. Written 2026-09-04 from the live scripts, sidecars, job state, worktrees and shell history on this machine, plus the current `main` of both projects (Kandev `ddcc4fc6`, HAR `9a8cbcc` / v1.12.0). Nothing in the workflow was changed.

Cross-model check: Sol (codex, effort high) was consulted blind on the same evidence and independently recommended the same option; its findings, what was verified, and what was adopted are in §26.

---

## 1. Executive conclusion

**Recommended direction: Kandev as the task/agent control plane, lanes kept as the environment layer underneath it, HAR's evidence idea adopted without HAR itself, Fleet reduced to a thin attention client (or retired). Conditional on one experiment passing first.**

Why, in one paragraph. The current system's *product concepts* are sound and mostly absent from both candidates: attention-first inbox, warm lanes with physical singletons, explicit completion separate from "agent idle", one deliberate plan gate. But its *plumbing* is a Claude-CLI-shaped workaround: it polls `claude agents --json`, screen-scrapes tmux to answer a question that Claude already writes as structured JSON, keys completion off a sidecar file the /e2e skill never writes, and puts the scheduler inside an LLM session (`orchestrating-lanes`) with no persisted lease. Kandev already has the durable pieces the north star needs and the current system lacks: a persisted task/session model over 20+ agents via ACP, a Linear issue watch that is literally "READY filter → create task → auto-start, capped by max in-flight", workflow steps with per-step agent profile and `reset_agent_context` (fresh-context cross-model review as a first-class step), WIP limits and pull, structured clarification requests, `blocked_by` dependencies, a WebSocket event stream, and idempotent `external_id` task creation. HAR solves a different problem well (bind "verified" to an exact tree hash) but its slots are ephemeral, know nothing about singletons, and would duplicate both `bin/create_worktree` and Kandev's worktrees.

The riskiest assumption is not Kandev's feature list; it is whether Claude Code plugin skills (`/e2e`, `/ship`, `/verify`) run under Kandev's ACP adapter rather than only in opaque passthrough mode. Experiment 1 (§23) tests exactly that, on one lane, in an afternoon, reversibly. If it fails, the fallback is Option E: fix the four cheap defects in the current system (§5) and keep it.

**Relation to the 2026-08-18 verdict.** "The Missing Control Plane" concluded native-first: `claude agents` as the control plane, no tmux orchestrator, no Craft/xirp/Conductor. Two weeks of use since then produced exactly the workarounds catalogued in §3.2 and §5, and the requirement set has changed: agent-agnosticism, autonomous pickup and cross-model collaboration are now first-class. Kandev was not in the August comparison set. The August "don't build an orchestrator" verdict stands; this audit's difference is "adopt one" rather than "build one", and only if Experiment 1 passes.

**Keep:** the attention-first inbox contract, warm lanes + `bin/create_worktree`, `/e2e` + `/ship` + `/verify` as the engineering policy layer.
**Stop maintaining:** `fleet`'s data plane (session polling, sidecars, tmux gate-answering), `orchestrating-lanes` as the scheduler, hand-rolled worktree lifecycle around `claude rm`.
**Kandev owns:** task identity, ready-queue intake from Linear, scheduling/WIP, agent runtimes, sessions, clarification/blocked state, workflow steps, events.
**HAR owns:** nothing as runtime; its tree-hash validation + commit-gate idea moves into `/verify` and `/ship`.
**Fleet becomes:** a read-only attention view over Kandev events, kept only if Kandev's own Threads/Inbox surface proves too process-shaped.
**First experiment:** run one `/e2e` ticket through a Kandev Worktree task on the mn3 lane with a Claude ACP profile.

---

## 2. North star (restated as testable properties)

| # | Property | How it would be observed |
|---|----------|--------------------------|
| N1 | Work is picked up without a manual dispatch | A ticket meeting READY starts a stream within one poll interval, nobody ran `new-agent` |
| N2 | Standards enforced regardless of runtime | Same `/e2e` gates and same PR shape whether Claude or Codex implemented |
| N3 | Cross-model collaboration where it improves quality | Reviewer has a fresh context and a different model from the implementer; disagreements surface, not average |
| N4 | Evidence-based completion | "Done" requires artefacts (tests, verify verdict, tree hash, PR, ticket state), never an agent's sentence |
| N5 | Human interrupted only for judgement | Inbox items are typed (plan review, architecture decision, models disagree, product context) and rate is measured |
| N6 | Provenance | One id links ticket → task → sessions → decisions → commits → PR → telemetry |
| N7 | Reliability | Crash of any process loses no state; duplicate pickup impossible; reconciliation restores truth |

Optimisation target: quality-weighted throughput per human-attention minute and per dollar. Autonomy is an input, not the objective.

---

## 3. Current architecture (as implemented, not as documented)

Sources: `dotfiles/bin/*`, `dotfiles/docs/operator-workflow.md`, `dotfiles/claude/settings.json`, `jjholmes927-claude-skills/skills/{e2e,orchestrating-lanes}/SKILL.md`, `joel-workflow/commands/{ship,verify,pick-up-linear-ticket}.md`, `mn1/bin/create_worktree`, `mn1/lib/{worktree_offset,dev_environment}.rb`.

```
Linear ticket ──(human types)──▶ new-agent <lane> "/e2e INT-X"
                                    │ fetch origin/main · branch · bin/create_worktree (DB/ports/env/memory)
                                    ▼
                              claude --bg --name --effort --model --permission-mode bypassPermissions
                                    │  ~/.claude/jobs/<id>/state.json  (Claude-owned lifecycle)
                                    ▼
      /e2e: pick-up-linear-ticket → brainstorm → plan → Sol audit (read-only codex) → HUMAN GATE (AskUserQuestion)
            → Sol implements per task (codex exec, workspace-write) → Sol self-review → Fable review + fix loop (≤3)
            → final branch review → /ship (format · commit · /verify · /simplify · push · PR · CI watch · bot-review consolidation)
                                    │
                                    ▼
                    agent runs `fleet-status complete|awaiting "<note>"`  → ~/.claude/fleet-status/<sessionId>
                                    │
        fleet TUI: claude agents --json --all (3s) + sidecars + transcript tail → BLOCKED/WORKING/COMPLETE/AWAITING/STOPPED
        orchestrating-lanes (LLM): queue → new-agent → SendMessage notify_when_idle → 15–20 min heartbeat → Linear Done + sidecar → refill
                                    │
                                    ▼
                    close: merge · claude rm · git worktree remove + branch -D (by hand) · memory line
```

### 3.1 Lifecycle transitions and their owners

| Transition | Owner | State lives in | Persisted? | Crash behaviour | Idempotent? | Duplicate possible? | Claude-specific? |
|---|---|---|---|---|---|---|---|
| ticket → readiness | human, in Linear; skill `pick-up-linear-ticket` warms context | Linear | yes | n/a | yes | no | no |
| readiness → lane selection | human (or orchestrating-lanes LLM: "free when no session working in it") | derived from `claude agents --json` cwd | derived | re-derived | yes | **yes** (two dispatches to one lane are allowed; lanes are hosts, so this is fine) | yes (`kind==interactive && cwd` probe) |
| lane → worktree | `new-agent` → `bin/create_worktree` (or `git worktree add` fallback) | git + `.env` + `.worktrees/<slug>` | yes | pre-created branch deleted on failure; partial worktree may remain | mostly (refuses existing path) | no | no |
| worktree → agent launch | `new-agent` → `claude --bg` | `~/.claude/jobs/<short>/state.json`, daemon | yes (Claude) | daemon adopts/respawns; state.json `respawnFlags` | no (re-running new-agent makes a second stream) | yes | **yes** |
| planning → human gate | `/e2e` Stage 1 `AskUserQuestion` | state.json `needs`, `block.questions[]`; also on screen | yes (Claude) | survives sleep; **retired after ~60 min idle** (daemon log: `retire 588ae134: idle-prompt, idle 63m`) | n/a | n/a | yes |
| gate → continuation | human via fleet peek (tmux attach + `send-keys 1 Enter`) or `claude attach` | none of ours | n/a | answering converts session to `blocked/idle` forever (doc §4) | no | possible (double answer) | yes, screen-scrape |
| implement / review / verify | `/e2e` stages, `e2e-codex.sh`, `.e2e/sessions.tsv` | worktree `.e2e/` | yes | resumable by thread id in TSV | partially (TSV is append-only ledger) | retries bounded by TSV | codex-specific wrapper, Claude-specific subagent review |
| completion | agent runs `fleet-status complete` | `~/.claude/fleet-status/<sessionId>` TSV | yes | fine | yes (last write wins) | n/a | key is Claude session id |
| PR / ticket state | `/ship` (gh), `pick-up-linear-ticket` (In Progress); **nothing moves Done** | GitHub, Linear | yes | fine | mostly | no | no |
| cleanup | human: `claude rm` + `git worktree remove` + `branch -D` | git | yes | n/a | yes | n/a | `claude rm` reaps only lazy worktrees |
| refill | orchestrating-lanes LLM heartbeat | LLM context + Linear + sidecar | **not persisted** | orchestrator session death = scheduler death | no | **yes** (nothing leases a ticket) | yes |

### 3.2 Claude-specific dependencies, classified

| Dependency | Where | Classification |
|---|---|---|
| `claude --bg --name --effort --model --permission-mode` | new-agent | adapter (launch) |
| `claude agents --json --all` polled every 3 s | fleet, pair, lane-sweep, clone-status, closure-sweep | **workaround** (no event API) |
| `claude attach` via tmux + `capture-pane` + `send-keys` to answer a gate | fleet `gate_answer` | **workaround** — and now obsolete: `state.json` carries `needs` and `block.questions[].options[]` |
| `~/.claude/projects/<slug>/<id>.jsonl` transcript tail for the context line | fleet | workaround / implementation detail |
| session id = stream identity; sidecar keyed by `CLAUDE_CODE_SESSION_ID` | fleet-status, fleet | **implementation detail leaking into identity** (§16) |
| `state == blocked && status != idle` heuristics; "answered gate = idle forever" | fleet `derive_bucket` | workaround for Claude state semantics |
| 60-minute idle retirement; Ctrl+T pin | daemon | Claude limitation the design routes around |
| `claude rm` leaving provisioned worktrees | close step | workaround (two-step close) |
| `SendMessage notify_when_idle` one-shot + notice loop | orchestrating-lanes | workaround → heartbeat sweep |
| `CLAUDE_CODE_SUBAGENT_MODEL=opus` hook, agent-teams OFF | settings.json | policy + workaround |
| `AskUserQuestion` as the plan gate | /e2e | **policy** (one gate) implemented through a Claude primitive |
| `Notification` hooks → tmux bell | settings.json | adapter (alerting) |
| PreToolUse OTel ledger hook | settings.json | adapter (telemetry) |
| Codex wrapper `e2e-codex.sh` (thread ids, `-o last-message.txt`, `--json`) | /e2e | adapter (Codex) |

Durable product requirements hidden in the above: "a stream has one owner and one completion record", "a human question is a typed, answerable object", "completion ≠ idle", "the inbox rings only on BLOCKED/COMPLETE transitions".

---

## 4. Observed real workflow

Evidence: `~/.bash_history` (717 lines), `~/.claude/history.jsonl` (3,468 rows, 494 in 21 days), `claude agents --json --all` (16 rows), `~/.claude/fleet-status/*` (11 sidecars), `~/.claude/jobs/*/timeline.jsonl`, `~/.claude/daemon.log`, `git worktree list` across mn1–mn5, `.e2e/sessions.tsv` in three worktrees.

**What the fleet is actually used for.** Of ~11 `new-agent` dispatches since 22 Aug, 3 were `/e2e <ticket>`. The other 8 were ad-hoc investigation, review, catch-up and "quiz me" prompts ("What do you think of this PR", "Check the alert here", "help me understand this PR", "socratic interview"). The system is as much a **parallel investigation bench** as a ticket pipeline. Any replacement must keep "type a prompt into a lane" cheap.

**Attention traffic today.** Three BLOCKED rows: one genuine plan gate (INT-773, `block.questions` with Approve/Revise), two "awaiting Joel's OK to move ticket to Done" (INT-831, INT-828). Two of three interruptions are ticket-state bookkeeping, not judgement. That is the strongest single argument for an evidence-based completion contract that moves Linear itself.

**Idle retirement bites awaiting work.** `daemon.log` shows 588ae134 retired at 63 min idle, re-claimed from fleet at 18:14, retired again at 86 min. Awaiting-human streams die on a timer and are resurrected by hand.

**Cleanup debt.** 25 worktrees across five lanes; 8 of them are from sessions already `done`/`stopped`. Two worktree containers (`.worktrees/` from `create_worktree`, `.claude/worktrees/` from Claude's lazy isolation). Worktree directory names are prompt slugs with timestamps (`jjholmes927-check-the-alert-here-https-wearebeam-sla-095221`) while the branch inside was renamed by the agent (`jjholmes927-scribe-rate-limit-alert-INT-755`), so path, branch and ticket disagree.

**Iteration is real and bounded.** INT-842: implement → self-review-fixed → fix-loop-1-fixed, then PR #9449 CI green, Bugbot clean. INT-508 (mn3): codex quota-blocked, fell back to an Opus subagent implementer (`opus-a4f4b822`), three tasks each with one fix loop, one branch-level fix loop. The loop caps in `/e2e` are being hit and are working; the TSV ledger is a good idea.

**Doc/implementation drift found.** `orchestrating-lanes` says default effort high; `new-agent` defaults to `low`. `operator-workflow.md` says `/e2e` calling `fleet-status` is pending — it still is; only the `new-agent` prompt footer asks for it. `orchestrating-lanes` says the lane sets the ticket Done "after its /e2e verification passed and the change is in production"; nothing in `/e2e`, `/ship` or `pick-up-linear-ticket` moves a ticket past In Progress. The refill trigger therefore depends on a human moving Linear.

**Telemetry.** The Claude/Codex OTel export and `workflow-ledger` hook are configured in `settings.json` and `~/.codex/config.toml`. The Honeycomb MCP available to this session is bound to the `beam` team, which has no `workflow-ledger` dataset, so the personal telemetry stream is **unverified** in this audit.

---

## 5. Current friction and failure modes

| # | Friction | Root cause | Cheap fix exists today? |
|---|---|---|---|
| F1 | Answering a plan gate requires tmux attach + screen scrape; headless paths dead-end | Fleet predates `state.json` `needs`/`block.questions` | Yes: read `~/.claude/jobs/<id>/state.json`; answering still needs attach |
| F2 | Awaiting-human streams retired after ~60 min | Claude daemon policy | Partial: pin (Ctrl+T) or make "awaiting" a state outside the session |
| F3 | "Blocked" conflates plan gate, clarifying question, and "OK to move ticket Done?" | No typed attention item | No: needs a completion contract that moves Linear (§17) |
| F4 | Completion detection = sidecar + Linear Done, but nothing writes Done | Policy gap in /e2e and /ship | Yes: /ship moves ticket to In Review; merge automation moves Done |
| F5 | Worktree/branch/ticket names diverge; two worktree containers; 25 orphans | new-agent slugs from prompt; Claude lazy worktrees; `claude rm` doesn't reap | Partial: name worktree after ticket; `bin/cleanup_worktrees`. The August landmine (`worktree_offset.rb` ignores `.claude/worktrees/` → DB offset 0) is still open: five such worktrees exist in mn1/mn4 today |
| F6 | Scheduler state lives in an LLM session | orchestrating-lanes design | No: needs a durable queue with leases |
| F7 | Duplicate pickup possible (no lease on a ticket) | same | No |
| F8 | Effort/model defaults drift between skill doc and script | two sources of truth | Yes |
| F9 | Cross-model review depends on Sol quota; INT-508 fell back to same-family Opus | single fallback path, no routing | Partial (Kandev has provider fallback routing) |
| F10 | Stream identity = Claude session uuid | sidecar keyed by session id | No: needs a vendor-neutral work id (§16) |
| F11 | Every helper re-implements `claude agents --json` parsing (5 scripts) | no shared runtime adapter | Yes, but see §21: better to delete than to refactor |

Accidental robustness worth keeping: the `.e2e/sessions.tsv` attempt ledger ("count from the file, never from memory"), the `fleet-status` single-writer sidecar contract, the "fetch fresh origin/main before every stream" rule, and `create_worktree`'s fail-closed provisioning.

---

## 6. Product concept vs implementation accident

| Element | Class | Note |
|---|---|---|
| Attention-first inbox (BLOCKED first, peek → answer → pair → resume) | **PRODUCT CONCEPT** | Kandev's Threads and Office Inbox partially cover it (§7.5) |
| Warm lane with fixed DB/ports/Redis and a physical singleton (Twilio tunnel on mn1) | **PRODUCT CONCEPT** | Neither Kandev nor HAR models singletons |
| Completion is explicit and separate from agent idle | **PRODUCT CONCEPT** | Kandev separates workflow position from runtime state too (`tasks-and-workflows.md`: "Workflow position and runtime state are different") |
| One deliberate human plan gate per stream | **POLICY** (see §15) | |
| Fresh origin/main per stream; branch naming convention | POLICY | |
| Independent cross-model plan audit and code review (`e2e-codex.sh audit/review`) | POLICY + ADAPTER | |
| Loop caps (implement 1 retry, fix 3, CI 2, audit 2) | POLICY | arbitrary numbers; §12 proposes evidence-based stopping |
| `/ship` verify gate: no push without a verdict block | POLICY | closest thing to HAR's commit gate already in use |
| `new-agent`, `pair`, `fleet-toggle`, `deck` | IMPLEMENTATION DETAIL | tmux/curses plumbing |
| `fleet-status` sidecar TSV | IMPLEMENTATION DETAIL (format) wrapping a PRODUCT CONCEPT (explicit completion) | |
| `claude agents --json` polling, transcript tail, tmux capture-pane | **WORKAROUND** | |
| heartbeat sweep in orchestrating-lanes | WORKAROUND (for one-shot idle notices) around a PRODUCT CONCEPT (reconciliation) | |
| Ctrl+T pinning | WORKAROUND | |
| Claude runtime flags, Codex wrapper, Linear MCP calls, Honeycomb hook | ADAPTER | |
| tmux bell hooks | ADAPTER | |

---

## 7. Kandev architecture (from source)

Repo: `kdlbs/kandev`, AGPL-3.0, created 2026-01, 748 stars, 55 contributors, 100+ commits in the last 30 days, weekly releases (v0.93.0 on 2026-09-02). Single Go binary + SQLite (Postgres optional), embedded web UI, `agentctl` sidecar per session, in-memory event bus, WebSocket-first API.

### 7.1 Runtime abstraction
- Agents speak **ACP** (Agent Client Protocol) through `agentctl`; Claude via `@agentclientprotocol/claude-agent-acp@0.70.0`, Codex via `@agentclientprotocol/codex-acp@1.6.0` (`apps/backend/internal/agent/agents/ACP_BRIDGE_VERSIONS.md`). 20+ agents registered (`agents/*.go`).
- **Profiles** hold model, mode, flags, env/secret refs, permissions, MCP servers, passthrough toggle (`docs/public/agents-and-profiles.md`). "Auto-approve all permissions" exists and is off by default; Claude's `--dangerously-skip-permissions` is only consumed in passthrough (`claude_acp.go:21-32`).
- **Passthrough** runs the native TUI in a PTY: full Claude Code UX but "does not provide full structured chat, task MCP, resumable ACP state, usage, plans" (`feature-status.md` row "Bring-your-own TUI/passthrough agent"). This is the central trade-off for us (§8 risk R1).
- **Dynamic profiles / provider routing**: ordered candidate profiles with health-based fallback on auth/quota/rate-limit errors (`tasks-and-workflows.md` "dynamic profile"; Office routing doc). Directly addresses F9.
- ACP carries an `available_commands` event ("available slash commands from the agent", `agentctl/types/streams/agent.go:53-54, 376`) and the Claude adapter points at `.claude/skills` dirs (`claude_acp.go:133-134`), so slash commands are advertised in principle; whether *marketplace plugin* skills (`joel-workflow:e2e`, `ship`, `verify`) load under `claude-agent-acp` (Agent SDK, not the CLI) is **UNVERIFIED** and is the pass/fail of Experiment 1.

### 7.2 Task/session model
- Task = title, prompt, workflow position, repository attachments, sessions, one editable plan with revisions (`tasks-and-workflows.md`). Task states: `TODO, CREATED, SCHEDULING, IN_PROGRESS, REVIEW, BLOCKED, WAITING_FOR_INPUT, COMPLETED, FAILED, CANCELLED` (`internal/task/models/models.go:9-18`). Note `BLOCKED` and `WAITING_FOR_INPUT` are task-level states, not only session-level.
- Session states: `CREATED, STARTING, RUNNING, WAITING_FOR_INPUT, IDLE, COMPLETED, FAILED, CANCELLED` (`coordination.md`, `sessions-and-review.md`).
- **Clarification** is first-class: `internal/clarification/types.go` — `Request{PendingID, SessionID, TaskID, Questions[]{Title, Prompt, Options[]}}`, statuses `pending/answered/rejected/expired/cancelled`; WebSocket `session.clarification_requested`, `session.pending_action_changed`, `session.state_changed` (`pkg/websocket/actions.go`).
- Subtasks (one level in Kanban; trees in Office), `blocked_by` dependencies with cycle checks. Dependency gating of automated launch is wired for regular Kanban tasks and fails closed (`orchestrator/event_handlers_dependencies.go:29-40`, `backendapp/orchestrator.go:172-175`); only the *editing UI* is Office-only (`automation-and-mcp.md:386`, `feature-status.md:52`).
- `run_code_review` on step entry can use a different agent profile than the implementer, but "a failed review does not block the transition" (`workflow/models/models.go:39-45`) — acceptance must be enforced by the step-completion signal or the human gate, not by this action.
- Crash recovery: lazy resume after backend restart via ACP `session/load` or history injection (`docs/task_session_resume.md`).
- Idempotent creation: `external_id` per workspace on `create_task_kandev` / `POST /api/v1/tasks` (`automation-and-mcp.md:473-494`).

### 7.3 Repositories and environments
- Executors: Worktree (default), Local (the selected checkout itself), Local Docker, Kubernetes, SSH, Sprites (`executors.md`). Executor profile = env/secret refs + prepare/cleanup script + MCP policy.
- Worktree path is `{KANDEV_HOME}/tasks/{taskDir}/{repoName}[-{branchSlug}]` (`internal/worktree/config.go:86-102`) — **not** under the repo's `.worktrees/`. Branch template default `feature/{title}-{suffix}`, configurable per repository branch policy.
- Repository **setup script** runs in the fresh worktree after creation; failure is non-fatal with a warning (`worktree/manager_cleanup.go:385-429`, `git-operations.md:138`). Repository cleanup script runs before removal; audited cleanup preserves branches with unique commits (`git-operations.md:269-291`).
- Multi-repo tasks: one worktree per attached repo, per-repo PRs (Worktree executor only).

### 7.4 Coordination and workflows
- Workflow = ordered steps with events: `on_enter` (`auto_start_agent`, `enable_plan_mode`, `reset_agent_context`, `configure_session`, `run_code_review`, `queue_run`, `ensure_participant_seat`…), `on_turn_start`, `on_turn_complete` (`move_to_next/previous/step`, `disable_plan_mode`), `on_exit`, `on_agent_error` (`workflow/models/models.go:11-134, 328-345`). Per-step `AgentProfileID`, `WIPLimit`, `PullFromStepID`, `StageType (work|review|approval)`, `AutoAdvanceRequiresSignal` (explicit `step_complete_kandev` MCP signal) (`models.go:217-250`).
- Built-in templates: Kanban, Plan & Build, Architecture, **Feature Dev** (Spec → Work → Review[reset context] → QA → PR → CI Fixup), PR Review (`docs/workflow-tips.md`).
- Human gate = a step whose on_turn_complete is "Do nothing (wait for user)" (`coordination.md:109`).
- Agent-to-agent: `spawn_session_kandev`, `message_task_kandev` (queued/interrupt), `stop_task_kandev`, coordinator parent with `on_children_completed` (`sessions-and-review.md`, `coordination.md`).
- Multi-participant steps with roles reviewer/approver/watcher/collaborator/runner and `WorkflowStepDecision` (open-ended verdicts for quorum) exist in the model (`workflow/models/phase2.go`) but `feature-status.md:44,57` says quorum/participants are **Office-only, in progress, feature-flagged and off in the production profile**.

### 7.5 Human interaction
- Threads view: one column per task with an active primary session; header shows "explicit permission or question that needs your attention" (`sessions-and-review.md`). Notifications: local/WebSocket, system/OS, Apprise (`notifications/models`).
- Office **Inbox** spec: computed view over pending approvals, budget alerts, agent errors, review requests, clarification requests; `execution_policy` of ordered review/approval stages (`docs/specs/office/requirements/inbox.md`). Draft, feature-flagged.
- Plan approval: Plan step saves plan via MCP and stops; human edits in UI and moves the card (`workflow-tips.md` Plan & Build).

### 7.6 Integrations (Linear)
- Linear GraphQL client; **issue watch**: `IssueWatch{WorkflowID, WorkflowStepID, RepositoryID, BaseBranch, Filter{TeamKey, StateIDs, Assigned me|unassigned, Priorities, LabelIDs, EstimateMin/Max, CreatorID}, AgentProfileID, ExecutorProfileID, Prompt (with {{issue.*}} placeholders), PollIntervalSeconds, MaxInflightTasks, SortBy}` (`linear/models.go:209-244`). Dedup by `UNIQUE(issue_watch_id, issue_identifier)` (`IssueWatchTask`). Dispatch path acquires a watcher slot honouring `MaxInflightTasks` (`orchestrator/watcher_dispatch_wiring.go:224`, `source_linear.go:108`). Poll tick 60 s (`linear/poller.go:19`).
- Write-back: `SetIssueState` mutation exists and is exposed over HTTP/WS (`linear/graphql_client.go:433`, `handlers.go:54,414`) but is **user-driven**; no automatic state transition on task create/complete was found (UNVERIFIED beyond grep of orchestrator/automation callers).
- Status: "Limited — search/browse, state changes, task launch, watches require credentials; watch reads 50 matches or ≤250 with local sorting" (`feature-status.md:107`).

### 7.7 Extensibility
- WebSocket `/ws` request/response/notification envelope; catalogue of `task.*`, `session.*`, `workflow.*`, `orchestrator.*` actions (`pkg/websocket/actions.go`). Explicitly "internal application protocol, not a versioned public SDK"; **no client authentication** on `/ws`; per-client 256-frame queue drops under backpressure, "notifications are invalidation hints" (`websocket-api.md`).
- HTTP `/api/v1/*` routes, external MCP with 42 tools including `create_task_kandev` with `external_id` (`automation-and-mcp.md:690-846`).
- Plugin SDK: Go subprocess + native UI bundle, events/webhooks (`plugins-authoring.md`).
- Automations: cron, webhook, GitHub PR open/merged triggers (`feature-status.md:110`).

### 7.8 Observability
- OTel tracing for transport and agent protocol layers, no-op without `OTEL_EXPORTER_OTLP_ENDPOINT` (`docs/tracing.md`); stats page computed from `task_sessions`, `task_session_turns`, `task_session_commits` (`docs/stats.md`); session cost plugin (roadmap). No first-party Honeycomb integration; env-var OTLP endpoint suffices.

---

## 8. HAR architecture (from source)

Repo: `os-factory/har`, Apache-2.0, created 2026-06, 85 stars, 7 contributors, 100+ commits in 30 days, v1.12.0 (five releases in two days, 2026-09-02/03). TypeScript CLI + MCP server; Next.js Mission Control with Postgres.

- **Harness contract** `.har/` = `harness.env` (schema-validated), `stages.json` (stages, `verificationStages`, tiers quick/full, `agentSlots`, `commitGate`), `.har/stages/`, hooks, plugins (`docs/.../harness-files.md`, `guides/stages.md`).
- **Slot** = numbered reusable lane (`HARNESS_AGENT_SLOT_MIN/MAX`), each launch creates a **fresh** worktree + branch outside the main checkout, `.env.agent.<id>`, and a per-slot DB `agent_<id>` cloned from `HARNESS_TEMPLATE_DB` with `createdb -T` (`src/runtime/agent-ops.ts:163`, `launch.ts:181`). Ports = base + slot × step (`slot-ports.ts`). Infra (Postgres, minio, mailpit) runs as shared Docker services with persisted host ports in `.har/state/infra.env`. "A slot is not a permanent environment. Every normal launch creates a fresh session" (`concepts.md`). Occupied slots always block.
- **Run records** under `.har/runs/…json`; **validation** = tree hash of the whole working tree → `.har/validations/<treeHash>.json` (`src/core/validations.ts`); **commit gate** pre-commit compares staged tree with a passing full validation (`block|warn`, scope `worktrees|all`); `har env complete` refuses unless the current tree matches a passing full validation (`guides/verification.md`).
- **Work identity** (ADR 0001): `WorkUnit → WorkAttempt → slot session → runs → validation binding`; work unit is caller-provided (`--work-id INT-123 --work-source linear --work-url …`); explicit terminal outcomes `completed|abandoned`; everything else derived from evidence; "teardown never implies completion".
- **Factory lines**: declared multi-station programs with a cumulative gate ratchet; "agents hand off, they do not ship" (`guides/factory-lines.md`). Orchestration is explicitly *not* HAR's job: "Queueing, dispatch, tracker adapters, and agent invocation are separate later decisions" (ADR 0001).
- **Telemetry**: installs `@osfactory/otel-hook` into Claude/Codex/Cursor hooks, exports usage/events/spans to Mission Control with `har.work_unit_id`/`har.attempt_id` (`src/core/otel-hooks.ts`; Prisma `AgentSessionUsage{tokens*, costUsd, workUnitId, attemptId}`).
- **Singletons**: no concept found (`grep -ri singleton|exclusive|mutex src/core src/harness` → nothing).
- Public seam: `RunService` with injectable `StageExecutor` (`src/core/run-service.ts:95`), MCP tools `har_launch_environment`, `har_run_verification`, `har_complete_environment` (`reference/mcp.md`).

---

## 9. Capability matrix

Legend: **Cur** = current Operator/Fleet, **K** = Kandev, **H** = HAR. Verdict: who is stronger / equivalent / different / not needed.

| Capability | Cur | K | H | Verdict |
|---|---|---|---|---|
| Agent agnosticism | Claude launch + Codex via wrapper | 20+ ACP agents, profiles | any MCP agent (does not launch agents) | **K** |
| Model agnosticism | `--model` per stream; Codex effort | per profile + dynamic fallback routing | n/a | **K** |
| Multi-agent collaboration (planner/implementer/reviewer) | inside /e2e (Fable plans, Sol implements, both review) | per-step profiles + `reset_agent_context`; participants/quorum Office-only | factory-line stations (declared, not run) | **K** for structure, **Cur** for the actual review policy |
| Multi-agent concurrency | 3–6 bg sessions | unlimited tasks, WIP limits per step | slots 1–5 | K ≈ Cur; H equivalent |
| Multi-repo | lanes per repo; one repo per stream | one task spanning repos, per-repo PRs | one repo per harness | **K** |
| Warm dev environments | lanes: fixed DB/ports/Redis, caches, singleton | worktree in Kandev dir; Local executor = the checkout | ephemeral slot; shared infra containers | **Cur** (different abstraction) |
| Worktree isolation | `bin/create_worktree` | built-in | built-in | equivalent |
| DB/port/resource isolation | repo-level (`worktree_offset.rb`) | delegated to repo setup script | built-in template-DB clone + port lanes | **H** generically; Cur already solved for magicnotes |
| Singleton resources | mn1 owns tunnel (convention) | none | none | **Cur** (weak, convention only) |
| Task readiness | none (human decides) | issue-watch filter (state/label/assignee/priority) | none | **K** mechanism; policy still ours |
| Queueing | LLM-held list | persisted tasks, WIP queue, pull | occupied-slot blocking only | **K** |
| Scheduling | LLM heartbeat | watch poll + max in-flight + WIP/pull + dependencies | none | **K** |
| Lane allocation | human/LLM picks lane | executor profile per watch/step | slot number | fundamentally different; Cur's "lane = host, many worktrees" is not modelled by either |
| Automatic refill | LLM sweep | watch re-dispatch when slot frees | none | **K** |
| Dependencies | none | `blocked_by`, gates automated launch (fails closed), only successful completion resolves; editing UI Office-only | parent work unit only | **K** |
| Cross-agent coordination | none | messages, spawn, coordinator, children-completed | none | **K** |
| Reviewer independence | fresh Codex thread / fresh subagent | `reset_agent_context`, different profile per step | n/a | equivalent; K more declarative |
| Human attention routing | BLOCKED-first inbox, bell on transitions | Threads + notifications; Office Inbox (draft) | Mission Control (evidence view, no inbox) | **Cur** today; K catching up |
| Blocked-state detection | `state==blocked && status!=idle` heuristic | `WAITING_FOR_INPUT`, `clarification_requested` event | none | **K** |
| Question UX | peek + press 1–9 (tmux) | structured options in UI, answer via WS/MCP | none | **K** |
| Plan approval | AskUserQuestion, one gate | Plan step + editable plan + manual move | handoff options, human approves | K ≈ Cur |
| Transcript inspection | JSONL tail, `claude logs` | full structured chat, walkthroughs | run logs only | **K** |
| Interactive takeover/pairing | `claude attach` in pair window | passthrough PTY / send message; no attach to an ACP session's terminal | none | **Cur** (attach to the *same* live session is unique) |
| External-ticket lifecycle | pick-up moves In Progress; nothing moves Done | watch creates task; `SetIssueState` manual | work unit metadata only | all weak; policy gap is ours |
| Completion semantics | sidecar `complete` ≠ idle | workflow Done step ≠ runtime state | `completed` only with passing full validation of exact tree | **H** strongest; K adequate; Cur explicit but self-reported |
| Deterministic verification | /verify (agent-driven evidence) | `run_code_review`, CI fixup step | stages + tiers + tree hash | **H** |
| Evidence | verdict block in ship summary; screenshots in PR | plan revisions, review findings, commits | run records, validations, artifacts, MC | **H** |
| Retries | TSV-counted caps | provider fallback, CI fixup rounds, GitLab auto-fix cap 10 | `--resume` partial launch | equivalent |
| Crash recovery | daemon respawn; sidecars inert | lazy session resume; `external_id` idempotency | slot registry `failed/starting` resumable | **K** |
| Reconciliation | heartbeat sweep (LLM) | pollers + queue promotion + cleanup retry | derived state from evidence | **K/H** |
| Cleanup | manual two-step | audited async cleanup, branch preservation rules | teardown keeps branch | **K** |
| Provenance | none (session uuid) | task id + `external_id` + sessions + commits | WorkUnit → Attempt → runs → validation | **H** conceptually; K sufficient |
| Observability | Honeycomb OTel (Claude+Codex) | OTel tracing, stats | OTel hooks → MC | equivalent; Cur's Honeycomb board is the asset |
| Cost/token telemetry | Honeycomb | session cost plugin | MC usage table | equivalent |
| Skill/tool telemetry | `workflow-ledger` hook | none | none | **Cur** |
| Operator ergonomics | tmux/curses, keyboard-first | web UI, mobile | web dashboard | Cur for 3–6 streams; K for review |
| Extensibility | shell scripts | WS/HTTP/MCP/plugins (unversioned) | CLI/MCP, RunService seam | **K** |
| Local-first | yes | yes (SQLite) | yes (Postgres via Docker for MC) | equivalent |

---

## 10. What the current system genuinely does better or differently

**A — solved better by Kandev:** session lifecycle, blocked/clarification state, queue/WIP/refill, dependencies, transcript inspection, crash recovery, multi-repo, provider fallback.
**B — solved better by HAR:** binding "verified" to an exact tree, evidence records, commit gate.
**C — common, not differentiating:** worktree creation, tmux layout, bell notifications, PR creation.
**D — genuinely useful and missing/weaker in both:**
1. **Attention-first inbox contract** — typed rows, BLOCKED first, bell only on BLOCKED/COMPLETE transitions, 48 h fold. Kandev's Threads is process-shaped; Office Inbox is a draft.
2. **Warm lane as a host with singleton ownership** — neither project has "this environment owns the Twilio tunnel". Kandev's Local executor + setup script can *emulate* it; HAR cannot (fresh slot each launch).
3. **Live attach to the running session** (`pair`) — Kandev can message a session or run passthrough, but you cannot drop into the terminal of an ACP-driven Claude.
4. **The engineering policy encoded in `/e2e`, `/ship`, `/verify`** — cross-model plan audit, verdict-gated push, bot-review consolidation, loop caps in a ledger. Kandev's Feature Dev template is a generic sketch of this.
5. **Skill/MCP attribution telemetry** (`workflow-ledger`).
**E — unnecessary complexity to delete:** `fleet-toggle` (comparison of two inboxes), tmux gate-answering, five copies of the `claude agents --json` probe, `closure-sweep`'s blocked-row half, `pair`'s name-resolution table, `.claude/worktrees` lazy isolation alongside `.worktrees`.

**Lifecycle semantics verdict.** `session state + sidecar + Linear + heartbeat + gate` is *three* reconciliation loops over *four* sources of truth with no owner. That is duplicated complexity, not robustness. The durable idea inside it, "completion is a separate, explicit, evidence-bearing record", survives; the mechanism should not.

**Queue/refill verdict.** Kandev's issue watch + `MaxInflightTasks` + WIP/pull + `blocked_by` is a superset of `orchestrating-lanes`, persisted, and not dependent on an LLM staying alive.

**TUI/operator speed verdict.** For 3–6 streams the keyboard inbox is faster than a browser board. It should become a client of Kandev's WebSocket stream rather than own state (§25 confirms feasibility, with the unauthenticated-endpoint caveat).

---

## 11. What Kandev makes obsolete

`new-agent` (task create + auto-start), `fleet`'s data plane (sessions, sidecars, transcript tail), `orchestrating-lanes` (watch + WIP + refill), `pair`'s session lookup (Kandev task ids), `closure-sweep`'s blocked-row scan (Threads/Inbox), the heartbeat sweep (queue promotion + pollers), `fleet-status` as a *file* (becomes a workflow step transition + completion record), `claude rm` + manual worktree removal (audited cleanup).

Not obsolete: `bin/create_worktree` (becomes the repository setup script), `gmp-all`/`lane-sweep`/`clone-status` (lane hygiene is outside Kandev's scope), the Honeycomb telemetry, `/e2e`, `/ship`, `/verify`, `deck` as a tmux layout if a TUI survives.

---

## 12. What HAR adds (and what it would cost)

Adds: tree-hash-bound validation records; commit gate; run records with trigger/duration; work unit → attempt identity; Mission Control cost per attempt.

Costs if adopted as runtime: a second worktree/DB provisioning system beside `create_worktree` and Kandev's worktrees; ephemeral slots (no warm caches, no singleton); a second dashboard (MC) beside Kandev; `.har/` contract to adapt and maintain for a Rails app whose harness is already `bin/setup` + `worktree_offset.rb`; Docker infra assumptions. HAR itself says orchestration is above it (ADR 0001), so it would sit *under* Kandev and duplicate Kandev's worktree executor.

Recommendation: adopt the **ideas** (Option D). Concretely: `/verify` writes `.e2e/validations/<treeHash>.json` with the verdict block and evidence pointers; `/ship` refuses to push if `git rev-parse HEAD^{tree}` (plus dirty-tree hash) has no passing record; completion (§17) requires that record. That is ~60 lines of shell inside skills the repo already owns.

---

## 13. Readiness contract

The workspace already has the label `ready-for-agent` ("Scoped, dependency-aware ticket ready for an engineering agent"), used by the Notes team on 17 tickets, and `factory:done_manually` on the Talk team. Readiness is emerging as an organisation convention; reuse the label rather than inventing a state.

**Proposed contract: READY = Linear label `ready-for-agent` + state `Todo` + no open `blocked by` relations + assignee me-or-unassigned + a passing agent readiness check at pickup.**

| Input | Mandatory | Recommended | Discoverable by agent | Escalate if absent |
|---|---|---|---|---|
| Problem / outcome statement | ✅ | | | ✅ "BLOCKED ON PRODUCT CONTEXT" |
| Acceptance criteria (observable) | ✅ | | | ✅ |
| Affected systems / entry points | | ✅ | ✅ (code search) | only if search is ambiguous |
| Architectural constraints | | ✅ | ✅ (`docs/*.md` guides) | if plan crosses a guide it cannot satisfy |
| Linked design/discussion | | ✅ | ✅ (Linear relations, comments) | no |
| Dependencies | ✅ (as Linear relations) | | ✅ | ✅ if blocker open |
| Known risks / rollout expectations | | ✅ | partially (feature flags, migrations) | ✅ if plan touches migration/flag/external contract and ticket is silent |
| Reproduction steps (bugs) | ✅ for `Bug` label | | ✅ (Sentry link) | ✅ |
| Estimate ≤ M | | ✅ | | split proposal instead of implementation |

Where it lives: label + state + relations are Kandev issue-watch filter inputs (`SearchFilter{StateIDs, LabelIDs, Assigned}`); the readiness *check* is the first `/e2e` stage (extend `pick-up-linear-ticket`): it must output `READY` or `UNDERSPECIFIED: <missing>` and, on the latter, post the gap as a Linear comment, remove the label, and end the task in a typed "needs product context" state. The system refuses underspecified work rather than inventing requirements.

---

## 14. Scheduler / state model

Durable, not LLM-owned. Kandev supplies it; the configuration is ours.

```
Linear watch (60 s poll; filter: team INT, state Todo, label ready-for-agent, assignee me|unassigned, sortBy priority)
   │  UNIQUE(watch, issue) reservation → task created with external_id = INT-123 → auto-start in step "Readiness"
   ▼
Workflow: Readiness → Plan → [Plan gate] → Implement → Cross-model review → Verify → Ship → In review (human) → Done
   │  WIP limit on Implement = number of lanes able to host that repo (3); Pull from Plan
   │  blocked_by resolves only on predecessor COMPLETED
   ▼
Executor profile per lane group (repo + WORKTREE_OFFSET strategy); prepare script = bin/create_worktree refresh
```

Ranking inputs and where they live: priority (Linear), dependencies (Kandev `blocked_by`, mirrored from Linear relations by the readiness stage), capacity (WIP limit + `MaxInflightTasks`), risk (label or plan-derived tier → chooses which workflow/gates), environment (executor profile; the Twilio singleton is a separate workflow/executor bound to mn1 only), model availability (dynamic profile fallback), cost (Office budgets are in progress; until then a daily cap enforced by the watch's max in-flight), human review capacity (WIP limit on the "In review" step so the pipeline pauses when 3 PRs await Joel).

Leases: the watch reservation is the lease; `external_id` makes re-creation idempotent; Linear stays authoritative for business state; Kandev for execution state.

---

## 15. Multi-agent collaboration model

What Kandev provides today (production profile): per-step agent profile, `reset_agent_context` on step entry, `run_code_review` action, `spawn_session_kandev`/`message_task_kandev`, dynamic provider fallback. What is Office-only/in-progress: participants, quorum decisions, coordinator-led teams.

What ours still needs to own: the *content* of critique (refute-first review, agreement labels `[both]/[claude-only]/[codex-only]`, arbitration, stopping rules), plan audit before the human sees the plan, and the bounded fix loops. Today that lives in `/e2e`; it should stay there and be split so each Kandev step invokes one stage.

Topology to run first (matches the north star and today's practice):

```
Plan (Claude, plan mode)  →  Plan audit (Codex, fresh context, read-only)  →  human gate if tier ≥ 2
Implement (Codex; Claude fallback via dynamic profile)  →  Self-review (same session, native `codex review`)
Independent review (Claude, reset_agent_context, refute-first)  →  fix (implementer session) → re-verify findings only
Verify (/verify; deterministic stages first)  →  Ship (/ship)
```

Alternatives to evaluate later, not now: independent dual planning with a comparator (cost ×2 on planning; reserve for tier-3 architecture tickets), specialist reviewers (security only for tickets touching auth/PII/migrations). Properties enforced: reviewer never inherits implementer context (step boundary), disagreements are surfaced as `[claude-only]/[codex-only]` items with the human deciding only when both a `[both]` finding is contested or a review disagrees with the plan, collaboration cost bounded by per-step effort and loop caps recorded in the ledger.

---

## 16. Human attention policy

Risk tiers, assigned by the readiness stage from ticket labels and plan content, re-evaluated after planning:

| Tier | Signals | Human gates | Inbox item types |
|---|---|---|---|
| 0 routine | ≤2 files, tests exist, no migration/flag/contract change, `Bug` with repro | none before PR | READY FOR CODE REVIEW |
| 1 standard | multi-file within established patterns | plan gate **skipped** unless Codex audit says REVISE twice | READY FOR CODE REVIEW, MODELS DISAGREE |
| 2 significant | migration, feature flag, external API/contract, cross-boundary, UI copy end-users see | plan gate | NEEDS PLAN REVIEW |
| 3 architectural | new service/abstraction, security/PII, data migration with backfill, scope expansion | plan gate + design note | NEEDS ARCHITECTURE DECISION |

Never interrupts: test fixes, lint, retries, ordinary bot-review comments, environment recovery, moving a ticket to In Review when evidence passes (this removes two of today's three BLOCKED rows).

Verdict on "one deliberate plan gate per stream": a durable *policy* only above tier 1. At tier 0–1 it costs a human round-trip for work the human will review as a PR anyway. Make the gate conditional, and make "audit REVISE twice" and "models disagree" the escalation triggers instead of "every plan".

Fleet as a human attention router: rows are Kandev tasks whose session is `WAITING_FOR_INPUT` with a clarification (typed by the question's `Title`), tasks in the "In review" step, tasks with `FAILED` sessions or failed verify runs, and readiness rejections. Ordering: MODELS DISAGREE / HIGH-RISK VERIFICATION FAILURE → NEEDS ARCHITECTURE DECISION → NEEDS PLAN REVIEW → BLOCKED ON PRODUCT CONTEXT → READY FOR CODE REVIEW.

---

## 17. Completion / evidence contract

"Agent finished" is never completion. A stream is complete when every row below is satisfied and recorded:

| Requirement | Owner | Evidence artefact |
|---|---|---|
| Acceptance criteria evaluated | /e2e final stage | checklist in PR body, each AC → test or verify line |
| Unit/integration tests pass | CI (GitHub) | green checks |
| /e2e path completed with loop counts | /e2e | `.e2e/sessions.tsv` attached to Kandev task (plan document) |
| Deterministic verification | /verify | `.e2e/validations/<treeHash>.json` with verdict block; HEAD tree matches |
| Independent cross-model review done; findings resolved or accepted | /e2e Stage 5/6 | findings file with agreement labels; `[e2e unresolved]` PR comments |
| No unresolved clarification | Kandev | no pending clarification on task |
| Branch clean, rebased on required base | /ship | `git status` empty; behind-count 0 |
| PR created/updated with What/Why and screenshots when UI | /ship + `writing-pr-descriptions` | PR URL |
| Ticket state consistent | /ship (→ In Review); GitHub merge automation (→ Done) | Linear state + PR link attachment |
| Risk-specific checks (migration dry run, flag default off) | tier policy in /e2e | verify lines |
| Environment released, worktree reaped | Kandev audited cleanup | task archived |

Kandev's role: the workflow step `Ship → In review` may only be entered when the agent emits `step_complete_kandev` (`AutoAdvanceRequiresSignal`) after producing the artefacts; `Done` is entered by the PR-merged automation, not by the agent. Kandev's own `run_code_review` never blocks a transition, so the acceptance check (all rows above present) has to run in `/ship` before the signal is emitted — the agent's signal is a claim, the artefacts are the proof. While a human decision is pending, the model process should be released and the task, checkout, evidence and decision kept durable; nothing should depend on a Claude session staying alive. HAR's contribution is the tree-hash rule: any edit after verification invalidates the record and `/ship` must re-verify.

---

## 18. Reliability / reconciliation model

Principle: events for latency, periodic reconciliation for correctness — already how Kandev is built (pollers, queue promotion, lazy resume, cleanup retry) and how the current heartbeat sweep was meant to work.

| Concern | Today | With Kandev + policy |
|---|---|---|
| Persisted vs derived | sidecar persisted; buckets derived from Claude state | task/session/step persisted in SQLite; readiness/completion derived from artefacts |
| Leases / duplicate pickup | none | watch reservation + `external_id`; WIP limits |
| Crashed orchestrator | scheduler dies with the LLM session | backend restart → lazy resume; pollers resume |
| Crashed agent | daemon respawn; state.json | session `FAILED` → `on_agent_error` transition → inbox item |
| Orphaned worktrees | 25 today | audited cleanup on archive; branches with unique commits preserved |
| Stale sessions | 60-min retirement | `IDLE` sessions persist; resume on demand |
| Broken environment / poisoned DB | manual | prepare script fails non-fatally → typed failure; **gap**: Kandev will still start the agent; guard in `/e2e` Stage 2 must refuse to proceed when `bin/create_worktree` refresh failed |
| Lost notifications | bell only while inbox open | WS notifications are invalidation hints; the TUI must refetch on reconnect; system notifications as backup |
| Linear/GitHub API failures | skill stops and reports | poller `LastError`, watch self-heal; ship's bounded retries |
| Reconciliation still ours | heartbeat sweep | a nightly job: Linear `In Progress` with no live Kandev task → inbox; Kandev `COMPLETED` with Linear not Done → inbox; lanes dirty → `gmp-all` |

Necessary even with Kandev: lane hygiene (`gmp-all`, `lane-sweep`), the Linear↔Kandev drift check, and the tree-hash re-verify rule.

---

## 19. Provenance / telemetry

Canonical identity: **the Kandev task id**, with `external_id = <Linear identifier>`. Do not invent a separate `work_id`; HAR's ADR 0001 shape (WorkUnit → Attempt) maps to Kandev task → session. Claude/Codex session ids, Codex thread ids from `.e2e/sessions.tsv`, review agent sessions, verification records, commits and the PR are metadata under the task.

Honeycomb correlation: set `OTEL_RESOURCE_ATTRIBUTES=work.id=<INT-123>,kandev.task_id=<id>,work.role=<planner|implementer|reviewer|verifier>` in the executor profile / prepare script so both Claude Code and Codex exporters carry it (Claude reads the env at startup; Codex `[otel]` config picks up resource attributes — **UNVERIFIED** for Codex per-process attributes; Experiment 2 checks). Extend `otel-workflow-ledger.sh` to include `work.id` from the environment. Keep the personal Honeycomb team as the vendor-neutral layer; Kandev's own OTel can point at the same endpoint.

Evaluation metrics and their sources:

| Metric | Source |
|---|---|
| Escaped defects | Sentry/incident links back to PR → task |
| Review findings by source and agreement label | `.e2e` findings files → task document |
| Human corrections | count of Revise answers, PR review comments by Joel |
| Plan rejection rate | clarification responses (Revise/Approve) |
| Iterations to convergence | `sessions.tsv` |
| e2e/deterministic failures caught pre-review | verify records with 🔴 before PR |
| Time-to-reviewable-PR, elapsed | Kandev task timestamps |
| Agent compute, tokens, cost | Honeycomb by `work.id`, `work.role`, `model` |
| Human attention minutes | time between inbox item creation and answer (Kandev clarification timestamps) |

Comparison design (Claude-only vs Codex-only vs cross pairs vs full collaborative): one Kandev workflow per arm, tier-0/1 tickets assigned round-robin by the watch (alternate `AgentProfileID` per watch), 10 tickets per arm before reading the board. Report quality per human-minute and per dollar, not defect count alone.

---

## 20. Target architecture options

| Option | Complexity | Maintainability | Reliability | Autonomy | Human attention | Migration | Vendor coupling | Observability | Operator UX | Multi-model | Extensibility |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A own system + AgentRuntime | high (build runtime, queue, leases) | low (one maintainer) | low→medium | medium | good (own inbox) | none | Claude+Codex CLIs | good | best | manual | poor |
| **B Kandev control plane** | medium | medium (upstream churn) | high | high | good via client | moderate | Kandev + ACP adapters | good | good with TUI client | declarative | good |
| C Kandev + HAR | high (two runtimes) | low | high | high | good | hard | two projects | best | two dashboards | declarative | good |
| **D Kandev + HAR ideas** | medium | medium | high | high | good | moderate | Kandev | good | good | declarative | good |
| E simpler: fix current defects | low | medium | medium | low (still manual dispatch) | good | trivial | Claude CLI | good | best | manual | poor |

A duplicates Kandev's architecture for one user. C pays for two environment managers. E does not reach N1/N3/N7. **D (B plus the evidence rule) is recommended, gated by Experiment 1; E is the fallback if ACP breaks the skills.**

---

## 21. Recommended architecture

```
Linear (READY = label ready-for-agent + Todo + no blockers)
   │  Kandev issue watch, external_id = ticket
   ▼
Kandev workflow "beam-e2e": Readiness → Plan → Gate(tier≥2) → Implement → Review(reset ctx, other model) → Verify → Ship → In review → Done(PR merged)
   │  per-step agent profile; WIP limits; blocked_by
   ▼
Kandev Worktree executor over the lane repo (mn1..mn5 registered as repositories)
   │  repository setup script = bin/create_worktree (refresh) with WORKTREE_OFFSET=<task dir>
   │  mn1-only executor profile for telephony work (singleton by policy)
   ▼
Agents: Claude (ACP; passthrough fallback), Codex (ACP or e2e-codex.sh inside the Claude session)
   │  /e2e, /ship, /verify remain the policy; each Kandev step invokes one stage
   ▼
Evidence: .e2e/ ledger + validations/<treeHash>.json → task documents; PR; Linear
   ▼
Fleet TUI (thin): WS client → typed attention rows; answer clarification via WS; open task in browser for deep review
Honeycomb: Claude + Codex + ledger hook tagged work.id / role
```

---

## 22. Keep / Replace / Integrate / Delete

| Current component | Keep | Replace | Integrate | Delete | Reason |
|---|---|---|---|---|---|
| `fleet` (TUI) | concept | data plane | as WS client of Kandev | `fleet-toggle`, gate screen-scrape | attention router is valuable; polling/scraping is not |
| `new-agent` | | ✅ by Kandev task create (watch or `create_task_kandev`) | | | still keep a one-liner `kandev-task <lane> "<prompt>"` for ad-hoc investigations (8 of 11 dispatches) |
| `pair` | until Kandev attach exists | | | | live attach is unique; keep for passthrough sessions |
| `deck` | ✅ as tmux layout | | | | cheap |
| `fleet-status` | | ✅ by `step_complete_kandev` + completion record | | | single-writer idea survives as a step signal |
| lane provisioning (`bin/create_worktree`, `worktree_offset.rb`) | ✅ | | ✅ as Kandev repository setup script | | fail-closed provisioning is the asset |
| worktree lifecycle (`claude rm` + manual) | | ✅ Kandev audited cleanup | | ✅ | |
| `orchestrating-lanes` skill | | ✅ Linear watch + WIP + blocked_by | | ✅ after migration | LLM should not hold scheduler state |
| queue/refill logic | | ✅ | | | |
| heartbeat/completion detection | | ✅ pollers + step signals | keep nightly Linear↔Kandev drift check | | |
| Linear integration (`pick-up-linear-ticket`) | ✅ | | extend with readiness check + In Review move | | |
| telemetry hooks | ✅ | | add `work.id` | | |
| `/e2e` | ✅ policy | | split into per-step stages; conditional gate by tier | | |
| `/ship` | ✅ | | add tree-hash validation rule; move ticket to In Review | | |
| `/verify` | ✅ | | write validation record | | |
| Claude-specific session parsing (5 scripts) | | | | ✅ | replaced by Kandev API |
| `gmp-all`, `lane-sweep`, `clone-status` | ✅ | | | | lane hygiene is outside both projects |
| `closure-sweep` | PR half | | blocked half → Kandev | | |

---

## 23. Smallest experiments

**Experiment 1 — `/e2e --dry-run` through Kandev on an existing lane (riskiest assumption first).**
Prerequisite (Phase 1): change `/e2e` Stage 2's `CLAUDE_JOB_DIR` check to real checkout-ownership detection so it cannot nest a worktree under Kandev.
Setup: install Kandev locally (Homebrew), register `~/engineering/mn3` as a repository; repository setup script = a 10-line wrapper that exports a reserved, known-free `WORKTREE_OFFSET` then runs `bin/create_worktree` refresh; Claude ACP profile in ordinary mode (not autopilot), effort/model matching `new-agent`; Kanban workflow. Create one disposable task: prompt `/e2e --dry-run INT-<tiny tier-0 ticket>`.
Pass only if all hold: (a) the *installed* `joel-workflow:e2e` skill and the Codex plan audit actually execute, with identifiable artefacts (`.e2e/plan-audit-*.out`), not an agent paraphrasing them; (b) Rails boots against the offset DB, no collision with mn3's lane DB; (c) the plan question appears through `list_pending_questions_kandev` / `GET /api/v1/clarification` with Approve/Revise options; (d) after a controlled runtime stop, one `answer_question_kandev` resumes the task exactly once with artefacts and checkout intact; (e) no nested worktree or unintended repo mutation; dry-run stops before ship.
Fail modes: (a) fails → skills need passthrough → no structured state → Option E. (b) fails → fix the adapter, retry once. (c)/(d) fail → `AskUserQuestion` is not mapped to a clarification or resumption is lossy → Kandev cannot own the gate; re-evaluate. Missing skill discovery or a terminal-only question is a **fail**, not permission to switch to passthrough silently.
Reversible: delete the Kandev task and its worktree under `~/.kandev/tasks`; nothing in the lane or dotfiles changes.

**Experiment 2 — provenance tag survives both exporters.** In the same task, set `OTEL_RESOURCE_ATTRIBUTES` in the executor profile and check Honeycomb for `work.id` on `claude-code` and `codex_exec` events. Pass: both present. Fail: Codex needs `[otel]` resource attrs per config, so fall back to tagging via the wrapper.

**Experiment 3 — read-only Fleet over Kandev.** 150-line Python WS client: subscribe, list tasks + sessions, bucket by `WAITING_FOR_INPUT`+clarification / `REVIEW` step / `FAILED`. No dispatch. Pass: same rows as today's fleet for the same work, without `claude agents`.

**Experiment 4 — Linear watch as READY intake, dry.** Create an issue watch with filter `team INT, state Todo, label ready-for-agent, assignee me`, `maxInflightTasks 1`, `start_agent` disabled (create without starting). Label one ticket. Pass: exactly one task appears with `external_id` and no duplicate on the next poll.

**Experiment 5 — tree-hash evidence rule in `/ship`.** Add the validation record write to `/verify` and the check to `/ship` in a dotfiles branch; run on a normal ticket. Pass: editing a file after verify makes `/ship` refuse to push until re-verified. Independent of Kandev; can run first.

**Experiment 6 — cross-model review value.** For 5 tier-0/1 tickets, record findings from Sol self-review vs Fable refute-first review with agreement labels (already in `.e2e`), and count which findings Joel would have caught in PR review. This measures whether the second model is paying for itself.

---

## 24. Migration sequence

| Phase | Capability gained | Replaced / retained | Main risk | Rollback | Proof to continue |
|---|---|---|---|---|---|
| 0 (done) | This audit | — | — | — | — |
| 1 | Cheap defect fixes: `/e2e` final stage moves Linear to In Review and calls `fleet-status`; `new-agent` names worktree after ticket; fleet reads `state.json` `needs`; `bin/cleanup_worktrees` sweep | retained all | none | git revert dotfiles | two of three BLOCKED rows disappear |
| 2 | Experiment 5: tree-hash evidence in `/verify`+`/ship` | retained | false refusals | flag off in skill | one ship refuses correctly after post-verify edit |
| 3 | Experiment 1 (+2): one `/e2e` through Kandev on mn3 | new-agent for that task | ACP vs skills | delete task | 4 pass criteria |
| 4 | Experiment 3: read-only Fleet client | fleet data plane | WS unauthenticated (bind loopback) | keep old fleet | parity of rows |
| 5 | Workflow `beam-e2e` with per-step profiles, reset-context review, tier-conditional gate | orchestrating-lanes review policy | Feature Dev template drift | run old `/e2e` monolith in one step | 3 tickets end-to-end |
| 6 | Experiment 4 → live Linear watch with `maxInflightTasks 2` | manual dispatch, orchestrating-lanes | duplicate pickup | disable watch | 5 tickets picked up unattended, zero duplicates |
| 7 | Risk-based attention policy + typed inbox; nightly Linear↔Kandev drift check | heartbeat | over-automation of Done | policy flag | human interruptions per ticket ↓, escaped defects flat |
| 8 | Evaluation arms (Claude-only / Codex-only / cross) via watch profiles | — | small n | — | board after 10 tickets per arm |

---

## 25. Integration seams (concrete answers)

| Question | Answer | Evidence |
|---|---|---|
| Fleet consume Kandev state instead of `claude agents --json`? | Yes: WS `task.list`, `task.get`, `session.subscribe`; gateway-forwarded notifications `session.state_changed`, `session.pending_action_changed`, `session.message.added/updated`, `task.status_summary.updated`; authoritative pending questions via `list_pending_questions_kandev` / `GET /api/v1/clarification`; answer via `answer_question_kandev` / `POST /api/v1/clarification/:id/respond`. `session.clarification_requested` is a notification-provider event type, not a gateway subscription — do not build on it | `gateway/websocket/task_notifications.go:80-95`; `clarification/handlers.go:200`; `automation-and-mcp.md:760+` |
| API/event stream usable by a TUI? | Yes, but unversioned, unauthenticated, lossy under backpressure → refetch on reconnect | `websocket-api.md` §Security, §Transport |
| Attention-first view preserved? | Yes; bucket from session state + clarification + workflow step | §16 |
| `new-agent` → thin Kandev create? | Yes: `POST /api/v1/tasks` or `create_task_kandev` with `external_id`, `start_agent` | `automation-and-mcp.md:473-494, 844` |
| Could `new-agent` disappear? | For tickets, yes (watch). For ad-hoc prompts keep a one-liner | §4 usage |
| `pair` attach to a Kandev-launched agent? | Passthrough sessions: yes (PTY). ACP sessions: no terminal attach; use message/UI | `feature-status.md:96` |
| BLOCKED / needs-human exposed cleanly? | Yes: task states `BLOCKED`/`WAITING_FOR_INPUT`, session `WAITING_FOR_INPUT`, plus a clarification request object with options. Classify on the pending record, not on the state alone (an idle session can also be "waiting") | `task/models/models.go:9-18`; `clarification/types.go` |
| Plan review events? | Plan saved via MCP → `task.plan.created/updated`; gate is a wait step | `actions.go` `task.plan.*`; `workflow-tips.md` |
| Runtime completion vs workflow completion distinguished? | Yes: session terminal ≠ step Done; `AutoAdvanceRequiresSignal` | `workflow/models/models.go:239-244` |
| Lanes as Kandev executors? | Yes: register each lane repo; Worktree executor + setup script; or Local executor for the singleton lane | `executors.md`; `worktree/manager_cleanup.go:385` |
| Kandev target an already-warm environment? | Local executor uses the selected checkout directly; Worktree creates a fresh worktree but the lane's DB server, Redis, caches are shared by design | `executors.md` |
| HAR slots replace lanes? | No: fresh worktree + cloned DB per launch, no singleton | `concepts.md`; `agent-ops.ts:163` |
| HAR represent physical singletons? | No concept | grep |
| HAR verification from `/e2e`/`/ship`? | Possible via `har env verify --full --json`, but requires `.har/` for a Rails app HAR does not profile | `guides/stages.md` |
| HAR evidence as completion prerequisite? | The rule is portable without HAR (§12) | `validations.ts` |
| Kandev orchestrate HAR? | Only as a shell stage; no native integration | — |
| One task id across Kandev, Claude, Codex, HAR, GitHub, Linear in Honeycomb? | Via `OTEL_RESOURCE_ATTRIBUTES` in executor env (Claude yes; Codex UNVERIFIED); PR body and Linear carry the id | §19 |
| Separate Claude/Codex review contexts? | Yes: step with different `AgentProfileID` + `reset_agent_context` | `models.go:17,229` |
| Independent reviewers vs continued reasoning? | Declarative and default in Feature Dev's Review step | `workflow-tips.md` |
| magicnotes DB isolation under Kandev worktrees? | `worktree_offset.rb` needs parent dir `.worktrees` or `WORKTREE_OFFSET`; Kandev paths are `tasks/{taskDir}/{repo}` → adapter: setup script exports `WORKTREE_OFFSET=<unique per task>` before `bin/create_worktree` refresh; `.env` written by `DevEnvironment` then wins | `worktree_offset.rb:14-16, 49-58`; `dev_environment.rb:99-103`; `worktree/config.go:86-102` |

---

## 26. Cross-model check (Sol)

Sol (codex, effort high, thread `01a06e03-3ef7-7372-b464-80d14653a2d4`) was given the same evidence and questions **without** this report's conclusions. Its first line: *"RECOMMENDED OPTION: D — Pilot Kandev's control plane, retain repo-owned provisioning, and add a small acceptance layer informed by HAR's evidence model."* Each substantive point below is labelled by agreement after re-reading Sol's cited lines.

**[both]**
- Option D; never run two environment managers (Kandev worktrees + HAR slots).
- Keep `/e2e`'s adversarial cross-model review and `/verify`'s semantic verification as *our* policy; Kandev supplies primitives only.
- Retire tmux screen-scraping, `fleet-status` as acceptance authority, and the LLM heartbeat scheduler.
- The Kandev Worktree executor needs an explicit `WORKTREE_OFFSET`; directory conventions alone will not work (`worktree/config.go:86-102`, `worktree_offset.rb:13-16`).
- One fixed plan gate per stream is a workflow artefact; gates should be risk-triggered decisions with a durable decision id.
- Keep an ad-hoc task path: most sessions were investigations, not ticket pipelines.

**[sol-only, verified and adopted]**
- **Task dependencies gate automated launch for regular Kanban tasks, wired unconditionally** — the feature-status page understates this (`orchestrator/event_handlers_dependencies.go:29-40`, `backendapp/orchestrator.go:172-175`: "dependencies are a core Kanban relationship, not an Office feature"; fails closed on read error). Capability matrix and §14 updated.
- **`run_code_review`'s failure does not block the step transition** (`workflow/models/models.go:39-45`). Acceptance must therefore be enforced by our step-completion signal, not by Kandev's review action. §17 updated.
- **Do not build Fleet against `session.clarification_requested`**: it is a notification-provider event type (`notifications/service/service.go:24`), not a gateway subscription; the WebSocket gateway forwards `session.pending_action_changed`, `session.message.added/updated`, `task.status_summary.updated` (`gateway/websocket/task_notifications.go:80-95`). Poll `list_pending_questions_kandev` / `GET /api/v1/clarification` for the authoritative list; use notifications as refresh hints. §25 updated.
- External answer path exists: `list_pending_questions_kandev`, `answer_question_kandev`, `POST /api/v1/clarification/:id/respond`, plus `list_pending_agent_permissions_kandev` / `resolve_agent_permission_kandev` (`automation-and-mcp.md:760+`, `clarification/handlers.go:200`). This is what a thin Fleet client calls instead of tmux `send-keys`.
- `bin/create_worktree` refresh mode derives identity from the checkout basename (`create_worktree` `copy_configs`, `refresh_current_worktree`), and Kandev repeats the repo basename across task directories — so the adapter must export a per-task offset *before* calling it, and `DevEnvironment.next_available_slot` scans one root without a lock (`dev_environment.rb:121`). For the pilot, reserve one known-free slot; before concurrency, add a host-wide lease.
- `/e2e` Stage 2 detects an existing worktree only via `CLAUDE_JOB_DIR` (`e2e/SKILL.md:73`); under Kandev that variable is absent, so it would provision a nested worktree. Replace with real checkout-ownership detection (`git rev-parse --git-common-dir` differs from `.git`) before Experiment 1.
- Release the model process while a human decision is pending and keep task + checkout + evidence + pending decision durable. This is the correct fix for the 60-minute retirement problem (F2), not pinning.
- Better Experiment 1: run `/e2e --dry-run` (stops before ship), require the *installed* skill and Codex audit to actually execute with identifiable artefacts, the plan question to appear through the pending-question API, and — after a controlled runtime stop — one API answer to resume the task exactly once. §23 updated.

**[sol-only, plausible, not verified here]**
- HAR runs verification *before* hashing the tree (`run-service.ts:374+`), so a concurrent writer can change the tree between test and record, and hashing failures are swallowed. Validation records carry no environment/DB fingerprint. Both strengthen §12's "borrow the idea, add environment identity and before/after hash equality" rather than adopt HAR.
- Upstream `claude-agent-acp` loads user/project settings and publishes available commands; the Agent SDK supports plugins and namespaced skills (Sol cited the upstream repo and SDK docs). If true, Experiment 1 is likely to pass. Still the pass/fail criterion.
- Asking a question moves the task to `REVIEW` as well as the session to `WAITING_FOR_INPUT` (`mcp/handlers/handlers.go:~3900`); the handler region seen sets task state around clarification, exact transition not confirmed.
- Ship's URL discovery reads `.env.local`/3000 and can miss the provisioner's `.env` (`ship.md:113`). Worth a check in Phase 1.

**[fable-only]** (in this report, not raised by Sol): the Linear `ready-for-agent` label already in use organisation-wide; the "two of three BLOCKED rows are ticket bookkeeping" observation and the resulting policy that `/ship` moves In Review and merge automation moves Done; the Honeycomb `work.id` tagging via executor env; the evaluation-arm design.

**Disagreements:** none unresolved. Sol frames B as "leaves acceptance enforcement unspecified", which is why both land on D; Sol adds "a small deterministic acceptance service" as a named component where this report puts the same logic inside `/verify` + `/ship` + the step-completion signal. Either shape works; start inside the skills (no new surface) and extract only if a second consumer appears.

---

## 27. Open questions / uncertainties

1. **Claude Code plugin skills under ACP** — decisive; Experiment 1.
2. **Kandev churn** — 100+ commits/month, unversioned WS protocol, Office in flux. Pin a release; wrap all API use in one small client module.
3. **Task/session status constant names** — verified (`task/models/models.go:9-18`, `:1527`).
4. **Automatic Linear write-back** — `SetIssueState` exists; no automation caller found. Assume ours to do from the skill.
5. **Codex OTel resource attributes per task** — UNVERIFIED.
6. **Personal Honeycomb telemetry** — not reachable from this session's MCP (bound to the `beam` team); assumed live per the doc.
7. **Kandev worktree + `bin/setup` cost** — `create_worktree` runs `bin/setup` (Ruby, Node, DB) per worktree; the warm-lane advantage partly depends on shared caches that Kandev's `tasks/` location may not share. Measure in Experiment 1.
8. **AGPL-3.0** — irrelevant for internal use, relevant if Kandev were ever redistributed with modifications.
9. **Whether Kandev's Threads/Inbox makes a TUI unnecessary** — decide after Experiment 3, not before.
