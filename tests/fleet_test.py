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


class ConfirmFlushesTypeahead(unittest.TestCase):
    class Fake(object):
        def __init__(self, log):
            self.log = log

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            self.log.append("getch")
            return ord("y")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def test_flushinp_runs_before_the_blocking_read(self):
        log = []
        saved = (fleet.curses.flushinp, fleet.curses.doupdate)
        try:
            fleet.curses.flushinp = lambda: log.append("flushinp")
            fleet.curses.doupdate = lambda: None
            answered = fleet.confirm(self.Fake(log), "rm abc12345?")
        finally:
            fleet.curses.flushinp, fleet.curses.doupdate = saved
        self.assertTrue(answered)
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

    def test_empty_window_id_warns_a_hidden_window_may_be_live(self):
        def fake(args, timeout=10):
            self.calls.append(args)
            return 0, ""

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

    def test_noise_on_stdout_is_not_taken_for_a_window_id(self):
        def fake(args, timeout=10):
            self.calls.append(args)
            return 0, "can't find pane @42"

        fleet.run_out = fake
        message, action = fleet.gate_answer(None, {"short": "abc12345"}, "abc12345")
        self.assertIn("hidden attach window for abc12345 may be live", message)
        self.assertEqual(action, "")
        self.assertEqual(len(self.calls), 1)


class GateAnswerValidWindowId(unittest.TestCase):
    class Fake(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self._saved = (fleet.run_out, fleet.overlay, fleet.ATTACH_WAIT, fleet.curses.doupdate)
        fleet.ATTACH_WAIT = 0
        fleet.curses.doupdate = lambda: None
        fleet.overlay = lambda screen, title, lines, footer: ord("x")
        self.calls = []

    def tearDown(self):
        fleet.run_out, fleet.overlay, fleet.ATTACH_WAIT, fleet.curses.doupdate = self._saved

    def test_real_window_id_captures_then_kills_that_window(self):
        def fake(args, timeout=10):
            self.calls.append(args)
            if args[1] == "new-window":
                return 0, "@42\n"
            return 0, "some pane text"

        fleet.run_out = fake
        message, action = fleet.gate_answer(self.Fake(), {"short": "abc12345"}, "abc12345")
        self.assertEqual((message, action), ("", ""))
        self.assertIn(["tmux", "capture-pane", "-t", "@42", "-p"], self.calls)
        self.assertEqual(self.calls[-1], ["tmux", "kill-window", "-t", "@42"])


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


class StatusFieldsStayUntangled(unittest.TestCase):
    def _session(self, **extra):
        session = {"sessionId": "k" * 36, "id": "kkkkkkkk", "name": "n", "cwd": "/e", "startedAt": 1}
        session.update(extra)
        return session

    def _row(self, session):
        return fleet.build_model([session], {}, set(), [])["groups"][0][1][0]

    def test_context_text_drives_display_while_status_drives_bucketing(self):
        row = self._row(
            self._session(state="blocked", status="idle", context_text="Recorded the status; ready for review.")
        )
        self.assertEqual(row["bucket"], "AWAITING")
        self.assertEqual(row["context"], "Recorded the status; ready for review.")

    def test_missing_context_text_falls_back_to_status(self):
        row = self._row(self._session(state="working", status="running"))
        self.assertEqual(row["bucket"], "WORKING")
        self.assertEqual(row["context"], "running")

    def test_cli_status_still_wins_for_bucketing_when_present(self):
        row = self._row(
            self._session(state="blocked", status="idle", cli_status="waiting", context_text="Which option?")
        )
        self.assertEqual(row["bucket"], "BLOCKED")
        self.assertEqual(row["context"], "Which option?")


class TranscriptTail(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._saved = fleet.PROJECTS_DIR
        fleet.PROJECTS_DIR = os.path.join(self._temp.name, "projects")

    def tearDown(self):
        fleet.PROJECTS_DIR = self._saved
        self._temp.cleanup()

    def _write(self, session_id, entries):
        path = fleet.transcript_path("/e/mn3", session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def _assistant(self, text):
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}

    def test_newlines_survive_for_the_peek_overlay(self):
        session_id = "m" * 36
        self._write(session_id, [self._assistant("Plan:\n- one\n- two")])
        lines = fleet.capture_lines(fleet.transcript_tail("/e/mn3", session_id))
        self.assertEqual(lines, ["Plan:", "- one", "- two"])

    def test_last_assistant_entry_wins_over_later_user_entries(self):
        session_id = "n" * 36
        self._write(
            session_id,
            [self._assistant("older"), self._assistant("newer"), {"type": "user", "message": {"content": "hi"}}],
        )
        self.assertEqual(fleet.transcript_tail("/e/mn3", session_id), "newer")

    def test_missing_transcript_is_empty(self):
        self.assertEqual(fleet.transcript_tail("/e/mn3", "z" * 36), "")


class HasQuestion(unittest.TestCase):
    def test_menu_capture_is_answerable(self):
        lines = ["Do you want to proceed?", "", "❯ 1. Yes, apply the fix", "  2. No, keep looking"]
        self.assertTrue(fleet.has_question(lines))

    def test_boxed_menu_is_answerable(self):
        lines = ["╭──────────────╮", "│ Pick a plan  │", "│ 1. Ship it   │", "│ 2. Revise    │", "╰──────────────╯"]
        self.assertTrue(fleet.has_question(lines))

    def test_prose_without_a_numbered_line_is_not(self):
        lines = ["I refactored the parser and ran the suite.", "Everything is green — over to you."]
        self.assertFalse(fleet.has_question(lines))


class BellCheck(unittest.TestCase):
    def _state(self, pairs):
        state = fleet.FleetState()
        state.rows = [{"session_id": session_id, "bucket": bucket} for session_id, bucket in pairs]
        return state

    def _poll(self, state, pairs):
        state.rows = [{"session_id": session_id, "bucket": bucket} for session_id, bucket in pairs]
        return fleet.bell_check(state)

    def test_first_poll_is_a_silent_baseline(self):
        state = self._state([("a", "BLOCKED"), ("b", "COMPLETE")])
        self.assertFalse(fleet.bell_check(state))

    def test_transition_into_blocked_rings(self):
        state = self._state([("a", "WORKING")])
        fleet.bell_check(state)
        self.assertTrue(self._poll(state, [("a", "BLOCKED")]))

    def test_transition_into_complete_rings(self):
        state = self._state([("a", "WORKING")])
        fleet.bell_check(state)
        self.assertTrue(self._poll(state, [("a", "COMPLETE")]))

    def test_working_to_awaiting_stays_silent(self):
        state = self._state([("a", "WORKING")])
        fleet.bell_check(state)
        self.assertFalse(self._poll(state, [("a", "AWAITING")]))

    def test_sitting_in_blocked_does_not_ring_again(self):
        state = self._state([("a", "WORKING")])
        fleet.bell_check(state)
        self.assertTrue(self._poll(state, [("a", "BLOCKED")]))
        self.assertFalse(self._poll(state, [("a", "BLOCKED")]))


class RestoreSelection(unittest.TestCase):
    def _state(self, ids, selected, selected_id):
        state = fleet.FleetState()
        state.rows = [{"session_id": session_id} for session_id in ids]
        state.selected = selected
        state.selected_id = selected_id
        return state

    def test_selection_follows_the_session_across_a_resort(self):
        state = self._state(["a", "b", "c"], 2, "c")
        state.rows = [{"session_id": session_id} for session_id in ("c", "a", "b")]
        fleet.restore_selection(state)
        self.assertEqual(state.selected, 0)
        self.assertEqual(state.selected_id, "c")

    def test_vanished_session_keeps_the_index_and_adopts_that_row(self):
        state = self._state(["a", "b", "c"], 1, "b")
        state.rows = [{"session_id": session_id} for session_id in ("a", "c", "d")]
        fleet.restore_selection(state)
        self.assertEqual(state.selected, 1)
        self.assertEqual(state.selected_id, "c")

    def test_vanished_session_past_the_end_clamps_to_the_last_row(self):
        state = self._state(["a", "b", "c"], 2, "c")
        state.rows = [{"session_id": "a"}]
        fleet.restore_selection(state)
        self.assertEqual(state.selected, 0)
        self.assertEqual(state.selected_id, "a")

    def test_empty_fleet_resets_the_selection(self):
        state = self._state([], 4, "c")
        state.top = 7
        fleet.restore_selection(state)
        self.assertEqual((state.selected, state.selected_id, state.top), (0, "", 0))


class BodyLinesAndScroll(unittest.TestCase):
    def _state(self, count, selected):
        rows = [
            {
                "session_id": str(index),
                "short": "sess%d" % index,
                "name": "row-%d" % index,
                "age": "1m",
                "context": "context %d" % index,
                "starred": False,
                "bucket": "WORKING",
                "pr": None,
            }
            for index in range(count)
        ]
        state = fleet.FleetState()
        state.rows = rows
        state.selected = selected
        state.model = {"counts": {}, "lanes": [], "groups": [("WORKING", rows)]}
        return state

    def test_header_and_two_lines_per_row_with_only_rows_indexed(self):
        lines = fleet.body_lines(self._state(3, 0), 120)
        self.assertEqual(len(lines), 1 + 2 * 3)
        self.assertEqual(lines[0][3], -1)
        self.assertEqual([line[3] for line in lines[1:]], [0, 0, 1, 1, 2, 2])

    def test_selected_row_is_fully_visible_at_a_small_height(self):
        state = self._state(12, 9)
        lines = fleet.body_lines(state, 120)
        height = 6
        top = fleet.scroll_top(lines, state.selected, 0, height)
        spots = [position for position, line in enumerate(lines) if line[3] == state.selected]
        self.assertGreaterEqual(spots[0], top)
        self.assertLess(spots[-1], top + height)

    def test_scrolling_back_up_pulls_the_window_to_the_selection(self):
        state = self._state(12, 0)
        lines = fleet.body_lines(state, 120)
        top = fleet.scroll_top(lines, 0, 15, 6)
        spots = [position for position, line in enumerate(lines) if line[3] == 0]
        self.assertEqual(top, spots[0])
        self.assertLess(spots[-1], top + 6)

    def test_boundary_heights_never_go_negative_or_past_the_end(self):
        state = self._state(8, 0)
        lines = fleet.body_lines(state, 120)
        for height in (0, 1, 2, len(lines) - 1, len(lines), len(lines) + 5):
            for selected in (0, 3, 7):
                for start in (0, 99):
                    top = fleet.scroll_top(lines, selected, start, height)
                    self.assertGreaterEqual(top, 0)
                    if height <= 0:
                        self.assertEqual(top, 0)
                    else:
                        self.assertLessEqual(top, max(0, len(lines) - height))

    def test_taller_than_the_body_pins_to_the_top(self):
        state = self._state(2, 1)
        lines = fleet.body_lines(state, 120)
        self.assertEqual(fleet.scroll_top(lines, 1, 0, len(lines) + 4), 0)

    def test_empty_body_has_no_offset(self):
        self.assertEqual(fleet.scroll_top([], 0, 3, 10), 0)


if __name__ == "__main__":
    unittest.main()
