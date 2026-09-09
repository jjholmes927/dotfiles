---
name: simplify
description: Review recently changed code for reuse, clarity, and efficiency, and fix concrete issues before shipping. Provides the simplify step used by ship.
---

Inspect the working tree diff and the branch diff against its actual base.
Review reuse, code quality, and efficiency. Use independent review tasks when
available and appropriate; otherwise perform the three passes sequentially.
Fix concrete regressions or avoidable complexity in the changed code, preserve
the requested behavior, and rerun affected checks. Do not broaden scope to
unrelated refactoring. Report changes and verification evidence. If invoked by
ship, return to ship so it can re-verify the changed tree before pushing.
