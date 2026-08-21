import importlib.util, importlib.machinery, pathlib, tempfile, unittest

_path = pathlib.Path(__file__).resolve().parent.parent / "bin" / "fleet"
_loader = importlib.machinery.SourceFileLoader("fleet", str(_path))
_spec = importlib.util.spec_from_loader("fleet", _loader)
fleet = importlib.util.module_from_spec(_spec)
_loader.exec_module(fleet)


class DeriveBucket(unittest.TestCase):
    def test_working_passes_through(self):
        self.assertEqual(fleet.derive_bucket("working", None), "WORKING")

    def test_blocked_passes_through(self):
        self.assertEqual(fleet.derive_bucket("blocked", None), "BLOCKED")

    def test_done_with_complete_sidecar(self):
        self.assertEqual(fleet.derive_bucket("done", ("complete", "t", "n")), "COMPLETE")

    def test_stopped_with_complete_sidecar(self):
        self.assertEqual(fleet.derive_bucket("stopped", ("complete", "t", "n")), "COMPLETE")

    def test_done_with_awaiting_sidecar(self):
        self.assertEqual(fleet.derive_bucket("done", ("awaiting", "t", "n")), "AWAITING")

    def test_done_silent_is_awaiting(self):
        self.assertEqual(fleet.derive_bucket("done", None), "AWAITING")

    def test_stopped_silent_is_stopped(self):
        self.assertEqual(fleet.derive_bucket("stopped", None), "STOPPED")

    def test_failed_is_stopped(self):
        self.assertEqual(fleet.derive_bucket("failed", None), "STOPPED")

    def test_stale_sidecar_never_recolors_live(self):
        self.assertEqual(fleet.derive_bucket("working", ("complete", "t", "n")), "WORKING")
        self.assertEqual(fleet.derive_bucket("blocked", ("awaiting", "t", "n")), "BLOCKED")


class ParsePr(unittest.TestCase):
    def test_pr_hash(self):
        self.assertEqual(fleet.parse_pr("INT-842 done, PR #9403"), "#9403")

    def test_bare_hash(self):
        self.assertEqual(fleet.parse_pr("merged #123 earlier"), "#123")

    def test_none(self):
        self.assertIsNone(fleet.parse_pr("no refs here"))


class Sidecars(unittest.TestCase):
    def test_roundtrip_and_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p / "abc-123").write_text("complete\t2026-08-21T10:00:00Z\tnote text\n")
            (p / "bad").write_text("only-one-field\n")
            (p / "ignore.tmp").write_text("complete\tt\tn\n")
            out = fleet.read_sidecars(str(p))
        self.assertEqual(out["abc-123"], ("complete", "2026-08-21T10:00:00Z", "note text"))
        self.assertNotIn("bad", out)
        self.assertNotIn("ignore.tmp", out)


class Stars(unittest.TestCase):
    def test_toggle_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(pathlib.Path(d) / "stars")
            fleet.toggle_star(path, "aaa")
            fleet.toggle_star(path, "bbb")
            self.assertEqual(fleet.read_stars(path), {"aaa", "bbb"})
            fleet.toggle_star(path, "aaa")
            self.assertEqual(fleet.read_stars(path), {"bbb"})

    def test_missing_file_is_empty(self):
        self.assertEqual(fleet.read_stars("/nonexistent/stars"), set())


class BuildModel(unittest.TestCase):
    def _sessions(self):
        return [
            {"sessionId": "a" * 36, "id": "aaaaaaaa", "name": "mn3/gate", "state": "blocked", "status": "q", "cwd": "/e/mn3/.worktrees/x", "startedAt": 1},
            {"sessionId": "b" * 36, "id": "bbbbbbbb", "name": "mn2/work", "state": "working", "status": "running", "cwd": "/e/mn2/.worktrees/y", "startedAt": 2},
            {"sessionId": "c" * 36, "id": "cccccccc", "name": "done-one", "state": "done", "status": "idle", "cwd": "/e", "startedAt": 3},
        ]

    def test_group_order_and_star_sort(self):
        sidecars = {"c" * 36: ("complete", "t", "PR #9")}
        model = fleet.build_model(self._sessions(), sidecars, {"b" * 36}, [])
        self.assertEqual([g[0] for g in model["groups"]], ["BLOCKED", "WORKING", "COMPLETE"])
        self.assertEqual(model["counts"]["BLOCKED"], 1)

    def test_empty_groups_omitted(self):
        model = fleet.build_model([], {}, set(), [])
        self.assertEqual(model["groups"], [])


class Formatting(unittest.TestCase):
    def test_narrow_width_drops_context(self):
        row = {"short": "aaaaaaaa", "name": "mn3/thing", "age": "12m", "context": "some ctx", "starred": False, "bucket": "BLOCKED"}
        lines = fleet.format_row(row, 70, False)
        self.assertEqual(len(lines), 1)

    def test_normal_width_two_lines(self):
        row = {"short": "aaaaaaaa", "name": "mn3/thing", "age": "12m", "context": "some ctx", "starred": True, "bucket": "BLOCKED"}
        lines = fleet.format_row(row, 120, True)
        self.assertEqual(len(lines), 2)
        self.assertIn("★", lines[0])


if __name__ == "__main__":
    unittest.main()
