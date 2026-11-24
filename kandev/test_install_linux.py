import getpass
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import configure

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent


class InstallLinux(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = pathlib.Path(os.path.realpath(holder.name))
        self.conf = self.root / "fleet.json"
        self.conf.write_text(json.dumps({"kandev_version": "0.100.0"}))
        self.stub_bin = self.root / "stub-bin"
        self.stub_bin.mkdir()
        self.path = f"{self.stub_bin}:/usr/bin:/bin"

    def stub(self, directory, name, body):
        path = directory / name
        path.write_text(body)
        path.chmod(0o755)
        return path

    def run_script(self, script, *args, system="Linux"):
        self.stub(self.stub_bin, "uname", f"#!/bin/sh\necho {system}\n")
        env = {"HOME": "/home/t", "PATH": self.path, "KANDEV_FLEET_CONF": str(self.conf)}
        return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=60)

    def test_render_units_fills_placeholders(self):
        out = self.root / "units"
        result = self.run_script(HERE / "install-linux.sh", "--render-units", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        kandev = (out / "kandev.service").read_text()
        observer = (out / "kandev-observer.service").read_text()
        bundle = "/home/t/.local/share/kandev/0.100.0/kandev"
        for unit in (kandev, observer):
            self.assertNotIn("@", unit)
            self.assertIn(f"User={getpass.getuser()}", unit)
            self.assertIn(f"Environment=PATH={self.path}", unit)
            self.assertIn("EnvironmentFile=-/home/t/.config/coder-setup/agent.env", unit)
        self.assertIn(f"ExecStart={bundle}/bin/kandev --headless", kandev)
        self.assertIn(f"Environment=KANDEV_BUNDLE_DIR={bundle}", kandev)
        self.assertIn("Environment=KANDEV_VERSION=0.100.0", kandev)
        self.assertIn("StandardOutput=append:/home/t/.kandev/logs/service.out", kandev)
        self.assertIn(f"ExecStart={REPO}/kandev/fleet-observer.sh", observer)
        self.assertIn("StandardOutput=append:/home/t/.kandev/logs/observer.out", observer)

    def copy_install(self):
        work = self.root / "kandev"
        work.mkdir()
        shutil.copy(HERE / "install.sh", work / "install.sh")
        log = self.root / "dispatched.log"
        self.stub(work, "install-linux.sh", f"#!/bin/sh\necho \"$@\" > {log}\n")
        return work / "install.sh", log

    def test_install_sh_dispatches_on_linux(self):
        script, log = self.copy_install()
        result = self.run_script(script, "--x")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text(), "--x\n")

    def test_install_sh_unchanged_on_darwin(self):
        script, log = self.copy_install()
        result = self.run_script(script, "--x", system="Darwin")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Homebrew is required", result.stderr)
        self.assertFalse(log.exists())

    def test_missing_kandev_hint_on_linux_skips_brew(self):
        with mock.patch.object(configure.sys, "platform", "linux"), \
                mock.patch.object(configure.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(RuntimeError) as caught:
                configure.require_kandev()
        self.assertIn("kandev/install.sh", str(caught.exception))
        self.assertNotIn("brew", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
