#!/usr/bin/env python3
import json
import os
import re
import sys

ANSI = {
    "bad": "31",
    "warn": "33",
    "ok": "32",
    "ask": "35",
    "info": "34",
    "accent": "38;2;255;180;84",
}

RULES = {
    "bad": r"❌|🔴|p0\b|block(?:ed|er)?\b|fail(?:ed|ure)?\b|error\b|broken\b|refuted\b|not verified\b|red\b",
    "warn": r"⚠️?|🟡|p1\b|warn(?:ing)?\b|risk\b|caveat\b|gotcha\b|uncertain\b|partial\b|stale\b|pending\b|worth noting\b|watch out\b|unverified\b",
    "ok": r"✅|🟢|ok\b|done\b|shipped\b|verified\b|pass(?:ed)?\b|merged\b|confirmed\b|fixed\b|all implemented\b|green\b|resolved\b|complete[d]?\b|works\b",
    "ask": r"decision needed|decision\b|question\b|approve\b|gate\b|needs you\b|your call\b|choose\b|pick\b|tl;dr",
    "info": r"p[23]\b|also found\b|note\b|fyi\b|context\b|background\b|measured\b|evidence\b|next\b|follow-?ups?\b",
}


def main():
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") != "cli":
        return
    raw = sys.stdin.read()
    if "**" not in raw:
        return

    levels = [(level, re.compile(r"^(?:→\s*)?(?:" + words + ")", re.I)) for level, words in RULES.items()]
    bold = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
    step = re.compile(r"^\d+\s*→$")
    noise = re.compile(r"^[\s*_`\"'(\[]+")

    def classify(text):
        stripped = noise.sub("", text)
        return next((level for level, pattern in levels if pattern.match(stripped)), None)

    def colour_line(line):
        line_level = None

        def paint(match):
            nonlocal line_level
            inner = match.group(1)
            if step.match(inner):
                return match.group(0)
            level = classify(inner)
            if line_level is None:
                line_level = level or "accent"
            return f"**\x1b[{ANSI[level or line_level]}m{inner}\x1b[39m**"

        return bold.sub(paint, line)

    delta = json.loads(raw).get("delta", "")
    painted = "".join(colour_line(line) for line in delta.splitlines(keepends=True))
    json.dump({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": painted}}, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
