import json
import os
import pathlib
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "claude" / "hooks" / "confirm-github-posts.sh"
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
AGENT = "gh-agent jjholmes927/NeverMissABeat"
COMMENT = f"{AGENT} pr comment 518 --body-file verdict.md"
MODES = ["bypassPermissions", "default", "acceptEdits"]


def decide(command, mode="bypassPermissions"):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "permission_mode": mode})
    result = subprocess.run([BASH, str(HOOK)], input=payload, capture_output=True, text=True, check=True)
    if not result.stdout.strip():
        return None, ""
    output = json.loads(result.stdout)["hookSpecificOutput"]
    return output["permissionDecision"], output["permissionDecisionReason"]


class HookCase(unittest.TestCase):
    def assertDecision(self, command, bypass, other, reason):
        for mode in MODES:
            with self.subTest(command=command, mode=mode):
                decision, why = decide(command, mode)
                self.assertEqual(bypass if mode == "bypassPermissions" else other, decision)
                self.assertIn(reason, why)


class AgentCommentTests(HookCase):

    def test_single_agent_pr_comment_is_allowed_in_every_mode(self):
        for command in [COMMENT, f"  {AGENT} pr comment 518 --body 'Production check passed'", f"{AGENT} pr comment 518 --edit-last --body-file verdict.md"]:
            self.assertDecision(command, "allow", "allow", "agent bot")

    def test_other_agent_posts_still_need_joel(self):
        for command in [
            f"{AGENT} pr review 518 --approve",
            f"{AGENT} pr review 518 --comment --body ok",
            f"{AGENT} issue comment 12 --body hi",
            f"{AGENT} api repos/jjholmes927/NeverMissABeat/issues/518/comments -X POST -f body=hi",
            f"{AGENT} api repos/jjholmes927/NeverMissABeat/pulls/518/reviews --input review.json",
        ]:
            self.assertDecision(command, "deny", "ask", "agent bot")

    def test_chained_agent_comment_falls_through_to_the_guard(self):
        for command in [
            f"{COMMENT}; {AGENT} pr review 518 --approve",
            f"{COMMENT} && echo done",
            f"{COMMENT} & sleep 1",
            f"{COMMENT} | tee out.log",
            f"{COMMENT}\necho done",
            f"{AGENT} pr comment 518 --body-file - <<'EOF'\nverdict\nEOF",
            f"{AGENT} pr comment 518 --body \"$(cat verdict.md)\"",
            f"{AGENT} pr comment 518 --body `cat verdict.md`",
            f"{AGENT} pr comment 518 --body-file <(echo verdict)",
            f"{COMMENT} > ~/.zshrc",
            f"{AGENT} pr comment 518 --body-file - < verdict.md",
            f"cd /tmp && {COMMENT}",
            f"FOO=1 {COMMENT}",
        ]:
            self.assertDecision(command, "deny", "ask", "agent bot")

    def test_chained_post_as_joel_is_never_smuggled_through(self):
        for command in [
            f"{COMMENT}; gh pr comment 518 --body hi",
            f"{COMMENT} && gh pr comment 518 --body hi",
            f"{COMMENT} || gh pr comment 518 --body hi",
            f"cat x | {COMMENT} | gh pr comment 518 --body-file -",
            f"{COMMENT}\ngh pr review 518 --approve",
            f"{AGENT} pr comment 518 --body \"$(gh pr comment 518 --body hi)\"",
            f"{AGENT} pr comment 518 --body `gh pr comment 518 --body hi`",
            f"{COMMENT} gh pr review 518 --approve",
            f"{COMMENT} /opt/homebrew/bin/gh pr comment 518 --body hi",
            f"{COMMENT}; gh api repos/o/r/issues/518/comments -X POST -f body=hi",
        ]:
            self.assertDecision(command, "deny", "ask", "as Joel")

    def test_non_posting_agent_commands_are_left_alone(self):
        for command in [f"{AGENT} pr view 518", f"{AGENT} pr checks 518", "gh-agent --check jjholmes927/NeverMissABeat"]:
            self.assertDecision(command, None, None, "")


class ExistingGuardTests(HookCase):
    def test_posts_as_joel_ask_or_deny_in_bypass(self):
        for command in [
            "gh pr comment 518 --body hi",
            "gh issue comment 12 --body hi",
            "gh pr review 518 --approve",
            "gh api repos/o/r/pulls/518/comments -f body=hi",
            "gh api repos/o/r/pulls/518/reviews -X POST --input review.json",
            "cd repo && gh pr comment 518 --body-file x.md",
        ]:
            with self.subTest(command=command):
                self.assertEqual(("deny", "This posts to GitHub as Joel and bypass mode cannot confirm it - ask Joel in chat first, then have him post it or switch out of bypass mode"), decide(command))
                self.assertEqual(("ask", "This posts to GitHub as Joel - confirm to send"), decide(command, "default"))

    def test_e2e_finding_comments_stay_auto_allowed(self):
        for command in ["gh pr comment 518 --body '[e2e resolved] fixed in abc'", "gh pr comment 518 --body '[e2e unresolved] still failing'"]:
            self.assertDecision(command, "allow", "allow", "e2e pipeline finding comment - auto-allowed")

    def test_reads_and_unrelated_commands_get_no_decision(self):
        for command in ["gh pr view 518", "gh api repos/o/r/pulls/518/comments", "gh pr list", "git status", "ls -la", ""]:
            self.assertDecision(command, None, None, "")


if __name__ == "__main__":
    unittest.main()
