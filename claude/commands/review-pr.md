# Review PR

Four-agent PR review: security, Rails patterns, code quality, and product domain.
Posts to GitHub when you're the author; shows inline when you're the reviewer.

> **Requires:** Run from inside the target repo's working tree. Context files (`docs/vision-and-ethos.md`, `CLAUDE.md`) are read from the current directory.

## Arguments

`$ARGUMENTS` — optional PR number, or `--fast` to skip.

### Parsing rules
- `--fast` → print "Review skipped (--fast)" and stop immediately
- A number (e.g. `142`) → review PR #142
- Empty → detect PR from current branch

## Step 0: Parse arguments

If `$ARGUMENTS` is `--fast`:
```
Review skipped (--fast)
```
Stop here.

If `$ARGUMENTS` is a number, use that as the PR number.
Otherwise detect from current branch:
```bash
gh pr view --json number -q '.number' 2>/dev/null
```
If that returns empty, tell the user no PR was found and stop.

## Step 1: Preflight checks

Run these in parallel:

```bash
# Verify gh is authenticated
gh auth status 2>&1

# Detect PR author
gh pr view <PR_NUMBER> --json author -q '.author.login' 2>/dev/null

# Detect current user
gh api user -q '.login' 2>/dev/null
```

**Failure modes — stop with a clear message if:**
- `gh auth status` fails → "Run `gh auth login` first"
- PR author fetch fails → "Could not find PR <number>"

Compare author to current user:
- Match → **author mode**: post to GitHub + show inline
- No match → **reviewer mode**: show inline only

## Step 2: Fetch diff and context

Run in parallel:

```bash
# Fetch the diff (once — reuse for all agents)
gh pr diff <PR_NUMBER>
```

```bash
# Check which context files exist
ls docs/vision-and-ethos.md 2>/dev/null && echo "vision: found" || echo "vision: missing"
ls docs/product-knowledge.md 2>/dev/null && echo "knowledge: found" || echo "knowledge: missing"
```

If `docs/vision-and-ethos.md` is missing → skip Agent 4 (product domain) and note in the review footer:
`⚠️ product-domain skipped — docs/vision-and-ethos.md not found`

If diff is empty → stop with:
"No diff found — nothing to review."

Read the following files:
- `docs/vision-and-ethos.md` (required)
- `docs/product-knowledge.md` (if it exists — skip silently if not)
- Extract the `## Architecture` and `## Conventions` sections from `CLAUDE.md` by finding those level-2 headings (lines starting with exactly `## `) and reading until the next level-2 heading (not `###` subheadings)

## Step 3: Run four agents in parallel

Launch all four using the Agent tool simultaneously. Pass the full diff text in each
prompt. Individual agent failures are non-fatal — proceed with whatever returns.

### Agent 1: Security & Data Safety

Prompt:
```
You are a security-focused code reviewer for a Ruby on Rails application.

Review the following git diff for security issues. Focus only on security and data safety.

Look for:
- Mass assignment — params not filtered through `permit`
- Encrypted attribute mishandling — tokens, keys, PII stored or logged in plaintext
- Auth gaps — actions missing `require_login`, `User.find(params[:id])` instead of
  scoping to `current_user`
- Credential exposure — API keys or secrets in code or logs
- SQL injection via raw string interpolation
- Unsafe or open redirects
- Brakeman-class issues

Output format — list findings as:
CRITICAL: <description> [file:line if identifiable]
IMPORTANT: <description> [file:line if identifiable]
MINOR: <description> [file:line if identifiable]
NONE: No security findings.

Only output findings at these severity levels. Be concise. One line per finding.
Maximum 10 findings total. Prioritise the most significant.

<diff>
[INSERT FULL DIFF HERE]
</diff>
```

### Agent 2: Rails Domain Patterns

Prompt:
```
You are a Rails-specialist code reviewer. Review the following git diff for
Rails-specific antipatterns and convention violations.

Project conventions for context:
[INSERT ## Architecture SECTION FROM CLAUDE.md]
[INSERT ## Conventions SECTION FROM CLAUDE.md]

Look for:
- N+1 queries — associations loaded in loops without includes/preload
- Synchronous work in controllers that belongs in a background job
- Job safety — not idempotent, not retry-safe, incorrect use of perform_later
- Service object shape violations (see conventions above)
- ActiveRecord misuse — update_attribute bypassing validations, save! swallowed in
  rescue, callbacks doing too much
- Missing database indexes on new foreign keys or frequently-queried columns
- find_or_create_by vs create! race condition risks

Output format:
CRITICAL: <description> [file:line if identifiable]
IMPORTANT: <description> [file:line if identifiable]
MINOR: <description> [file:line if identifiable]
NONE: No Rails pattern findings.

Only output findings at these severity levels. Be concise. One line per finding.
Maximum 10 findings total. Prioritise the most significant.

<diff>
[INSERT FULL DIFF HERE]
</diff>
```

### Agent 3: Code Quality

Prompt:
```
You are a code quality reviewer. Review the following git diff for correctness,
edge cases, and test coverage. No domain knowledge assumed.

Look for:
- Logic errors — off-by-one, wrong boolean, inverted condition
- Unhandled edge cases — nil inputs, empty arrays, concurrent writes
- New code paths without corresponding tests
- Tests that pass vacuously — not verifying real behaviour
- Dead code — unreachable branches, unused variables
- Methods doing too many things
- Naming that obscures intent

Output format:
CRITICAL: <description> [file:line if identifiable]
IMPORTANT: <description> [file:line if identifiable]
MINOR: <description> [file:line if identifiable]
NONE: No code quality findings.

Only output findings at these severity levels. Be concise. One line per finding.
Maximum 10 findings total. Prioritise the most significant.

<diff>
[INSERT FULL DIFF HERE]
</diff>
```

### Agent 4: Product Domain

Prompt:
```
You are a product domain reviewer. Review the following git diff through a product
and user lens. Even backend-only changes can have user-visible consequences.

Product context:
[INSERT FULL CONTENT OF docs/vision-and-ethos.md]

[IF docs/product-knowledge.md EXISTS, INSERT:]
Domain knowledge:
[INSERT FULL CONTENT OF docs/product-knowledge.md]

Look for:
- Changes that affect what users see or experience, even indirectly
  (e.g. sync frequency → data freshness → user confidence in recommendations)
- Behaviour that contradicts the vision doc — noise over signal, late alerts,
  reduced trust, commercialisation over curation
- Anything in the domain knowledge this change touches or potentially invalidates
- Scope creep — the change does more than the PR description says
- User-facing consequences not mentioned in the PR description

Output format:
CRITICAL: <description>
IMPORTANT: <description>
MINOR: <description>
NONE: No product domain findings.

Only output findings at these severity levels. Be concise. One line per finding.
Maximum 10 findings total. Prioritise the most significant.

<diff>
[INSERT FULL DIFF HERE]
</diff>
```

## Step 4: Synthesise findings

After all four agents return, combine their outputs:

1. Collect all lines starting with CRITICAL:, IMPORTANT:, MINOR: from all agents
2. Deduplicate by topic — if two agents flag the same issue in different words, keep the
   more descriptive one. Prefer false-positive duplicates over missed real findings.
3. Group by severity. Prefix each finding with the agent tag in brackets:
   `[security]`, `[rails]`, `[quality]`, `[product]`
4. Format the final comment (omit sections with no findings):

```markdown
## AI Code Review

### 🔴 Critical
- [tag] description

### 🟡 Important
- [tag] description

### 🟢 Minor
- [tag] description

---
*security · rails-patterns · code-quality · product-domain*
```

If all four agents returned NONE → output:
```markdown
## AI Code Review

✅ No significant issues found.

---
*security · rails-patterns · code-quality · product-domain*
```

Note any agents that failed or timed out in the footer:
`⚠️ rails-patterns timed out — skipped`

## Step 5: Route output

**Always:** Display the formatted comment inline in the session.

**If author mode:** Post to GitHub:
```bash
gh pr comment <PR_NUMBER> --body "$(cat <<'REVIEW'
[INSERT FORMATTED COMMENT]
REVIEW
)"
```

## Step 6: Signal status for /ship integration

After displaying output, print one of these lines as the final line of output so that
`/ship` can parse the result when it invokes this command:

```
REVIEW_STATUS: CRITICAL
REVIEW_STATUS: OK
REVIEW_STATUS: CLEAN
```

- `CRITICAL` — one or more Critical findings exist
- `OK` — Important or lower findings only
- `CLEAN` — no findings at all

Precedence: any Critical finding → CRITICAL; else any Important or Minor → OK; else CLEAN.

`/ship` reads this line to decide whether to prompt the user (see ship.md Step 8).
