# Upstream skills

> **TL;DR** Third-party skills I use in every harness, linked straight from their upstream repos. Nothing here calls them; they're just available.

**Add one:** append `owner/repo path/to/skill-dir` to [`skills.txt`](skills.txt), then run `./upstream-skills/install.sh`. Add a tag or commit as a third column to pin it.

**Update:** re-run the script. Unpinned repos fast-forward to upstream `main`. Pinned repos stay on their ref until you change it in `skills.txt`. Read the upstream diff before bumping a pin, because a prompt change quietly changes how the skill behaves.

| Detail | Value |
|---|---|
| **Checkouts** | `~/.local/share/upstream-skills/<owner>__<repo>` |
| **Linked into** | `skills/` under `~/.claude`, `~/.codex`, `~/.cursor`, `~/.config/opencode` (only harnesses that exist) |
| **Existing entries** | A same-name skill that isn't this link is left alone, with a warning |
| **Pinning** | Optional third column (tag or commit). Every line for a repo must use the same ref |
| **Run by** | Every harness installer (`claude`, `codex`, `cursor`, `opencode`), or directly |

## Current skills

| Skill | Upstream | Licence |
|---|---|---|
| `grill-me` | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me), trigger only: `/grill-me` loads `grilling` | MIT |
| `grilling` | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling), the interview itself ([guide](https://www.aihero.dev/skills-grill-me)) | MIT |
| `ponytail` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail/tree/v5.2.0/skills/ponytail), pinned `v5.2.0`. Write-the-least-code mode, loaded by `/e2e` while building. Skills only, none of its hooks | MIT |
| `ponytail-review` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail/tree/v5.2.0/skills/ponytail-review), pinned `v5.2.0`. Review lens used in `/e2e` branch review | MIT |
