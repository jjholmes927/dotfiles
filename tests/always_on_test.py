import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
POINTER = (ROOT / "workflow/always-on.md").read_text().strip()


class AlwaysOnPointerTests(unittest.TestCase):
    def test_claude_md_contains_pointer(self):
        self.assertIn(POINTER, (ROOT / "claude/CLAUDE.md").read_text())

    def test_codex_agents_contains_pointer(self):
        self.assertIn(POINTER, (ROOT / "codex/AGENTS.md").read_text())


if __name__ == "__main__":
    unittest.main()
