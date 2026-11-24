import os
import unittest

from shell_test import ShellToolCase


class SecretGet(ShellToolCase):
    def setUp(self):
        super().setUp()
        self.write_stub("uname")
        self.write_stub("security")
        self.secrets = os.path.join(self.home, ".config", "secrets")

    def on(self, system):
        self.env["STUB_UNAME_OUT"] = system + "\n"

    def secret(self, name, value, mode=0o600):
        os.makedirs(self.secrets, exist_ok=True)
        path = os.path.join(self.secrets, name)
        with open(path, "w") as fh:
            fh.write(value)
        os.chmod(path, mode)
        return path

    def test_darwin_reads_keychain(self):
        self.on("Darwin")
        self.env["STUB_SECURITY_OUT"] = "abc\n"
        result = self.run_tool("secret-get", "linear-api-key")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "abc\n")
        self.assertEqual([c["argv"] for c in self.stub_calls("security")],
                         [["find-generic-password", "-s", "linear-api-key", "-w"]])

    def test_linux_reads_file(self):
        self.on("Linux")
        self.secret("linear-api-key", "xyz\n")
        result = self.run_tool("secret-get", "linear-api-key")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "xyz\n")
        self.assertEqual(self.stub_calls("security"), [])

    def test_linux_missing_is_silent_exit_1(self):
        self.on("Linux")
        result = self.run_tool("secret-get", "linear-api-key")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_linux_loose_permissions_refused(self):
        self.on("Linux")
        self.secret("linear-api-key", "xyz\n", mode=0o644)
        result = self.run_tool("secret-get", "linear-api-key")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("mode 600", result.stderr)

    def test_name_with_path_rejected(self):
        self.on("Linux")
        self.secret("x", "leak\n")
        result = self.run_tool("secret-get", "../secrets/x")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
