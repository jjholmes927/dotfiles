import json
import os
import subprocess
import unittest

from shell_test import REPO, ShellToolCase

SETUP = REPO / "coder" / "setup.sh"

CALL_LOG = 'echo "{name} $*" >> "$STUB_LOG_DIR/calls.log"\n'

STUBS = {
    "sudo": '#!/bin/sh\n' + CALL_LOG.format(name="sudo") + 'exec env "$@"\n',
    "apt-get": '#!/bin/sh\n' + CALL_LOG.format(name="apt-get"),
    "locale-gen": '#!/bin/sh\n' + CALL_LOG.format(name="locale-gen"),
    "docker": '#!/bin/sh\n' + CALL_LOG.format(name="docker")
    + '[ "$1 $2" = "info --format" ] && cat "$STUB_LOG_DIR/docker-driver"\nexit 0\n',
    "systemctl": '#!/bin/sh\n' + CALL_LOG.format(name="systemctl")
    + '[ "$*" = "restart docker" ] && echo overlay2 > "$STUB_LOG_DIR/docker-driver"\nexit 0\n',
}


class SystemPhaseDocker(ShellToolCase):
    def setUp(self):
        super().setUp()
        for name, body in STUBS.items():
            self.write_stub(name, body)
        self.daemon_json = os.path.join(self.root, "etc", "docker", "daemon.json")
        self.env.update({
            "CODER_SETUP_STATE": os.path.join(self.root, "state"),
            "DOCKER_DAEMON_JSON": self.daemon_json,
            "USER": "coder",
        })

    def system_phase(self, driver):
        with open(os.path.join(self.log_dir, "docker-driver"), "w") as fh:
            fh.write(driver + "\n")
        return subprocess.run([str(SETUP), "system"], env=self.env, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120, stdin=subprocess.DEVNULL)

    def calls(self):
        path = os.path.join(self.log_dir, "calls.log")
        return open(path).read().splitlines() if os.path.exists(path) else []

    def daemon_settings(self):
        with open(self.daemon_json) as fh:
            return json.load(fh)

    def test_moves_docker_onto_the_persisted_store(self):
        result = self.system_phase("overlayfs")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIs(self.daemon_settings()["features"]["containerd-snapshotter"], False)
        self.assertIn("systemctl restart docker", self.calls())

    def test_keeps_existing_docker_settings(self):
        os.makedirs(os.path.dirname(self.daemon_json))
        with open(self.daemon_json, "w") as fh:
            json.dump({"log-driver": "local", "features": {"buildkit": True}}, fh)
        result = self.system_phase("overlayfs")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.daemon_settings(), {
            "log-driver": "local",
            "features": {"buildkit": True, "containerd-snapshotter": False},
        })

    def test_leaves_docker_alone_when_already_persisted(self):
        result = self.system_phase("overlay2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.exists(self.daemon_json))
        self.assertNotIn("systemctl restart docker", self.calls())


if __name__ == "__main__":
    unittest.main()
