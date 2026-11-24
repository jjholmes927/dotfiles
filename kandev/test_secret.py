import subprocess
import unittest
from unittest import mock

import configure


class KeychainSecret(unittest.TestCase):
    def test_keychain_secret_uses_secret_get(self):
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="key-value\n", stderr="")
        with mock.patch.object(configure.subprocess, "run", return_value=done) as run:
            value = configure.keychain_secret("linear-api-key")
        self.assertEqual(value, "key-value")
        self.assertEqual(run.call_args.args[0], [str(configure.SECRET_GET), "linear-api-key"])

    def test_secret_get_lives_in_repo_bin(self):
        self.assertEqual(configure.SECRET_GET.name, "secret-get")
        self.assertEqual(configure.SECRET_GET.parent.name, "bin")


if __name__ == "__main__":
    unittest.main()
