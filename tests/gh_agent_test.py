import base64
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import time
import unittest

from shell_test import BIN, LOGGING_STUB, ShellToolCase

SCRIPT = BIN / "gh-agent"
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
TOKEN = "ghs_installationTokenValue123"

CURL_STUB = r'''#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
method, data, url = "GET", None, None
index = 0
while index < len(args):
    item = args[index]
    if item in ("-X", "--data", "-H", "-w", "--config"):
        value = args[index + 1]
        if item == "-X":
            method = value
        elif item == "--data":
            data = value
        index += 2
        continue
    if not item.startswith("-"):
        url = item
    index += 1
config = sys.stdin.read()
with open(os.path.join(os.environ["STUB_LOG_DIR"], "curl.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": args, "method": method, "url": url, "data": data, "config": config}) + "\n")
path = url.split("https://api.github.com", 1)[1]
credential = config.split("Bearer ", 1)[1].split('"', 1)[0]
reachable = [{"id": 1001, "full_name": "jjholmes927/NeverMissABeat"}, {"id": 2002, "full_name": "jjholmes927/Other"}]
if path.endswith("/installation"):
    status = os.environ.get("STUB_INSTALL_STATUS", "200")
    body = {"id": 42} if status == "200" else {"message": "Moved Permanently" if status == "301" else "Not Found"}
elif path == "/app/installations/42/access_tokens":
    status = "201"
    request = json.loads(data)
    if "repository_ids" in request:
        body = {"token": os.environ["STUB_TOKEN"], "expires_at": os.environ["STUB_EXPIRES"], "repositories": [r for r in reachable if r["id"] in request["repository_ids"]]}
    else:
        body = {"token": "ghs_lookupTokenValue456", "expires_at": os.environ["STUB_EXPIRES"]}
elif path.startswith("/installation/repositories"):
    status = "200"
    repos = reachable if credential == "ghs_lookupTokenValue456" else reachable[:1]
    body = {"total_count": len(repos), "repositories": repos}
else:
    status = "404"
    body = {"message": "Not Found"}
sys.stdout.write(json.dumps(body) + "\n" + status)
'''

GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys

with open(os.path.join(os.environ["STUB_LOG_DIR"], "gh.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "token": os.environ.get("GH_TOKEN"), "repo": os.environ.get("GH_REPO")}) + "\n")
print("gh ran")
'''


def iso(offset):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


def b64url_decode(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class GhAgentTests(ShellToolCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory()
        keys = pathlib.Path(cls.keys.name)
        cls.private = keys / "key.pem"
        cls.public = keys / "pub.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(cls.private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(cls.private), "-pubout", "-out", str(cls.public)], check=True, capture_output=True)
        cls.key_b64 = base64.b64encode(cls.private.read_bytes()).decode()

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        super().setUp()
        self.write_stub("security")
        self.write_stub("curl", CURL_STUB)
        self.write_stub("gh", GH_STUB)
        home = pathlib.Path(self.home)
        self.app = home / ".config/jjholmes927-agent/app.json"
        self.app.parent.mkdir(parents=True)
        self.app.write_text(json.dumps({"id": 5878121, "slug": "never-miss-a-bot", "keychain_service": "agent-service"}))
        self.cache = home / ".cache/jjholmes927-agent/jjholmes927__NeverMissABeat.json"
        self.env.update({"STUB_SECURITY_OUT": self.key_b64 + "\n", "STUB_TOKEN": TOKEN, "STUB_EXPIRES": iso(3600)})

    def run_agent(self, *args, **env):
        result = subprocess.run([BASH, str(SCRIPT), *args], env={**self.env, **env}, capture_output=True, text=True)
        for secret in (TOKEN, "ghs_lookupTokenValue456", self.key_b64[:40], "BEGIN PRIVATE KEY", "Bearer"):
            self.assertNotIn(secret, result.stdout + result.stderr)
        return result

    def test_runs_gh_with_a_repo_scoped_token_for_that_command_only(self):
        result = self.run_agent("jjholmes927/NeverMissABeat", "pr", "comment", "518", "--body-file", "verdict.md")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("gh ran\n", result.stdout)
        self.assertEqual([["find-generic-password", "-s", "agent-service", "-a", "private-key", "-w"]], [call["argv"] for call in self.stub_calls("security")])
        [call] = self.stub_calls("gh")
        self.assertEqual({"argv": ["pr", "comment", "518", "--body-file", "verdict.md"], "token": TOKEN, "repo": "jjholmes927/NeverMissABeat"}, call)
        installation, lookup, listing, mint = self.stub_calls("curl")
        self.assertEqual(("GET", "https://api.github.com/repos/jjholmes927/NeverMissABeat/installation"), (installation["method"], installation["url"]))
        self.assertEqual({"permissions": {"metadata": "read"}}, json.loads(lookup["data"]))
        self.assertEqual("https://api.github.com/installation/repositories?per_page=100", listing["url"])
        self.assertEqual(("POST", "https://api.github.com/app/installations/42/access_tokens"), (mint["method"], mint["url"]))
        self.assertEqual({"repository_ids": [1001], "permissions": {"pull_requests": "write"}}, json.loads(mint["data"]))
        self.assertFalse(any("Bearer" in item for request in self.stub_calls("curl") for item in request["argv"]))

    def test_repository_id_is_cached_so_later_mints_skip_the_lookup(self):
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "1", STUB_EXPIRES=iso(500)).returncode)
        self.assertEqual(1001, json.loads(self.cache.read_text())["repository_id"])
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "2").returncode)
        later = self.stub_calls("curl")[4:]
        self.assertEqual(2, len(later))
        self.assertEqual({"repository_ids": [1001], "permissions": {"pull_requests": "write"}}, json.loads(later[1]["data"]))

    def test_jwt_is_signed_by_the_keychain_key_and_short_lived(self):
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "518").returncode)
        config = self.stub_calls("curl")[0]["config"]
        jwt = config.split("Bearer ", 1)[1].split('"', 1)[0]
        header, payload, signature = jwt.split(".")
        self.assertEqual({"alg": "RS256", "typ": "JWT"}, json.loads(b64url_decode(header)))
        claims = json.loads(b64url_decode(payload))
        self.assertEqual("5878121", claims["iss"])
        self.assertEqual(600, claims["exp"] - claims["iat"])
        self.assertLessEqual(abs(claims["iat"] + 60 - time.time()), 30)
        signed = pathlib.Path(self.root) / "signed"
        signed.write_text(f"{header}.{payload}")
        sig = pathlib.Path(self.root) / "sig"
        sig.write_bytes(b64url_decode(signature))
        verify = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(self.public), "-signature", str(sig), str(signed)], capture_output=True, text=True)
        self.assertEqual(0, verify.returncode, verify.stdout + verify.stderr)

    def test_token_is_cached_privately_and_reused(self):
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "1").returncode)
        self.assertEqual(0o600, stat.S_IMODE(self.cache.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(self.cache.parent.stat().st_mode))
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "2").returncode)
        self.assertEqual(4, len(self.stub_calls("curl")))
        self.assertEqual([TOKEN, TOKEN], [call["token"] for call in self.stub_calls("gh")])

    def test_token_within_ten_minutes_of_expiry_is_replaced(self):
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "1", STUB_EXPIRES=iso(500)).returncode)
        self.assertEqual(0, self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "2").returncode)
        self.assertEqual(6, len(self.stub_calls("curl")))
        self.assertEqual([TOKEN, TOKEN], [call["token"] for call in self.stub_calls("gh")])

    def test_machine_without_the_app_fails_clearly(self):
        self.app.unlink()
        result = self.run_agent("jjholmes927/NeverMissABeat", "pr", "comment", "518", "--body-file", "verdict.md")
        self.assertEqual(1, result.returncode)
        self.assertIn("not set up on this machine", result.stderr)
        self.assertEqual([], self.stub_calls("gh") + self.stub_calls("curl") + self.stub_calls("security"))

    def test_missing_keychain_key_fails_clearly(self):
        result = self.run_agent("jjholmes927/NeverMissABeat", "pr", "view", "1", STUB_SECURITY_OUT="", STUB_SECURITY_RC="44")
        self.assertEqual(1, result.returncode)
        self.assertIn("no private key in the macOS Keychain (service agent-service", result.stderr)
        self.assertEqual([], self.stub_calls("gh") + self.stub_calls("curl"))

    def test_repository_without_the_app_fails_clearly(self):
        for repo, env, message in [
            ("jjholmes927/elsewhere", {"STUB_INSTALL_STATUS": "404"}, "never-miss-a-bot is not installed on jjholmes927/elsewhere"),
            ("jjholmes927/GigMe", {"STUB_INSTALL_STATUS": "301"}, "jjholmes927/GigMe has been renamed or moved"),
            ("jjholmes927/Unlisted", {}, "never-miss-a-bot cannot reach jjholmes927/Unlisted"),
        ]:
            with self.subTest(repo=repo):
                result = self.run_agent(repo, "pr", "view", "1", **env)
                self.assertEqual(1, result.returncode)
                self.assertIn(message, result.stderr)
        self.assertEqual([], self.stub_calls("gh"))

    def test_check_mints_and_prints_only_the_repositories_reached(self):
        result = self.run_agent("--check", "jjholmes927/NeverMissABeat")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("never-miss-a-bot reaches jjholmes927/NeverMissABeat\n", result.stdout)
        self.assertEqual("https://api.github.com/installation/repositories", self.stub_calls("curl")[-1]["url"])
        self.assertIn(TOKEN, self.stub_calls("curl")[-1]["config"])
        self.assertEqual([], self.stub_calls("gh"))

    def test_bad_arguments_are_rejected_before_any_call(self):
        for args in [(), ("jjholmes927/NeverMissABeat",), ("--check",), ("../../etc", "pr", "view"), ("owner/repo;rm", "pr", "view")]:
            with self.subTest(args=args):
                self.assertNotEqual(0, self.run_agent(*args).returncode)
        self.assertEqual([], self.stub_calls("gh") + self.stub_calls("curl") + self.stub_calls("security"))


if __name__ == "__main__":
    unittest.main()
