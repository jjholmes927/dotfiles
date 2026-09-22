# Shared workflows in Cursor

Use Cursor's native file, search and shell tools. Source frontmatter describes
the workflow; `allowed-tools` does not grant Cursor permissions. Resolve script
paths from the source root in this skill's entry, never the current repository.
For a script that reads CLAUDE_PLUGIN_ROOT, set it only for that invocation.

Use this Cursor adapter's instructions when a workflow also appears in a Claude
or Codex skill directory. Those directories can be discovered automatically;
their harness-specific tool names and configuration are not Cursor interfaces.
A slash-command dependency means read and follow its installed workflow.
For personal workflows, resolve siblings from this adapter's skills directory.
For an unported dependency, read it from the recorded canonical package root and
apply these mappings. Keep Beam team variants explicit instead of replacing
the personal ship/verify workflows with similarly named Beam commands.

## Tools, questions and permissions

- Read/Write/Edit/Glob/Grep/Bash mean the available native equivalents.
- Skill means read the selected SKILL.md and its referenced instructions.
- TodoWrite means the native todo tool when available; otherwise maintain the plan.
- In Kandev, use its plan and ask_user_question_kandev tools. A pending, timed-out
  or disconnected question is a hard waiting barrier: end the turn and do no
  dependent work until completed answers arrive. Rejection is not approval.
- Outside Kandev, use Cursor's question tool when available, or ask in the reply
  and end the turn. Never manufacture an answer or approval.
- EnterPlanMode/ExitPlanMode mean planning and the workflow's human approval
  gate. Cursor's plan/ask modes do not themselves establish user approval.
- Find MCP tools by capability and inspect their actual schemas. Do not invent
  Claude tool names or silently skip a required unavailable integration.
- Task/Agent means native subagents only when available and explicitly authorized.
  Children receive bounded briefs, not recursive E2E orchestration. If optional
  delegation is unavailable, apply review lenses sequentially and say so;
  required independent review still needs its authorized separate-context route.
- Preserve Cursor/Kandev permissions. Do not edit another harness's settings or
  use --force/--yolo to bypass a missing permission or approval.

## Delivery and review

E2E's explicit execution profile owns implementation and review routing. A
Cursor host does not imply a particular model or external CLI. Record requested
models and observed identities separately; fresh context is not model diversity.
Required read-only review must enforce its write boundary, including MCP tools.
Use the installed verify, verify-ui and writing-pr-descriptions workflows.
Use an available simplify skill or perform the source's stated checks directly.
Repository runtime, PR and attachment guides retain authority over generic examples.
Preserve approval, verification fingerprints, PR size/readiness and retry limits.
Only signal Kandev completion after the step's actual evidence criteria are met.
Do not infer permission to publish comments/reviews from authorship; report locally
unless the session authorizes publication. Missing required review stays incomplete.

## Beam Socratic interview

Preserve the source's question ladder, evidence-backed grading, corrections,
detours and ending. Interviewing does not authorize implementation. In Kandev,
ask one question at a time: put feedback in context_paragraphs and the next
question in prompt. When options are required, use "Skip this question" and
"End interview", never candidate answers or hints. A skip is not an incorrect
answer. End/rejection produces the source's scorecard using actual answers only.
Never grade or continue without a completed answer.
