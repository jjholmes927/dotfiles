---
description: "Use when the user says 'save permissions', 'save session permissions', or 'add permissions' to scan recent session transcripts for Bash commands and save missing permission patterns to .claude/settings.local.json."
allowed-tools: Bash(python3:*), Bash(git rev-parse:*), Read, Write
argument-hint: "[optional: number of recent sessions to scan, default 5]"
---

Scan recent Claude Code session transcripts for Bash commands used in this project, derive permission patterns, and add any missing ones to `.claude/settings.local.json`.

**Red Flags — STOP:** Never silently add patterns for dangerous commands (`rm`, `sudo`, `chmod`, `git reset`, `git push`, etc.). Flag them to the user instead.

## Steps

### 1. Resolve paths

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# Claude Code uses the absolute path with leading slash replaced by dash (keeps leading dash)
PROJECT_KEY=$(echo "$PROJECT_ROOT" | sed 's|/|-|g')
SESSIONS_DIR="$HOME/.claude/projects/$PROJECT_KEY"
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.local.json"

echo "Project:  $PROJECT_ROOT"
echo "Sessions: $SESSIONS_DIR"
echo "Settings: $SETTINGS_FILE"
```

Stop and report if `$SESSIONS_DIR` does not exist.

If `$SETTINGS_FILE` does not exist, check for `.claude/settings.json`. If neither exists, create `.claude/settings.local.json`:

```bash
mkdir -p "$PROJECT_ROOT/.claude"
echo '{"permissions":{"allow":[]}}' > "$SETTINGS_FILE"
```

### 2. Scan sessions, derive patterns, and write

Parse `$ARGUMENTS` as the number of sessions to scan (default 5). Run this script — it scans, previews, filters dangerous patterns, and writes safe ones in one pass:

```bash
N_SESSIONS=${ARGUMENTS:-5}

python3 - "$SESSIONS_DIR" "$SETTINGS_FILE" "$N_SESSIONS" <<'PYEOF'
import json, sys, re
from pathlib import Path

sessions_dir = Path(sys.argv[1])
settings_file = Path(sys.argv[2])
n_sessions = int(sys.argv[3])

# Dangerous command prefixes — flag to user, never auto-add
DANGEROUS_PREFIXES = {
    'rm', 'sudo', 'chmod', 'chown', 'dd', 'mkfs', 'truncate',
    'git push', 'git reset', 'git rebase', 'git clean',
    'pkill', 'kill', 'killall', 'shutdown', 'reboot',
    'DROP', 'DELETE', 'TRUNCATE',
}

# Two-word launchers (NOT bin/* — those are handled separately)
TWO_WORD = {
    'git', 'bundle', 'npx', 'bin/rails', 'bin/rake',
    'pnpm', 'yarn', 'npm', 'docker', 'docker-compose',
}

# Valid executable: lowercase-starting word with only letters, digits, hyphens, underscores
# Also allows bin/*, ./, /usr/*, /opt/* paths
VALID_EXE = re.compile(r'^[a-z][a-z0-9_-]*$|^bin/[a-z]|^\./|^/[a-z]')

def split_commands(cmd):
    """Split on &&, ||, |, ; using only the first line (skips heredoc bodies)."""
    first_line = cmd.split('\n')[0]
    return [p.strip() for p in re.split(r'\s*(?:&&|\|\|?|;)\s*', first_line) if p.strip()]

def derive_pattern(cmd):
    """Derive a Bash permission pattern from a single command string. Returns None for non-commands."""
    cmd = cmd.strip()
    if not cmd or cmd.startswith('#'):
        return None

    # Detect env var prefix(es) like RAILS_ENV=test or FOO=bar
    # Keep them in the pattern (Claude Code stores them verbatim, e.g. Bash(RAILS_ENV=test bin/rails:*))
    env_match = re.match(r'^((?:[a-zA-Z_][a-zA-Z0-9_]*=\S+\s+)+)', cmd)
    # Only treat as env var if values are simple (not subshell substitutions like $(...)
    env_prefix = ''
    if env_match and '$(' not in env_match.group(1):
        env_prefix = env_match.group(1).rstrip() + ' '
    rest = cmd[len(env_prefix):].strip() if env_prefix else cmd

    parts = rest.split()
    if not parts:
        return None

    first = parts[0]

    # Reject if first word looks like a shell flag, subshell, or non-executable
    if first.startswith('-') or first.startswith('$') or first.startswith('('):
        return None
    # Reject if fewer than 2 chars (single-letter Ruby/Python variables)
    if len(first) < 2:
        return None
    # Reject if first word contains code/string characters
    if re.search(r'["\'\(\)\\!\.\$\|=\{\}@]', first):
        return None

    # Validate the executable looks real (only if no env prefix — env+cmd pairs are kept as-is)
    if not env_prefix and not VALID_EXE.match(first):
        return None

    # bin/* executables — just the executable, no subcommand
    if first.startswith('bin/'):
        return f'Bash({env_prefix}{first}:*)'
    # Two-word launchers
    if first in TWO_WORD and len(parts) > 1:
        # Reject if second word looks like a flag or junk
        second = parts[1]
        if second.startswith('-') or re.search(r'["\'\(\)\\!\$]', second):
            return f'Bash({env_prefix}{first}:*)'
        return f'Bash({env_prefix}{first} {second}:*)'
    return f'Bash({env_prefix}{first}:*)'

def is_dangerous(pattern):
    inner = pattern[5:-3]  # strip Bash( and :*)
    return any(inner == d or inner.startswith(d + ' ') for d in DANGEROUS_PREFIXES)

# Load existing permissions
with open(settings_file) as f:
    settings = json.load(f)
existing_perms = set(settings.get('permissions', {}).get('allow', []))

# Find N most recent session files
sessions = sorted(sessions_dir.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:n_sessions]

if not sessions:
    print('NO_SESSIONS_FOUND')
    sys.exit(0)

# Collect and process all commands
safe_patterns = {}    # pattern -> example_cmd
flagged_patterns = {} # pattern -> example_cmd

for session_file in sessions:
    try:
        with open(session_file) as f:
            lines = [json.loads(l) for l in f if l.strip()]
        for item in lines:
            if item.get('type') != 'assistant':
                continue
            for block in item.get('message', {}).get('content', []):
                if not (isinstance(block, dict) and
                        block.get('type') == 'tool_use' and
                        block.get('name') == 'Bash'):
                    continue
                raw_cmd = block.get('input', {}).get('command', '')
                if not raw_cmd:
                    continue
                for sub_cmd in split_commands(raw_cmd):
                    pattern = derive_pattern(sub_cmd)
                    if not pattern:
                        continue
                    if pattern in existing_perms:
                        continue
                    example = sub_cmd[:80]
                    if is_dangerous(pattern):
                        if pattern not in flagged_patterns:
                            flagged_patterns[pattern] = example
                    else:
                        if pattern not in safe_patterns:
                            safe_patterns[pattern] = example
    except Exception as e:
        print(f'Warning: could not read {session_file.name}: {e}', file=sys.stderr)

# Write safe patterns
allow = settings.setdefault('permissions', {}).setdefault('allow', [])
added = []
for pattern in safe_patterns:
    if pattern not in set(allow):
        allow.append(pattern)
        added.append(pattern)

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')

# Output results
print(f'SCANNED={len(sessions)}')
print(f'ADDED={len(added)}')
for p in added:
    print(f'ADD\t{p}\t{safe_patterns[p]}')
print(f'FLAGGED={len(flagged_patterns)}')
for p, ex in flagged_patterns.items():
    print(f'FLAG\t{p}\t{ex}')
PYEOF
```

### 3. Report results

Parse the script output and present to the user:

**If `NO_SESSIONS_FOUND`:** Report "No session files found in `$SESSIONS_DIR`." and stop.

**Otherwise**, show:

```
Scanned N sessions. Added M permissions to .claude/settings.local.json:

  + Bash(git rev-parse:*)       ← git rev-parse HEAD~1
  + Bash(python3:*)             ← python3 - "$SESSIONS_DIR" ...
  ...
```

If any patterns were flagged as dangerous, show them separately and **do not add them**:

```
⚠ Skipped K dangerous patterns (review manually before adding):

  Bash(rm:*)          ← rm -rf /tmp/old
  Bash(git reset:*)   ← git reset --hard HEAD~1
  ...
```

If no new patterns were found: "All permissions from recent sessions are already saved."

## Notes

- Only writes to `.claude/settings.local.json` (project-local, gitignored). Never modifies `~/.claude/settings.json`.
- Scans the N most recent sessions (default 5, override via argument).
- Shell operator chains (`&&`, `|`, `;`) are split so each sub-command gets its own pattern.
- Dangerous patterns are flagged for manual review — they are never auto-added.
