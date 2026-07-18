# Cross-model AI coding workflows — research report (2026-07-18)

**Question:** Cross-model AI coding workflows in 2025-2026 where one frontier model does planning/review and another does implementation (e.g. Claude Code orchestrating OpenAI Codex CLI headlessly, or vice versa): who is doing this, what tools/harnesses exist (open-source orchestrators, plugin skills, multi-agent pipelines), what patterns work (plan gates, per-task reasoning-effort grading, self-review vs cross-review, fix-loop caps), and what concrete ideas would be worth adopting into a personal pipeline that uses Claude for planning/arbitration and codex exec for implementation with checkpoint-commit reviews.

## Summary

Cross-model AI coding workflows where one frontier model plans/reviews and another implements are a real, active 2025-2026 open-source pattern, with at least seven working orchestrators found — including an official OpenAI-shipped Claude Code plugin (codex-plugin-cc). The dominant architecture is: a frontier model plans and arbitrates, cheaper/other-family models implement, and an independent fresh-context reviewer from a different model family gates the work — cross-review consistently beats self-critique (fresh-context verifiers caught ~73% of seeded bugs vs 7-33% for self-critique). Every mature pipeline hardcodes the same three primitives you're targeting: an explicit plan gate before implementation, a bounded fix-loop cap (commonly 3, 10, or 15 iterations with human escalation on cap-hit), and a cross-family review gate at checkpoints. Google/MIT/DeepMind research grounds the design: an orchestrator-as-reviewer contains error amplification to 4.4x vs 17.2x for unchecked multi-agent pipelines, but multi-agent splitting HURTS sequential/non-decomposable tasks by 39-70% — so keep implementation single-threaded and reserve the second model for review/arbitration, not parallel task-splitting. For your Claude-plans / codex-exec-implements pipeline, the highest-value adoptions are per-invocation reasoning-effort grading, a READY/REVISE plan gate with a fresh-context verifier, cross-family review at each checkpoint-commit with a hard iteration cap, and a verification-outcome taxonomy on findings.

## Findings

### 1. [high] A cluster of working open-source cross-model orchestrators exists (2025-2026), spanning every role permutation: Claude-orchestrates-Codex, Gemini-orchestrates-Claude+Codex, Codex-as-MCP-server, and tiered Claude-only dispatch. This is a mature, actively-maintained pattern, not vaporware.

pilotfish (MIT, 481 stars, v1.2.1 Jul 2026) does tiered Claude dispatch (Fable 5/Opus plan, Sonnet/Haiku execute). claude-codex (Z-M-Huang) and ching-kuo/claude-codex both orchestrate Codex from Claude. claude-codex-gemini puts Gemini as orchestrator, Claude as coder, Codex as reviewer. All reference current 2026 model IDs (gpt-5.3/5.6-codex, Opus 4.8), are actively pushed, and describe the plan-implement-review shape.

Sources: https://github.com/Nanako0129/pilotfish · https://github.com/Z-M-Huang/claude-codex · https://github.com/openai/codex-plugin-cc · https://github.com/johnpsasser/codex-pr-review · https://github.com/shimo4228/codex-review · https://github.com/ching-kuo/claude-codex · https://github.com/Z-M-Huang/claude-codex-gemini

### 2. [high] OpenAI officially ships codex-plugin-cc — a Claude Code plugin (hosted under the openai/ GitHub org, Apache-2.0, ~29k stars) that lets Claude Code invoke Codex CLI for reviews and delegate implementation/investigation tasks, reusing your existing local Codex auth. This directly validates the 'Claude orchestrates Codex exec headlessly' pattern as first-party supported.

Repo description: 'Use Codex from Claude Code to review code or delegate tasks.' README: 'this plugin uses your local Codex CLI and uses the same local authentication state.' Slash commands: /codex:review, /codex:adversarial-review, /codex:rescue, /codex:transfer. Corroborated by DeepWiki, Medium, ClaudeKit. Caveat: 'official' rests on the openai/ org namespace, not a staff press announcement.

Sources: https://github.com/openai/codex-plugin-cc

### 3. [high] Codex delegation is fully headless/async-capable: /codex:rescue routes a task through a codex-rescue subagent with per-invocation --model and --effort flags (defaulting when omitted), plus --background/--wait and job-management commands (/codex:status, /codex:result, /codex:cancel). This is the exact 'codex exec headlessly with per-task reasoning-effort grading' primitive you want.

README: '/codex:rescue --model gpt-5.4-mini --effort medium investigate the flaky test'; 'If you do not pass --model or --effort, Codex chooses its own defaults.' Background job commands documented verbatim. Verified against raw README, not just rendered page.

Sources: https://github.com/openai/codex-plugin-cc

### 4. [high] Cross-review (independent, fresh-context, different-model-family reviewer) is the near-universal design choice, explicitly preferred over self-critique. The stated rationale — a second model is a 'decorrelation seam' that catches blind spots a same-model author-reviewer pair shares — recurs across independent projects.

pilotfish: 'independent fresh-context verifier subagents outperform self-critique' (labeled official Anthropic guidance; Lance Martin experiments cite fresh-context verifiers catching ~73% of seeded issues vs 7-33% self-critique). shimo4228/codex-review: 'a decorrelation seam, not a throughput tool ... same-model agents scale throughput, a different model scales judgment decorrelation.' codex-plugin-cc's review gate runs Codex against Claude's output via a Stop hook that can block flagged responses.

Sources: https://github.com/Nanako0129/pilotfish · https://github.com/shimo4228/codex-review · https://github.com/johnpsasser/codex-pr-review · https://github.com/Z-M-Huang/claude-codex · https://github.com/openai/codex-plugin-cc

### 5. [high] An explicit plan gate before implementation is a standard primitive: a read-only reviewer challenges the plan and returns a binary verdict (READY/REVISE, approved/needs_changes, or Codex plan-audit for correctness/security/completeness) before any code is written. Post-execution, a fresh-context verifier attempts to REFUTE the completed work (CONFIRMED/REFUTED) rather than rubber-stamp it.

pilotfish: plan-verifier gives read-only challenge returning READY/REVISE; post-exec verifier 'tries to refute completed work ... and never fixes' returning CONFIRMED/REFUTED. ching-kuo/claude-codex: 'Codex audits the plan → flags issues (max 3 rounds)' for correctness/security/completeness. claude-codex-gemini enforces fixed sequence Requirements→Planning→Plan Review→Implementation→Code Review with reviewer approval required to advance.

Sources: https://github.com/Nanako0129/pilotfish · https://github.com/ching-kuo/claude-codex · https://github.com/Z-M-Huang/claude-codex-gemini · https://github.com/Z-M-Huang/claude-codex

### 6. [high] Reviews are ordered/escalating and structurally enforced. Mature pipelines cascade through escalating reviewers (Sonnet → Opus → Codex) for BOTH plan and code stages, with Codex as the terminal gate, and enforce ordering via explicit task dependencies (blockedBy) so a phase cannot start until the prior review passes.

claude-codex: 'SEQUENTIAL REVIEWS (enforced via blockedBy): Implement → Sonnet (blocked until impl) → Opus (blocked until Sonnet) → Codex (blocked until Opus)', Codex marked '<- GATE'. claude-codex-gemini: 'Sonnet → Opus → Codex for both plan and code stages ... sequentially (NOT parallel) for quality gates.'

Sources: https://github.com/Z-M-Huang/claude-codex · https://github.com/Z-M-Huang/claude-codex-gemini

### 7. [high] Fix-loops are always hard-capped to bound token cost, and hitting the cap escalates to a human as a signal of conflicting requirements. Observed caps: 3 rounds (ching-kuo/claude-codex plan-audit and code-fix loops), 10 for plan-review / 15 for code-review + 3 auto-resolve attempts (Z-M-Huang/claude-codex), and 10 per-reviewer with human escalation on cap-hit (claude-codex-gemini).

Z-M-Huang/claude-codex README 'hardcoded defaults': plan review limit 10, code review limit 15, auto-resolve attempts 3. ching-kuo: 'Claude fixes CRITICAL/HIGH issues → re-reviews (max 3 rounds)' to 'keep token usage predictable.' claude-codex-gemini: 'Max iterations: 10 per reviewer. If a reviewer hits 10 iterations, Gemini escalates to user (likely conflicting requirements).'

Sources: https://github.com/Z-M-Huang/claude-codex · https://github.com/ching-kuo/claude-codex · https://github.com/Z-M-Huang/claude-codex-gemini

### 8. [high] The strongest cross-review pattern is bidirectional grounded verification with a findings taxonomy: run both families in parallel against identical prompts, have each family's grounded verifier check the OTHER family's findings against source before posting, and label each surviving finding by cross-model agreement level ([both], [codex-only]/[claude-only], [unconfirmed-by-X], [deterministic]). Refuted findings are dropped; unconfirmed ones are priority-demoted and confidence-discounted (×0.7).

README: 'Codex (gpt-5.6-sol) and Claude Opus run in parallel ... every LLM finding independently verified against source by the other family before being posted.' Six-label taxonomy confirmed verbatim; [unconfirmed] findings 'Priority demoted by 1; confidence_score *= 0.7'; [deterministic] from lint/typecheck/test 'skips verification because tools don't hallucinate.'

Sources: https://github.com/johnpsasser/codex-pr-review

### 9. [high] Research grounds the orchestrator-as-reviewer/validation-gate pattern quantitatively: a centralized orchestrator that cross-checks subagent outputs contains error amplification to 4.4x versus 17.2x for independent multi-agent systems with unchecked propagation.

'Towards a Science of Scaling Agent Systems' (Kim et al., Google Research/MIT/DeepMind, Dec 2025), Table 5: Single-agent 1.0x, Centralized 4.4x, Hybrid 5.1x, Decentralized 7.8x, Independent 17.2x. Mechanism: 'sub-agent outputs pass through an orchestrator that cross-checks reasoning steps before aggregation.' Caveat: non-peer-reviewed v1 preprint.

Sources: https://arxiv.org/html/2512.08296v1

### 10. [high] Multi-agent task-splitting only helps decomposable/parallelizable work; for sequential reasoning it degrades performance 39-70%. Implication for a personal pipeline: keep implementation single-threaded (one implementer per task) and use the second model for review/arbitration, NOT for parallel decomposition of a sequential coding task.

Same paper: centralized coordination +80.9% on parallelizable financial reasoning, but 'for sequential reasoning tasks, every multi-agent variant tested degraded performance by 39-70%' (PlanCraft: Centralized -50.4%, Independent -70.0%). Caveat: the 39-70% range leans heavily on one benchmark (PlanCraft); non-peer-reviewed preprint.

Sources: https://arxiv.org/html/2512.08296v1

### 11. [high] Read-only-by-construction is an enforceable safety pattern for the reviewer seam: the wrapper invokes 'codex review' (never 'codex exec -p yolo'), forwards only allowlisted flags, and rejects unauthorized flags with exit 64 — enforcement lives in the wrapper script, not assumed of the Codex CLI. Useful for a review gate you want provably unable to mutate the working tree.

Verified against actual wrapper source (codex-review.sh): 'exec env NO_COLOR=1 codex review'; strict allowlist case for --uncommitted/--base/--commit/-m/--prompt; catch-all '-*' branch exits 64; header: 'The read-only invariant is enforced here by an explicit flag allowlist, so it does not depend on the external Codex CLI never adding write-enabling flags.'

Sources: https://github.com/shimo4228/codex-review

### 12. [high] Tiered dispatch (frontier model for judgment, cheaper same-family model for volume execution) is a validated cost lever distinct from cross-family review: quality is protected by fresh-context verification, not by using the biggest model everywhere.

pilotfish: 'the frontier model (Fable 5/Opus) plans, decides, and spec reviews ... while cheaper models (Opus/Sonnet/Haiku) execute the volume work through global subagents. Quality is protected by fresh-context verification, not by using the biggest model everywhere.' Cites Anthropic benchmark: Fable 5 orchestrator + Sonnet workers at 96% of all-Fable performance for 46% of cost.

Sources: https://github.com/Nanako0129/pilotfish

### 13. [high] Concrete adoption recommendations for a Claude-plans / codex-exec-implements pipeline with checkpoint-commit reviews.

Synthesized from confirmed patterns above: (1) Adopt codex-plugin-cc directly — reuses local Codex auth, gives /codex:rescue with per-task --effort grading and --background for headless exec. (2) Add a READY/REVISE plan gate with a fresh-context plan-verifier before any codex exec runs. (3) At each checkpoint-commit, run a cross-family review (Codex reviews Claude's/its own diff, or Claude arbitrates Codex's implementation) with a hard iteration cap (start with 3, escalate to human on cap-hit). (4) Grade reasoning-effort per task rather than globally — low for mechanical edits, high for judgment-heavy changes. (5) Make the reviewer read-only-by-construction via a flag allowlist. (6) Label findings by cross-model agreement and drop refuted ones. (7) Keep implementation single-threaded per task — don't parallel-split sequential coding.

Sources: https://github.com/openai/codex-plugin-cc · https://github.com/johnpsasser/codex-pr-review · https://github.com/Nanako0129/pilotfish · https://github.com/Z-M-Huang/claude-codex · https://arxiv.org/html/2512.08296v1

## Refuted claims

- (0-3) Smart routing decides the implementer by change size: small changes (<=2 files, <=30 lines) are implemented by Claude directly, while large changes are delegated to Codex, explicitly to reduce cost. — https://github.com/ching-kuo/claude-codex

## Caveats

Source quality is strong-but-narrow. The two quantitative research claims (4.4x vs 17.2x error amplification; 39-70% sequential degradation) come from a single non-peer-reviewed arXiv v1 preprint (2512.08296), and the 39-70% range leans heavily on one benchmark (PlanCraft) — treat the exact numbers as directional, not settled. Every orchestrator claim is sourced from the project's own README/source, which is authoritative for describing what a tool DOES but says nothing about real-world efficacy, adoption, or whether these designs actually outperform a simpler single-model loop in practice; star counts are modest (18-481) for most, and several are explicitly hobbyist/experimental (claude-codex-gemini is GPL, personal). 'Official' for codex-plugin-cc rests on the openai/ GitHub org namespace, not a formal OpenAI staff announcement. The field is fast-moving: repos are migrating (Z-M-Huang/claude-codex has moved to a vcp/dev-buddy plugin), and model IDs (gpt-5.3/5.6, Opus 4.8) will date quickly. The specific iteration caps (3/10/15) are the projects' arbitrary defaults, not empirically-tuned optima. One claim was refuted in verification: claude-codex does NOT route by change-size (small→Claude, large→Codex) to save cost — do not assume size-based routing exists.

## Open questions

- Do these cross-model pipelines actually outperform a well-configured single-model loop on real coding tasks, or is the overhead (extra review round-trips, token cost, latency) net-negative? None of the sources provide head-to-head efficacy benchmarks for their own designs.
- What are empirically-optimal fix-loop caps and reasoning-effort thresholds? Observed caps (3/10/15) are arbitrary defaults — is there data on where diminishing returns actually set in per iteration?
- How should model roles be assigned when both frontier families are near-parity — is Claude-plans/Codex-implements meaningfully better or worse than the reverse, and does it depend on task type (greenfield vs debugging vs refactor)?
- How do these pipelines handle state/context handoff between the planning model and the implementing model at checkpoint-commit boundaries — what exactly gets passed (full plan, diff, test results), and how is context-window blowup managed across many fix-loop iterations?

---
Stats: {"angles": 6, "sourcesFetched": 23, "claimsExtracted": 115, "claimsVerified": 25, "confirmed": 24, "killed": 1, "unverified": 0, "afterSynthesis": 13, "urlDupes": 8, "budgetDropped": 5, "agentCalls": 106}
