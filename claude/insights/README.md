# Claude Code Insights Archive

Longitudinal archive of `/insights` reports across machines for tracking usage patterns over time.

## Structure

```
insights/
  work-laptop/
    YYYY-MM-DD-report.html     # Visual report (open in browser)
    YYYY-MM-DD-facets/         # Per-session analysis JSON
    YYYY-MM-DD-session-meta/   # Session metadata JSON
  personal-laptop/
    ...
```

## Generating a new snapshot

```bash
# Run /insights in Claude Code, then:
DATE=$(date +%Y-%m-%d)
MACHINE=work-laptop  # or personal-laptop
DIR=~/Documents/repos/dotfiles/claude/insights/$MACHINE

cp ~/.claude/usage-data/report.html "$DIR/$DATE-report.html"
cp -r ~/.claude/usage-data/facets "$DIR/$DATE-facets"
cp -r ~/.claude/usage-data/session-meta "$DIR/$DATE-session-meta"
```
