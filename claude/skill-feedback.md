# Skill feedback log

Real-world PR triages, reviews, and incidents that shaped skills / commands in `~/.claude/`. Add an entry whenever a concrete piece of feedback drives a skill change — so future iteration has the receipts and we don't re-litigate decisions.

Entry format:
- **Date · Skill · Source** — one-line context
- **Triage outcome:** what worked, what didn't (so the lesson is visible without opening links)
- **Skill change:** what was actually edited

---

## `review-pr` — `~/.claude/commands/review-pr.md`

### 2026-05-07 · format + agent calibration · [magicnotes#7211](https://github.com/wearebeam/magicnotes/pull/7211)

**Original review (v1, hard to parse):** https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4381603757

**Format iteration on the same PR:**
- [v1 — bullet cards with checkboxes](https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4398118669)
- [v2 — single details, tables inside](https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4398175361)
- [v3 — details per severity, tables overflowed comment width](https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4398222211)
- [v4 — 3-col tables, file in `<sub>` under finding, fits in width](https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4398246206) ← **locked in**

**Author triage of the v1 review content** (the gold for agent calibration): https://github.com/wearebeam/magicnotes/pull/7211#issuecomment-4381697525

**Triage outcome (17 findings):**
- 2 directly fixed: Critical A (`worker.onerror` after `ready`), Important E (fire-and-forget `aicState` PATCH). Both were concrete observable failures.
- 3 false positives — drove the per-agent `Before flagging, sanity-check` blocks:
  - **Race claim was wrong** — agent saw two state setters and inferred a race; in reality `setRefA(...); setStateB(...);` were sequential in the same effect.
  - **Stale-prop claim was wrong** — agent assumed `getAicSessionAuditFields` reads "current" props; the function fires once at session start, no stale-data problem possible.
  - **"Credentials shipped to browser" was a vendor-distributable SDK key** — flagged as security CRITICAL when it should have been a MINOR confirm-with-vendor.
- 5 real-but-deferred — drove the severity recalibration:
  - "Real but extreme edge case" (mid-session LD flag flip)
  - "Real but defensive" (uncapped output FIFO; would only bite if SDK already broken)
  - "By design per spec" (no mid-recording hot insert — anti-flicker contract)
  - "Stylistic, no convention to violate" (`aic_state_params` flat strong-params)
  - "Real but very low risk" (`update!` no rescue with typed boolean from client)
- 7 Minor — calibration there was fine; mostly accepted as low-priority follow-ups.

**Skill changes:**
- Agent output reshaped to pipe-delimited (`SEVERITY | finding | impact | file:line`) so synthesizer can split into table cells without parsing prose.
- Step 4 layout rewritten to v4 (header counts + per-severity `<details>` + 3-col table + file in `<sub>` under finding).
- Per-agent "Before flagging, sanity-check" blocks added — security (vendor SDK keys), rails (convention claims, service-extraction claims, rescue claims), quality (race / stale / unbounded / dead-code claims), product (vision-anchor / scope-creep claims).
- Unified severity rubric: Important = "real risk under realistic conditions, not 'if X+Y+Z coincide'."
