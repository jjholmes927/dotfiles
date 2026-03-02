---
description: "Generate weekly brag doc entries from GitHub activity. Use when asked to create a brag doc, summarize weekly contributions, or review GitHub activity."
allowed-tools: Bash, Read, Write
argument-hint: "[person] [week] [repos] [org]"
---

# Brag Doc Generator

Generate weekly brag doc entries by pulling GitHub activity (merged PRs, reviews given) and summarizing accomplishments.

## Parameters

Parse from user input:
- **person**: Name of person (default: "joel")
- **week**: Week commencing date like "2025-01-06" (default: current week's Monday)
- **repos**: Comma-separated repo list (default: "magicnotes")
- **org**: GitHub org/owner prefix (default: "wearebeam")

## Paths

```
BRAG_ROOT=~/Documents/repos/second-brain/05-reflections/brag
PEOPLE_DIR=~/Documents/repos/second-brain/02-people
```

## Steps

### 0. Validate Paths

Before doing anything, verify that `$BRAG_ROOT` and `$PEOPLE_DIR` exist:
```bash
ls -d "${BRAG_ROOT}" "${PEOPLE_DIR}"
```
If either path does not exist, stop and tell the user:
> "Required directory not found: {path}. Please check that your second-brain repo is cloned at the expected location."

### 1. Resolve Person

Look up the person in `$PEOPLE_DIR/`:
- Read their `.md` file to get `github` username from frontmatter
- If person is "joel" or "myself", use `myself.md`
- Create folder `$BRAG_ROOT/{person}/` if it doesn't exist

If no github username found, ask user to provide it.

### 2. Calculate Week Range

For the given week commencing date (e.g., "2025-01-06"):
- Start: The provided Monday date (YYYY-MM-DD)
- End: Sunday of that week (start + 6 days)

If no week specified, calculate current week's Monday.

File naming: `{week-commencing}.md` (e.g., `2025-01-06.md`)

### 3. Check for Existing Entry

Before generating, check if `$BRAG_ROOT/{person}/{week-commencing}.md` already exists. If it does, ask the user:
> "A brag doc already exists for {person} week of {week-commencing}. Overwrite it, or skip?"

Only proceed if the user confirms overwrite.

### 4. Pull GitHub Data

For each repo in the repos list, run these gh CLI commands:

**Merged PRs by this person:**
```bash
gh pr list --repo "${org}/${repo}" --author "${github_username}" --state merged --search "merged:${start}..${end}" --json number,title,mergedAt,url --limit 50
```

**Reviews given by this person:**
```bash
gh search prs --reviewed-by="${github_username}" --repo="${org}/${repo}" --updated "${start}..${end}" --json number,title,url --limit 50
```

Note: The reviews query finds PRs the person reviewed in the date range. If it returns too many results or times out, summarize what you can get.

### 5. Generate Weekly Entry

Create file at: `$BRAG_ROOT/{person}/{week-commencing}.md`

Use this format:
```markdown
---
week_commencing: {YYYY-MM-DD}
week_ending: {YYYY-MM-DD}
person: {person}
generated: {today}
repos: {repos}
---

# Week of {week-commencing} - {person}

## PRs Merged ({count})

{For each PR:}
- **[#{number}]({url})**: {title}
  - Merged: {date}
  - Summary: {one-line summary of what this accomplished}

## Reviews Given ({count})

{For each review:}
- **[#{pr_number}]({url})**: {pr_title}
  - Review type: {APPROVED/CHANGES_REQUESTED/COMMENTED}
  - Key feedback: {brief summary if available}

## Week Summary

{2-3 sentences summarizing the week's work themes and impact}

## Potential Highlights

{List 1-3 items that might be worth promoting to highlights file}

## Notes

<!-- Add any context, blockers overcome, or learnings -->
```

### 6. Prompt for Highlights

After creating the weekly file, ask:

> "I've created the weekly brag doc. Would you like to promote any of these to the highlights file?"
>
> Potential highlights:
> 1. {item 1}
> 2. {item 2}
> 3. {item 3}
>
> Enter numbers to promote (e.g., "1,3") or "skip" to finish.

If user selects items, append to `$BRAG_ROOT/{person}/highlights.md`:

```markdown
| {week-commencing} | {highlight text} | {category} |
```

### 7. Confirm Completion

Report:
- Weekly file created at: {path}
- PRs found: {count}
- Reviews found: {count}
- Highlights promoted: {count or "none"}

## Error Handling

- **gh CLI not authenticated**: Tell user to run `gh auth login`
- **No activity found**: Create file with empty sections, note "No GitHub activity found for this period"
- **Person not found**: Ask for github username or create new person file
- **API rate limited**: Report what was captured, suggest trying again later

## Examples

```
/brag-doc
→ Generates current week for joel from magicnotes (wearebeam org)

/brag-doc cameron 2025-03-10 magicnotes myorg
→ Generates week of March 10th for Cameron in the myorg GitHub org
```
