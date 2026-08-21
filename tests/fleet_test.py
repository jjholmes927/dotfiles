import importlib.util, importlib.machinery, json, os, pathlib, tempfile, time, unittest

_path = pathlib.Path(__file__).resolve().parent.parent / "bin" / "fleet"
_loader = importlib.machinery.SourceFileLoader("fleet", str(_path))
_spec = importlib.util.spec_from_loader("fleet", _loader)
fleet = importlib.util.module_from_spec(_spec)
_loader.exec_module(fleet)


class DeriveBucket(unittest.TestCase):
    def test_working_passes_through(self):
        self.assertEqual(fleet.derive_bucket("working", "running", None), "WORKING")

    def test_blocked_passes_through(self):
        self.assertEqual(fleet.derive_bucket("blocked", None, None), "BLOCKED")

    def test_done_with_complete_sidecar(self):
        self.assertEqual(fleet.derive_bucket("done", None, ("complete", "t", "n")), "COMPLETE")

    def test_stopped_with_complete_sidecar(self):
        self.assertEqual(fleet.derive_bucket("stopped", None, ("complete", "t", "n")), "COMPLETE")

    def test_done_with_awaiting_sidecar(self):
        self.assertEqual(fleet.derive_bucket("done", None, ("awaiting", "t", "n")), "AWAITING")

    def test_done_silent_is_awaiting(self):
        self.assertEqual(fleet.derive_bucket("done", None, None), "AWAITING")

    def test_stopped_silent_is_stopped(self):
        self.assertEqual(fleet.derive_bucket("stopped", None, None), "STOPPED")

    def test_failed_is_stopped(self):
        self.assertEqual(fleet.derive_bucket("failed", None, None), "STOPPED")

    def test_stale_sidecar_never_recolors_live(self):
        self.assertEqual(fleet.derive_bucket("working", "running", ("complete", "t", "n")), "WORKING")
        self.assertEqual(fleet.derive_bucket("blocked", None, ("awaiting", "t", "n")), "BLOCKED")


class IdleBlockedBucketsBySidecar(unittest.TestCase):
    def test_idle_blocked_with_complete_sidecar_is_complete(self):
        self.assertEqual(fleet.derive_bucket("blocked", "idle", ("complete", "t", "n")), "COMPLETE")

    def test_idle_blocked_without_sidecar_is_awaiting(self):
        self.assertEqual(fleet.derive_bucket("blocked", "idle", None), "AWAITING")

    def test_idle_blocked_with_awaiting_sidecar_is_awaiting(self):
        self.assertEqual(fleet.derive_bucket("blocked", "idle", ("awaiting", "t", "n")), "AWAITING")

    def test_live_gate_reports_no_status_and_stays_blocked(self):
        self.assertEqual(fleet.derive_bucket("blocked", None, ("complete", "t", "n")), "BLOCKED")

    def test_waiting_status_stays_blocked(self):
        self.assertEqual(fleet.derive_bucket("blocked", "waiting", ("complete", "t", "n")), "BLOCKED")

    def test_answered_session_lands_in_complete_through_the_model(self):
        sessions = [{"sessionId": "d" * 36, "id": "dddddddd", "name": "answered", "state": "blocked", "status": "idle", "cwd": "/e", "startedAt": 1}]
        sidecars = {"d" * 36: ("complete", "t", "Done — recorded.")}
        model = fleet.build_model(sessions, sidecars, set(), [])
        self.assertEqual([g[0] for g in model["groups"]], ["COMPLETE"])
        self.assertEqual(model["groups"][0][1][0]["context"], "Done — recorded.")


class RemodelBucketsFromRawCliStatus(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._saved = (fleet.PROJECTS_DIR, fleet.SIDECAR_DIR, fleet.STARS_PATH)
        root = self._temp.name
        fleet.PROJECTS_DIR = os.path.join(root, "projects")
        fleet.SIDECAR_DIR = os.path.join(root, "fleet-status")
        fleet.STARS_PATH = os.path.join(root, "fleet-stars")
        os.makedirs(fleet.SIDECAR_DIR)

    def tearDown(self):
        fleet.PROJECTS_DIR, fleet.SIDECAR_DIR, fleet.STARS_PATH = self._saved
        self._temp.cleanup()

    def _transcript(self, cwd, session_id, text):
        path = fleet.transcript_path(cwd, session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _sidecar(self, session_id, state, note):
        with open(os.path.join(fleet.SIDECAR_DIR, session_id), "w", encoding="utf-8") as handle:
            handle.write("%s\t2026-08-21T10:00:00Z\t%s\n" % (state, note))

    def _row(self, session):
        state = fleet.FleetState()
        state.sessions = [session]
        fleet.remodel(state)
        return state.rows[0]

    def _session(self, session_id, **extra):
        session = {
            "sessionId": session_id,
            "id": session_id[:8],
            "name": "parked",
            "state": "blocked",
            "cwd": "/e/mn3/.worktrees/task-3",
            "startedAt": 1,
        }
        session.update(extra)
        return session

    def test_answered_idle_blocked_lands_complete_with_transcript_context(self):
        session_id = "e" * 36
        self._transcript("/e/mn3/.worktrees/task-3", session_id, "Recorded the status; ready for review.")
        self._sidecar(session_id, "complete", "")
        row = self._row(self._session(session_id, status="idle"))
        self.assertEqual(row["bucket"], "COMPLETE")
        self.assertEqual(row["context"], "Recorded the status; ready for review.")

    def test_answered_idle_blocked_without_sidecar_lands_awaiting(self):
        session_id = "f" * 36
        self._transcript("/e/mn3/.worktrees/task-3", session_id, "Still thinking about it.")
        row = self._row(self._session(session_id, status="idle"))
        self.assertEqual(row["bucket"], "AWAITING")
        self.assertEqual(row["context"], "Still thinking about it.")

    def test_genuine_gate_with_transcript_stays_blocked(self):
        session_id = "g" * 36
        self._transcript("/e/mn3/.worktrees/task-3", session_id, "Which option do you want?")
        self._sidecar(session_id, "complete", "stale note PR #9")
        row = self._row(self._session(session_id))
        self.assertEqual(row["bucket"], "BLOCKED")
        self.assertEqual(row["context"], "Which option do you want?")
        self.assertIsNone(row["pr"])

    def test_sidecar_note_still_wins_over_transcript_when_settled(self):
        session_id = "h" * 36
        self._transcript("/e/mn3/.worktrees/task-3", session_id, "transcript tail")
        self._sidecar(session_id, "complete", "INT-842 done, PR #9403")
        row = self._row(self._session(session_id, status="idle"))
        self.assertEqual(row["bucket"], "COMPLETE")
        self.assertEqual(row["context"], "INT-842 done, PR #9403")
        self.assertEqual(row["pr"], "#9403")


class OverlayFlushesTypeahead(unittest.TestCase):
    class Fake(object):
        def __init__(self, log):
            self.log = log

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            self.log.append("getch")
            return ord("x")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def test_flushinp_runs_before_the_blocking_read(self):
        log = []
        saved = (fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate)
        try:
            fleet.curses.newwin = lambda *args: self.Fake(log)
            fleet.curses.flushinp = lambda: log.append("flushinp")
            fleet.curses.doupdate = lambda: None
            key = fleet.overlay(self.Fake(log), "title", ["body"], "footer")
        finally:
            fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate = saved
        self.assertEqual(key, ord("x"))
        self.assertEqual(log, ["flushinp", "getch"])


class GateAnswerNewWindowTimeout(unittest.TestCase):
    def setUp(self):
        self._real_run_out = fleet.run_out
        self.calls = []

    def tearDown(self):
        fleet.run_out = self._real_run_out

    def test_timeout_warns_a_hidden_window_may_be_live(self):
        def fake(args, timeout=10):
            self.calls.append(args)
            return 124, "timed out after 5s"

        fleet.run_out = fake
        message, action = fleet.gate_answer(None, {"short": "abc12345"}, "abc12345")
        self.assertIn("hidden attach window for abc12345 may be live", message)
        self.assertIn("tmux list-windows", message)
        self.assertEqual(action, "")
        self.assertEqual(len(self.calls), 1)

    def test_plain_failure_still_reports_new_window_failed(self):
        def fake(args, timeout=10):
            self.calls.append(args)
            return 1, "no server running"

        fleet.run_out = fake
        message, action = fleet.gate_answer(None, {"short": "abc12345"}, "abc12345")
        self.assertIn("tmux new-window failed", message)
        self.assertNotIn("may be live", message)
        self.assertEqual(action, "")


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

    def test_pr_badge_on_first_line(self):
        sessions = [{"sessionId": "p" * 36, "id": "pppppppp", "name": "ship-it", "state": "done", "status": "idle", "cwd": "/e", "startedAt": 1}]
        sidecars = {"p" * 36: ("complete", "t", "INT-842 done, PR #9403")}
        model = fleet.build_model(sessions, sidecars, set(), [])
        row = model["groups"][0][1][0]
        lines = fleet.format_row(row, 120, False)
        self.assertIn("PR #9403", lines[0])
        self.assertLess(lines[0].index("ship-it"), lines[0].index("PR #9403"))

    def test_no_pr_leaves_first_line_clean(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "2h", "context": "c", "starred": False, "bucket": "COMPLETE", "pr": None}
        self.assertNotIn("PR", fleet.format_row(row, 120, False)[0])


class LaneStrip(unittest.TestCase):
    def test_clean_and_dirty_lanes(self):
        lanes = [
            {"name": "mn1", "branch": "main", "dirty": False, "worktrees": 2},
            {"name": "mn3", "branch": "main", "dirty": True, "worktrees": 1},
        ]
        lines = fleet.format_lane_strip(lanes, 120)
        joined = " ".join(lines)
        self.assertIn("mn1 ✓2", joined)
        self.assertIn("mn3 DIRTY·1", joined)

    def test_error_lane_renders_question_mark(self):
        lines = fleet.format_lane_strip([{"name": "mn9", "error": True}], 120)
        self.assertIn("mn9 ?", " ".join(lines))

    def test_narrow_width_wraps_not_overflows(self):
        lanes = [{"name": "mn%d" % i, "branch": "main", "dirty": False, "worktrees": i} for i in range(1, 6)]
        for line in fleet.format_lane_strip(lanes, 40):
            self.assertLessEqual(len(line), 40)


class FormatAge(unittest.TestCase):
    def test_boundaries(self):
        now = time.time()
        self.assertTrue(fleet.format_age((now - 59) * 1000).endswith("s"))
        self.assertTrue(fleet.format_age((now - 61) * 1000).endswith("m"))
        self.assertTrue(fleet.format_age((now - 3601) * 1000).endswith("h"))
        self.assertTrue(fleet.format_age((now - 90000) * 1000).endswith("d"))

    def test_garbage_is_question_mark(self):
        self.assertEqual(fleet.format_age(None), "?")
        self.assertEqual(fleet.format_age("banana"), "?")


class StaleNoteNeverOnLiveRows(unittest.TestCase):
    def test_working_row_ignores_sidecar_note(self):
        sessions = [{"sessionId": "x" * 36, "id": "xxxxxxxx", "name": "n", "state": "working", "cwd": "/e", "startedAt": 1}]
        sidecars = {"x" * 36: ("complete", "t", "old note PR #9")}
        model = fleet.build_model(sessions, sidecars, set(), [])
        row = model["groups"][0][1][0]
        self.assertEqual(row["context"], "")
        self.assertIsNone(row.get("pr"))

    def test_blocked_row_keeps_live_status(self):
        sessions = [{"sessionId": "y" * 36, "id": "yyyyyyyy", "name": "n", "state": "blocked", "status": "waiting on input", "cwd": "/e", "startedAt": 1}]
        sidecars = {"y" * 36: ("complete", "t", "old note PR #9")}
        model = fleet.build_model(sessions, sidecars, set(), [])
        row = model["groups"][0][1][0]
        self.assertEqual(row["context"], "waiting on input")
        self.assertIsNone(row.get("pr"))

    def test_complete_row_still_uses_sidecar_note(self):
        sessions = [{"sessionId": "z" * 36, "id": "zzzzzzzz", "name": "n", "state": "done", "cwd": "/e", "startedAt": 1}]
        sidecars = {"z" * 36: ("complete", "t", "shipped PR #9")}
        model = fleet.build_model(sessions, sidecars, set(), [])
        row = model["groups"][0][1][0]
        self.assertEqual(row["context"], "shipped PR #9")
        self.assertEqual(row["pr"], "#9")


class ContextFlattening(unittest.TestCase):
    def test_newlines_flattened(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "1m", "context": "a\nb\tc", "starred": False, "bucket": "WORKING"}
        lines = fleet.format_row(row, 120, False)
        self.assertIn("a b c", lines[1])

    def test_carriage_return_flattened(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "1m", "context": "a\r\nb", "starred": False, "bucket": "WORKING"}
        lines = fleet.format_row(row, 120, False)
        self.assertIn("a  b", lines[1])
        self.assertNotIn("\n", lines[1])


class WorktreeParts(unittest.TestCase):
    def test_dot_worktrees_shape(self):
        self.assertEqual(
            fleet.worktree_parts("/e/mn3/.worktrees/task-3"),
            ("/e/mn3", "/e/mn3/.worktrees/task-3", "task-3"),
        )

    def test_claude_worktrees_shape(self):
        self.assertEqual(
            fleet.worktree_parts("/e/mn1/.claude/worktrees/task-3"),
            ("/e/mn1", "/e/mn1/.claude/worktrees/task-3", "task-3"),
        )

    def test_nested_containers_last_one_wins(self):
        self.assertEqual(
            fleet.worktree_parts("/e/mn1/.worktrees/outer/.claude/worktrees/inner"),
            ("/e/mn1/.worktrees/outer", "/e/mn1/.worktrees/outer/.claude/worktrees/inner", "inner"),
        )

    def test_nested_same_container_last_one_wins(self):
        self.assertEqual(
            fleet.worktree_parts("/e/mn1/.worktrees/outer/.worktrees/inner"),
            ("/e/mn1/.worktrees/outer", "/e/mn1/.worktrees/outer/.worktrees/inner", "inner"),
        )

    def test_deeper_cwd_inside_worktree_keeps_worktree_root(self):
        self.assertEqual(
            fleet.worktree_parts("/e/mn3/.worktrees/task-3/app/models"),
            ("/e/mn3", "/e/mn3/.worktrees/task-3", "task-3"),
        )

    def test_no_container_is_none(self):
        self.assertIsNone(fleet.worktree_parts("/e/mn3/app/models"))

    def test_container_without_name_is_none(self):
        self.assertIsNone(fleet.worktree_parts("/e/mn3/.worktrees"))
        self.assertIsNone(fleet.worktree_parts("/e/mn1/.claude/worktrees"))

    def test_container_at_root_is_none(self):
        self.assertIsNone(fleet.worktree_parts(".worktrees/task-3"))

    def test_empty_cwd_is_none(self):
        self.assertIsNone(fleet.worktree_parts(""))
        self.assertIsNone(fleet.worktree_parts(None))


class WorktreeHint(unittest.TestCase):
    def setUp(self):
        self._real_run_out = fleet.run_out
        self.calls = []

    def tearDown(self):
        fleet.run_out = self._real_run_out

    def _stub(self, rc, text):
        def fake(args, timeout=10):
            self.calls.append(args)
            return rc, text

        fleet.run_out = fake

    def test_uses_real_branch_not_directory_name(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mn3", ".worktrees", "task-3")
            os.makedirs(path)
            self._stub(0, "jjholmes927-real-branch-INT-1\n")
            hint = fleet.worktree_hint(path)
        self.assertIn("branch -D jjholmes927-real-branch-INT-1", hint)
        self.assertNotIn("branch -D task-3", hint)
        self.assertEqual(self.calls[0][:4], ["git", "-C", path, "rev-parse"])

    def test_detached_head_omits_branch_delete(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mn3", ".worktrees", "task-3")
            os.makedirs(path)
            self._stub(0, "HEAD\n")
            hint = fleet.worktree_hint(path)
        self.assertIn("worktree remove", hint)
        self.assertNotIn("branch -D", hint)

    def test_empty_branch_omits_branch_delete(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mn3", ".worktrees", "task-3")
            os.makedirs(path)
            self._stub(0, "\n")
            hint = fleet.worktree_hint(path)
        self.assertIn("worktree remove", hint)
        self.assertNotIn("branch -D", hint)

    def test_not_a_git_worktree_has_no_git_commands(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mn3", ".worktrees", "task-3")
            os.makedirs(path)
            self._stub(128, "fatal: not a git repository\n")
            hint = fleet.worktree_hint(path)
        self.assertEqual(hint, "worktree dir left behind: %s" % path)
        self.assertNotIn("git ", hint)

    def test_space_in_path_is_quoted(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "my lane")
            path = os.path.join(root, ".worktrees", "task 3")
            os.makedirs(path)
            self._stub(0, "feature branch\n")
            hint = fleet.worktree_hint(path)
        self.assertIn("'%s'" % root, hint)
        self.assertIn("'%s'" % path, hint)
        self.assertIn("'feature branch'", hint)

    def test_claude_worktrees_root_is_above_dot_claude(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "mn1")
            path = os.path.join(root, ".claude", "worktrees", "task-3")
            os.makedirs(path)
            self._stub(0, "some-branch\n")
            hint = fleet.worktree_hint(path)
        self.assertIn("git -C %s worktree remove %s" % (root, path), hint)

    def test_no_container_no_hint(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mn3", "app")
            os.makedirs(path)
            self._stub(0, "main\n")
            self.assertEqual(fleet.worktree_hint(path), "")
        self.assertEqual(self.calls, [])

    def test_missing_directory_no_hint(self):
        self._stub(0, "main\n")
        self.assertEqual(fleet.worktree_hint("/nonexistent/mn3/.worktrees/task-3"), "")
        self.assertEqual(self.calls, [])


class RemoveSession(unittest.TestCase):
    def setUp(self):
        self._real_run_out = fleet.run_out
        self._real_hint = fleet.worktree_hint

    def tearDown(self):
        fleet.run_out = self._real_run_out
        fleet.worktree_hint = self._real_hint

    def test_hint_keeps_the_removed_confirmation(self):
        fleet.run_out = lambda args, timeout=10: (0, "")
        fleet.worktree_hint = lambda cwd: "worktree not reaped: git -C a worktree remove b"
        message = fleet.remove_session({"short": "abc12345", "cwd": "/e/mn3/.worktrees/x"})
        self.assertTrue(message.startswith("removed abc12345 · "))
        self.assertIn("worktree not reaped", message)

    def test_no_hint_is_plain_removed(self):
        fleet.run_out = lambda args, timeout=10: (0, "")
        fleet.worktree_hint = lambda cwd: ""
        self.assertEqual(fleet.remove_session({"short": "abc12345", "cwd": "/e"}), "removed abc12345")


if __name__ == "__main__":
    unittest.main()
