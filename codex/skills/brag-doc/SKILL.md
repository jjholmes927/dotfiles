---
name: brag-doc
description: Generate weekly brag doc entries from GitHub activity. Use when the user asks to create a brag doc, write a weekly update, summarize weekly contributions, review GitHub activity, draft accomplishments, promote highlights, or explicitly says use brag-doc.
---

# Brag Doc

Generate weekly brag doc entries from GitHub activity.

## Parameters

Parse from user input:
- `person`: default `joel`
- `week`: week commencing date like `2025-01-06`
- `repos`: comma-separated repo list, default `magicnotes`
- `org`: GitHub org, default `wearebeam`

## Paths

```bash
BRAG_ROOT=~/Documents/repos/second-brain/05-reflections/brag
PEOPLE_DIR=~/Documents/repos/second-brain/02-people
```

## Workflow

1. Validate that both directories exist.
2. Resolve the person file in `PEOPLE_DIR` and read the GitHub username from frontmatter.
3. Calculate the Monday-to-Sunday week range.
4. Check whether the brag doc file already exists and ask before overwriting.
5. Pull GitHub data with `gh`:
   - merged PRs in the date range
   - reviews given in the date range
6. Write the weekly entry to `$BRAG_ROOT/{person}/{week}.md`.
7. Suggest 1-3 highlight candidates and ask whether to promote them to `highlights.md`.

## Output format

Write a markdown file with:
- frontmatter for week, person, generated date, and repos
- merged PRs
- reviews given
- week summary
- potential highlights
- notes

If required directories or the GitHub username are missing, stop and report that clearly.
