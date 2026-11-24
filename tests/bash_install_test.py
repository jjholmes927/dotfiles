import os
import subprocess
import unittest

from shell_test import REPO, ShellToolCase

INSTALL = REPO / "bash" / "install.sh"
PORTABLE = ["alias", "bash-colours", "bash-completion", "bash-history", "otel"]
START = "# >>> dotfiles profile.d >>>"


class BashInstall(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("uname")
        self.profile_d = os.path.join(self.home, ".profile.d")
        self.bashrc = os.path.join(self.home, ".bashrc")

    def install(self, system):
        self.env["STUB_UNAME_OUT"] = system + "\n"
        result = subprocess.run(["bash", str(INSTALL)], env=self.env, capture_output=True, encoding="utf-8",
                                errors="replace", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def target(self, name):
        return os.readlink(os.path.join(self.profile_d, name))

    def test_linux_links_portable_files_only(self):
        self.install("Linux")
        self.assertEqual(sorted(os.listdir(self.profile_d)), sorted(PORTABLE + ["linux-exports"]))
        for name in PORTABLE:
            self.assertEqual(self.target(name), str(REPO / "bash" / ".profile.d" / name))
        self.assertEqual(self.target("linux-exports"), str(REPO / "bash" / "linux" / "exports"))
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".bash_profile")))

    def test_linux_bashrc_block_added_once(self):
        with open(self.bashrc, "w") as fh:
            fh.write("export ORIGINAL=1\n")
        self.install("Linux")
        self.install("Linux")
        with open(self.bashrc) as fh:
            text = fh.read()
        self.assertEqual(text.count(START), 1)
        self.assertTrue(text.startswith("export ORIGINAL=1\n"))

    def test_darwin_unchanged(self):
        with open(self.bashrc, "w") as fh:
            fh.write("export ORIGINAL=1\n")
        self.install("Darwin")
        self.assertEqual(os.readlink(os.path.join(self.home, ".bash_profile")), str(REPO / "bash" / ".bash_profile"))
        expected = sorted(n for n in os.listdir(REPO / "bash" / ".profile.d") if not n.startswith("."))
        self.assertEqual(len(expected), 7)
        self.assertEqual(sorted(os.listdir(self.profile_d)), expected)
        with open(self.bashrc) as fh:
            self.assertEqual(fh.read(), "export ORIGINAL=1\n")

    def test_banner_shows_failed_status(self):
        self.install("Linux")
        state = os.path.join(self.home, ".local", "state", "coder-setup")
        os.makedirs(state)
        with open(os.path.join(state, "status"), "w") as fh:
            fh.write("system OK /s.log\nhome FAIL /x.log\n")
        result = subprocess.run(["bash", "-ic", "true"], env=self.env, capture_output=True, encoding="utf-8",
                                errors="replace", timeout=60, stdin=subprocess.DEVNULL)
        self.assertIn("coder-setup: home FAIL /x.log", result.stdout)
        self.assertNotIn("system OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
