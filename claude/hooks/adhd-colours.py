#!/usr/bin/env python3
import json
import os
import re
import sys

COLOURS = {
    "accent": (255, 180, 84),
    "bad": (255, 107, 107),
    "warn": (255, 216, 102),
    "ok": (90, 247, 142),
    "ask": (199, 146, 234),
    "info": (87, 199, 255),
}

LEAD = r"^(?:→\s*)?"
RULES = [
    ("bad", re.compile(LEAD + r"(?:❌|🔴|p0\b|block(?:ed|er|ing)?\b|fail(?:ed|ure|s)?\b|error\b|broken\b|refuted\b|not verified\b|danger\b)", re.I)),
    ("warn", re.compile(LEAD + r"(?:⚠️?|🟡|p1\b|warn(?:ing)?\b|risk\b|caveat\b|gotcha\b|uncertain\b|partial\b|stale\b|pending\b|worth noting\b|watch out\b|unverified\b|honest note\b)", re.I)),
    ("ok", re.compile(LEAD + r"(?:✅|🟢|ok\b|done\b|shipped\b|verified\b|pass(?:ed)?\b|merged\b|confirmed\b|fixed\b|settled\b|resolved\b|complete[d]?\b|works\b|live\b)", re.I)),
    ("ask", re.compile(LEAD + r"(?:❓|decision needed|decision\b|question\b|approve\b|needs you\b|your call\b|choose\b|pick\b|tl;dr|q\d+\b)", re.I)),
    ("info", re.compile(LEAD + r"(?:p[23]\b|also found\b|note\b|fyi\b|context\b|background\b|evidence\b|next\b|follow-?ups?\b)", re.I)),
]

BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
STEP = re.compile(r"^\d+\s*→$")


def classify(text):
    stripped = re.sub(r"^[\s*_`\"'(\[]+", "", text).strip()
    for level, pattern in RULES:
        if pattern.search(stripped):
            return level
    return None


def paint(text, level):
    r, g, b = COLOURS[level]
    return f"**\x1b[38;2;{r};{g};{b}m{text}\x1b[39m**"


def colour_line(line):
    line_level = None
    out = []
    last = 0
    for match in BOLD.finditer(line):
        inner = match.group(1)
        out.append(line[last:match.start()])
        if STEP.match(inner.strip()):
            out.append(match.group(0))
        else:
            level = classify(inner)
            if line_level is None:
                line_level = level or "accent"
            out.append(paint(inner, level or line_level))
        last = match.end()
    out.append(line[last:])
    return "".join(out)


def main():
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") != "cli":
        return
    data = json.load(sys.stdin)
    delta = data.get("delta", "")
    if "**" not in delta:
        return
    painted = "".join(colour_line(line) for line in delta.splitlines(keepends=True))
    json.dump({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": painted}}, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
