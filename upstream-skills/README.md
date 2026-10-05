# Upstream skills

> **TL;DR** Third-party skills I use in every harness, linked straight from their upstream repos. Nothing here calls them; they're just available.

**Add one:** append `owner/repo path/to/skill-dir` to [`skills.txt`](skills.txt), then run `./upstream-skills/install.sh`.

**Update:** re-run the script. It fast-forwards each upstream checkout, so links always point at upstream `main`.

| Detail | Value |
|---|---|
| **Checkouts** | `~/.local/share/upstream-skills/<owner>__<repo>` |
| **Linked into** | `skills/` under `~/.claude`, `~/.codex`, `~/.cursor`, `~/.config/opencode` (only harnesses that exist) |
| **Existing entries** | A same-name skill that isn't this link is left alone, with a warning |
| **Run by** | Every harness installer (`claude`, `codex`, `cursor`, `opencode`), or directly |

## Current skills

| Skill | Upstream | Licence |
|---|---|---|
| `grill-me` | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me), trigger only: `/grill-me` loads `grilling` | MIT |
| `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling), the interview itself ([guide](https://www.aihero.dev/skills-grill-me)) | MIT |
