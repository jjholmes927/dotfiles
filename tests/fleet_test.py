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

    def test_row_opens_with_the_state_dot(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "2h", "context": "c", "starred": False, "bucket": "WORKING"}
        self.assertTrue(fleet.format_row(row, 120, False)[0].startswith("● aaaaaaaa"))

    def test_star_replaces_the_dot_and_keeps_the_width(self):
        plain = {"short": "aaaaaaaa", "name": "n", "age": "2h", "context": "c", "starred": False, "bucket": "WORKING"}
        starred = dict(plain, starred=True)
        first = fleet.format_row(plain, 120, False)[0]
        second = fleet.format_row(starred, 120, False)[0]
        self.assertTrue(second.startswith("★ aaaaaaaa"))
        self.assertNotIn("●", second)
        self.assertEqual(len(first), len(second))

    def test_parts_line_up_with_the_rendered_line(self):
        row = {"short": "aaaaaaaa", "name": "mn3/thing", "age": "12m", "context": "c", "starred": False, "bucket": "BLOCKED", "pr": "#9403"}
        parts, text = fleet.row_parts(row, 120)
        self.assertEqual([role for _column, _chunk, role in parts], ["glyph", "short", "name", "age", "badge"])
        for column, chunk, _role in parts:
            self.assertEqual(text[column : column + len(chunk)], chunk)


class MarkdownNoise(unittest.TestCase):
    def test_context_line_drops_bold_markers_and_backticks(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "1m", "starred": False, "bucket": "WORKING",
               "context": "**Done** — ran `pytest` and it passed"}
        line = fleet.format_row(row, 120, False)[1]
        self.assertNotIn("**", line)
        self.assertNotIn("`", line)
        self.assertIn("Done — ran pytest and it passed", line)

    def test_sanitize_context_drops_markdown_too(self):
        self.assertEqual(fleet.sanitize_context("**Plan**: run `make`"), "Plan: run make")

    def test_single_asterisk_is_left_alone(self):
        self.assertEqual(fleet.sanitize_context("2 * 3 stays"), "2 * 3 stays")


class WideGlyphClipping(unittest.TestCase):
    def test_emoji_context_never_spills_past_the_pane(self):
        row = {"short": "aaaaaaaa", "name": "n", "age": "1m", "starred": False, "bucket": "COMPLETE",
               "context": "🟢 ✅ " + "x" * 400}
        line = fleet.format_row(row, 120, False)[1]
        self.assertLessEqual(fleet.cell_width(line), 120)
        self.assertTrue(line.endswith("…"))

    def test_plain_text_still_clips_by_characters(self):
        self.assertEqual(fleet._clip("abcdef", 4), "abc…")
        self.assertEqual(fleet._clip("abc", 4), "abc")

    def test_row_line_fits_the_pane_with_a_starred_glyph(self):
        row = {"short": "aaaaaaaa", "name": "n" * 300, "age": "1m", "starred": True, "bucket": "WORKING"}
        self.assertLessEqual(fleet.cell_width(fleet.format_row(row, 100, False)[0]), 100)


class ColorSystem(unittest.TestCase):
    def test_every_bucket_has_its_own_colour(self):
        names = [fleet.BUCKET_COLORS[bucket] for bucket in fleet.BUCKET_ORDER]
        self.assertEqual(len(set(names)), len(fleet.BUCKET_ORDER))

    def test_count_segments_columns_match_the_banner_text(self):
        counts = {"BLOCKED": 2, "WORKING": 3, "COMPLETE": 1}
        text = fleet.format_counts(counts, 120)
        for column, chunk, bucket in fleet.count_segments(counts):
            self.assertEqual(text[column : column + len(chunk)], chunk)
            self.assertIn(bucket, chunk)

    def test_header_label_sits_after_the_prefix(self):
        header = fleet.format_group_header("WORKING", 120)
        start = len(fleet.HEADER_PREFIX)
        self.assertEqual(header[start : start + len("WORKING")], "WORKING")

    def test_lane_marks_locate_the_glyphs(self):
        line = fleet.format_lane_strip(
            [{"name": "mn1", "dirty": False, "worktrees": 2}, {"name": "mn3", "dirty": True, "worktrees": 1}], 120
        )[0]
        marks = fleet.lane_marks(line)
        self.assertEqual([(chunk, name) for _column, chunk, name in marks], [("✓", "green"), ("DIRTY", "red")])
        for column, chunk, _name in marks:
            self.assertEqual(line[column : column + len(chunk)], chunk)

    def test_error_lane_mark_is_yellow(self):
        line = fleet.format_lane_strip([{"name": "mn9", "error": True}], 120)[0]
        self.assertEqual([(chunk, name) for _column, chunk, name in fleet.lane_marks(line)], [("?", "yellow")])


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
        self.assertEqual([line[1] for line in lines[:3]], ["spacer", "header", "row"])
        self.assertEqual([line[3] for line in lines if line[1] in ("row", "context")], [0, 0, 1, 1, 2, 2])
        self.assertTrue(all(line[3] == -1 for line in lines if line[1] in ("spacer", "header")))

    def test_a_blank_spacer_sits_between_rows_and_before_the_header(self):
        lines = fleet.body_lines(self._state(3, 0), 120)
        self.assertEqual(lines[0], ("", "spacer", None, -1))
        kinds = [line[1] for line in lines]
        self.assertEqual(
            kinds,
            ["spacer", "header"] + ["row", "context", "spacer"] * 2 + ["row", "context"],
        )
        self.assertTrue(all(not line[0] for line in lines if line[1] == "spacer"))

    def test_two_groups_get_one_spacer_before_each_header(self):
        state = self._state(2, 0)
        first, second = state.rows[0], state.rows[1]
        second["bucket"] = "COMPLETE"
        state.model["groups"] = [("WORKING", [first]), ("COMPLETE", [second])]
        kinds = [line[1] for line in fleet.body_lines(state, 120)]
        self.assertEqual(kinds, ["spacer", "header", "row", "context", "spacer", "header", "row", "context"])

    def test_spacers_never_take_the_selection_and_stay_out_of_the_scroll_spots(self):
        state = self._state(4, 2)
        lines = fleet.body_lines(state, 120)
        spots = [position for position, line in enumerate(lines) if line[3] == state.selected]
        self.assertEqual([lines[spot][1] for spot in spots], ["row", "context"])
        top = fleet.scroll_top(lines, state.selected, 0, 5)
        self.assertGreaterEqual(spots[0], top)
        self.assertLess(spots[-1], top + 5)

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


class ActionMenuItems(unittest.TestCase):
    def _row(self, **extra):
        row = {"short": "abc12345", "name": "mn3/thing", "bucket": "AWAITING", "starred": False}
        row.update(extra)
        return row

    def test_seven_items_in_the_locked_order(self):
        items = fleet.menu_items(self._row())
        self.assertEqual(
            [action for action, _label, _hint in items],
            ["pair", "peek", "complete", "awaiting", "star", "stop", "remove"],
        )
        self.assertEqual(
            [label for _action, label, _hint in items],
            ["pair in", "peek", "mark complete", "mark awaiting", "star", "stop", "remove"],
        )

    def test_every_hint_is_the_direct_key_for_the_same_action(self):
        for action, _label, hint in fleet.menu_items(self._row()):
            if hint == "enter":
                continue
            key = ord(" ") if hint == "space" else ord(hint)
            self.assertEqual(fleet.ACTION_KEYS[key], action)

    def test_enter_hint_belongs_to_the_first_item_only(self):
        items = fleet.menu_items(self._row())
        self.assertEqual(items[0][2], "enter")
        self.assertNotIn("enter", [hint for _action, _label, hint in items[1:]])

    def test_no_direct_key_strays_outside_the_menu(self):
        actions = set(action for action, _label, _hint in fleet.menu_items(self._row()))
        self.assertEqual(set(fleet.ACTION_KEYS.values()) - actions, set())

    def test_blocked_row_offers_peek_plus_answer(self):
        labels = dict((action, label) for action, label, _hint in fleet.menu_items(self._row(bucket="BLOCKED")))
        self.assertEqual(labels["peek"], "peek + answer")

    def test_settled_row_keeps_the_plain_peek_label(self):
        labels = dict((action, label) for action, label, _hint in fleet.menu_items(self._row(bucket="COMPLETE")))
        self.assertEqual(labels["peek"], "peek")

    def test_star_label_flips_when_the_row_is_already_starred(self):
        labels = dict((action, label) for action, label, _hint in fleet.menu_items(self._row(starred=True)))
        self.assertEqual(labels["star"], "unstar")

    def test_unstarred_row_says_star(self):
        labels = dict((action, label) for action, label, _hint in fleet.menu_items(self._row()))
        self.assertEqual(labels["star"], "star")

    def test_missing_row_still_builds_the_full_menu(self):
        self.assertEqual(len(fleet.menu_items(None)), len(fleet.MENU_ACTIONS))


class ActionMenuLines(unittest.TestCase):
    def _lines(self, row=None):
        return fleet.menu_lines(fleet.menu_items(row or {"bucket": "WORKING", "starred": False}))

    def test_lines_are_numbered_from_one(self):
        lines = self._lines()
        self.assertEqual([line.split(".")[0] for line in lines], [str(n) for n in range(1, len(lines) + 1)])

    def test_each_line_carries_its_shortcut_in_brackets(self):
        for line, (_action, _label, hint) in zip(self._lines(), fleet.menu_items({})):
            self.assertTrue(line.endswith("(%s)" % hint))

    def test_hints_line_up_in_one_column(self):
        columns = set(line.index("(") for line in self._lines())
        self.assertEqual(len(columns), 1)

    def test_blocked_label_widens_the_column_without_breaking_it(self):
        lines = self._lines({"bucket": "BLOCKED", "starred": True})
        self.assertIn("peek + answer", lines[1])
        self.assertIn("unstar", lines[4])
        self.assertEqual(len(set(line.index("(") for line in lines)), 1)


class ActionMenuChoice(unittest.TestCase):
    def setUp(self):
        self.items = fleet.menu_items({"bucket": "BLOCKED", "starred": False})

    def test_digits_select_their_row(self):
        for index, (action, _label, _hint) in enumerate(self.items, 1):
            self.assertEqual(fleet.menu_choice(ord(str(index)), self.items), action)

    def test_enter_inside_the_menu_pairs_in(self):
        for key in fleet.ENTER_KEYS:
            self.assertEqual(fleet.menu_choice(key, self.items), "pair")

    def test_digit_past_the_last_item_closes(self):
        self.assertEqual(fleet.menu_choice(ord("8"), self.items), "")
        self.assertEqual(fleet.menu_choice(ord("9"), self.items), "")

    def test_zero_and_any_other_key_close(self):
        for key in (ord("0"), ord("x"), ord("q"), curses_key_down(), -1):
            self.assertEqual(fleet.menu_choice(key, self.items), "")

    def test_digit_maps_to_the_same_action_as_its_direct_key(self):
        for index, (_action, _label, hint) in enumerate(self.items, 1):
            if hint == "enter":
                continue
            key = ord(" ") if hint == "space" else ord(hint)
            self.assertEqual(fleet.menu_choice(ord(str(index)), self.items), fleet.ACTION_KEYS[key])


def curses_key_down():
    return fleet.curses.KEY_DOWN


class StatusNoteDefaults(unittest.TestCase):
    def test_empty_note_falls_back_per_action(self):
        self.assertEqual(fleet.status_note("", "complete"), "marked complete from fleet")
        self.assertEqual(fleet.status_note("", "awaiting"), "marked awaiting from fleet")

    def test_whitespace_only_is_the_same_as_empty(self):
        self.assertEqual(fleet.status_note("   ", "complete"), fleet.status_note("", "complete"))
        self.assertEqual(fleet.status_note("\t ", "awaiting"), "marked awaiting from fleet")

    def test_typed_note_wins_and_is_flattened(self):
        self.assertEqual(fleet.status_note("  manual test PR #7 \n", "complete"), "manual test PR #7")


class MarkStatusCall(unittest.TestCase):
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

    def _row(self):
        return {"short": "abc12345", "session_id": "a" * 36}

    def test_shells_out_to_fleet_status_with_the_full_session_id(self):
        self._stub(0, "fleet-status: complete recorded for abc12345\n")
        message = fleet.mark_status(self._row(), "complete", "manual test PR #7")
        self.assertEqual(self.calls[0][0], "fleet-status")
        self.assertEqual(self.calls[0][self.calls[0].index("--session") + 1], "a" * 36)
        self.assertEqual(self.calls[0][-2:], ["complete", "manual test PR #7"])
        self.assertIn("manual test PR #7", message)
        self.assertIn("abc12345", message)

    def test_awaiting_passes_its_own_verb(self):
        self._stub(0, "")
        fleet.mark_status(self._row(), "awaiting", "needs a decision")
        self.assertIn("awaiting", self.calls[0])

    def test_note_that_looks_like_a_flag_stays_a_note(self):
        self._stub(0, "")
        fleet.mark_status(self._row(), "complete", "--stop was not meant")
        args = self.calls[0]
        self.assertLess(args.index("--"), args.index("--stop was not meant"))

    def test_failure_is_reported_on_the_message_line(self):
        self._stub(127, "no such file or directory: fleet-status")
        message = fleet.mark_status(self._row(), "complete", "note")
        self.assertIn("fleet-status complete failed", message)
        self.assertIn("no such file", message)


class ActionDispatch(unittest.TestCase):
    class Screen(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.log = []
        self.names = (
            "pair_handoff",
            "peek",
            "toggle_star",
            "remodel",
            "refresh_model",
            "read_note",
            "mark_status",
            "confirm",
            "stop_session",
            "remove_session",
        )
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        fleet.pair_handoff = lambda short: self._record("pair", short)
        fleet.peek = lambda screen, row: (self._record("peek", row["short"]), "")
        fleet.toggle_star = lambda path, session_id: self._record("star", session_id)
        fleet.remodel = lambda state: self._record("remodel", "")
        fleet.refresh_model = lambda state, **kwargs: self._record("refresh", "")
        fleet.read_note = lambda screen, prompt: self._record("prompt", prompt) and "typed note"
        fleet.mark_status = lambda row, action, note: self._record("mark", "%s %s" % (action, note))
        fleet.confirm = lambda screen, prompt: self._record("confirm", prompt) and True
        fleet.stop_session = lambda row: self._record("stop", row["short"])
        fleet.remove_session = lambda row: self._record("rm", row["short"])

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def _record(self, kind, detail):
        self.log.append((kind, detail))
        return "%s %s" % (kind, detail)

    def _row(self, **extra):
        row = {"short": "abc12345", "session_id": "a" * 36, "bucket": "AWAITING", "starred": False}
        row.update(extra)
        return row

    def _dispatch(self, action, row=None):
        state = fleet.FleetState()
        fleet.dispatch_action(self.Screen(), state, row or self._row(), action)
        return state

    def test_every_menu_action_reaches_a_handler(self):
        first = {
            "pair": "pair",
            "peek": "peek",
            "complete": "prompt",
            "awaiting": "prompt",
            "star": "star",
            "stop": "confirm",
            "remove": "confirm",
        }
        for action, _label, _hint in fleet.menu_items(self._row()):
            self.log = []
            self._dispatch(action)
            self.assertTrue(self.log, "%s did nothing" % action)
            self.assertEqual(self.log[0][0], first[action])

    def test_marking_prompts_then_records_then_remodels(self):
        state = self._dispatch("complete")
        self.assertEqual([kind for kind, _detail in self.log], ["prompt", "mark", "remodel"])
        self.assertEqual(self.log[1][1], "complete typed note")
        self.assertEqual(state.message, "mark complete typed note")

    def test_the_note_prompt_names_the_action_and_the_row(self):
        self._dispatch("awaiting")
        self.assertIn("awaiting", self.log[0][1])
        self.assertIn("abc12345", self.log[0][1])

    def test_an_empty_note_becomes_the_default(self):
        fleet.read_note = lambda screen, prompt: ""
        self._dispatch("complete")
        self.assertEqual(self.log[0], ("mark", "complete marked complete from fleet"))

    def test_an_escaped_note_marks_nothing(self):
        fleet.read_note = lambda screen, prompt: self._record("prompt", prompt) and None
        state = self._dispatch("complete")
        self.assertEqual([kind for kind, _detail in self.log], ["prompt"])
        self.assertEqual(state.message, fleet.NOTE_CANCELLED)

    def test_star_re_models_without_touching_the_cli(self):
        self._dispatch("star")
        self.assertEqual([kind for kind, _detail in self.log], ["star", "remodel"])

    def test_a_declined_confirm_stops_at_the_prompt(self):
        fleet.confirm = lambda screen, prompt: self._record("confirm", prompt) and False
        state = self._dispatch("stop")
        self.assertEqual([kind for kind, _detail in self.log], ["confirm"])
        self.assertEqual(state.message, "")

    def test_remove_refreshes_after_a_confirmed_rm(self):
        state = self._dispatch("remove")
        self.assertEqual([kind for kind, _detail in self.log], ["confirm", "rm", "refresh"])
        self.assertEqual(state.message, "rm abc12345")

    def test_peek_handing_off_to_pair_still_pairs(self):
        fleet.peek = lambda screen, row: (self._record("peek", row["short"]), "pair")
        state = self._dispatch("peek")
        self.assertEqual([kind for kind, _detail in self.log], ["peek", "pair"])
        self.assertEqual(state.message, "pair abc12345")

    def test_an_answered_gate_refreshes(self):
        fleet.peek = lambda screen, row: (self._record("peek", row["short"]), "refresh")
        self._dispatch("peek")
        self.assertEqual([kind for kind, _detail in self.log], ["peek", "refresh"])

    def test_direct_keys_and_menu_digits_land_on_the_same_handler(self):
        items = fleet.menu_items(self._row())
        for index, (action, _label, hint) in enumerate(items, 1):
            if hint == "enter":
                continue
            key = ord(" ") if hint == "space" else ord(hint)
            self.log = []
            self._dispatch(fleet.ACTION_KEYS[key])
            direct = list(self.log)
            self.log = []
            self._dispatch(fleet.menu_choice(ord(str(index)), items))
            self.assertEqual(direct, self.log, "%s took two different routes" % action)


class EscapedNoteNeverReachesFleetStatus(unittest.TestCase):
    class Screen(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.calls = []
        self.names = ("run_out", "read_note", "remodel")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        fleet.run_out = self._fake_run_out
        fleet.remodel = lambda state: None

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def _fake_run_out(self, args, timeout=10):
        self.calls.append(args)
        return 0, ""

    def _dispatch(self, note, action="complete"):
        fleet.read_note = lambda screen, prompt: note
        state = fleet.FleetState()
        row = {"short": "abc12345", "session_id": "a" * 36, "bucket": "AWAITING", "starred": False}
        fleet.dispatch_action(self.Screen(), state, row, action)
        return state

    def test_escape_shells_out_to_nothing_at_all(self):
        state = self._dispatch(None)
        self.assertEqual(self.calls, [])
        self.assertEqual(state.message, "cancelled")

    def test_escaped_awaiting_is_just_as_inert(self):
        self._dispatch(None, "awaiting")
        self.assertEqual(self.calls, [])

    def test_empty_enter_still_writes_the_default_note(self):
        state = self._dispatch("")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], "fleet-status")
        self.assertEqual(self.calls[0][-2:], ["complete", "marked complete from fleet"])
        self.assertIn("marked complete from fleet", state.message)


class OpenMenu(unittest.TestCase):
    class Screen(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self._saved = (fleet.overlay, fleet.dispatch_action)
        self.dispatched = []
        fleet.dispatch_action = lambda screen, state, row, action: self.dispatched.append(action)

    def tearDown(self):
        fleet.overlay, fleet.dispatch_action = self._saved

    def _row(self):
        return {"short": "abc12345", "name": "mn3/thing", "bucket": "BLOCKED", "starred": False}

    def test_the_overlay_is_titled_with_the_row_and_lists_every_item(self):
        seen = {}

        def fake(screen, title, lines, footer, fit=False):
            seen.update(title=title, lines=lines, footer=footer, fit=fit)
            return ord("3")

        fleet.overlay = fake
        fleet.open_menu(self.Screen(), fleet.FleetState(), self._row())
        self.assertIn("mn3/thing", seen["title"])
        self.assertIn("abc12345", seen["title"])
        self.assertEqual(len(seen["lines"]), len(fleet.MENU_ACTIONS))
        self.assertIn("1-7", seen["footer"])
        self.assertTrue(seen["fit"])
        self.assertEqual(self.dispatched, ["complete"])

    def test_enter_inside_the_menu_pairs_in(self):
        fleet.overlay = lambda screen, title, lines, footer, fit=False: 10
        fleet.open_menu(self.Screen(), fleet.FleetState(), self._row())
        self.assertEqual(self.dispatched, ["pair"])

    def test_any_other_key_closes_without_acting(self):
        fleet.overlay = lambda screen, title, lines, footer, fit=False: ord("z")
        state = fleet.FleetState()
        fleet.open_menu(self.Screen(), state, self._row())
        self.assertEqual(self.dispatched, [])
        self.assertEqual(state.message, "")

    def test_a_window_too_small_for_the_overlay_says_so(self):
        fleet.overlay = lambda screen, title, lines, footer, fit=False: -1
        state = fleet.FleetState()
        fleet.open_menu(self.Screen(), state, self._row())
        self.assertEqual(self.dispatched, [])
        self.assertEqual(state.message, fleet.MENU_TOO_SMALL)


class OverlayFit(unittest.TestCase):
    class Fake(object):
        def getmaxyx(self):
            return 50, 200

        def getch(self):
            return ord("x")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self._saved = (fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate)
        self.boxes = []
        fleet.curses.newwin = lambda *args: self.boxes.append(args) or self.Fake()
        fleet.curses.flushinp = lambda: None
        fleet.curses.doupdate = lambda: None

    def tearDown(self):
        fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate = self._saved

    def _menu(self):
        items = fleet.menu_items({"bucket": "WORKING", "starred": False})
        return fleet.menu_lines(items), fleet.MENU_FOOTER % len(items)

    def test_a_fitted_box_hugs_the_menu_instead_of_the_pane(self):
        lines, footer = self._menu()
        fleet.overlay(self.Fake(), "abc12345 mn3/thing", lines, footer, fit=True)
        box_height, box_width = self.boxes[0][0], self.boxes[0][1]
        self.assertEqual(box_height, len(lines) + 2)
        self.assertLess(box_width, int(200 * fleet.PEEK_RATIO))
        for line in lines + [footer, "abc12345 mn3/thing"]:
            self.assertLessEqual(fleet.cell_width(line) + fleet.BOX_PADDING, box_width)

    def test_a_fitted_box_stays_centred(self):
        lines, footer = self._menu()
        fleet.overlay(self.Fake(), "t", lines, footer, fit=True)
        box_height, box_width, top, left = self.boxes[0]
        self.assertEqual(top, (50 - box_height) // 2)
        self.assertEqual(left, (200 - box_width) // 2)

    def test_peek_keeps_the_big_box(self):
        fleet.overlay(self.Fake(), "t", ["one line"], "any key close")
        self.assertEqual(self.boxes[0][:2], (int(50 * fleet.PEEK_RATIO), int(200 * fleet.PEEK_RATIO)))

    def test_a_fitted_box_never_drops_below_the_minimums(self):
        fleet.overlay(self.Fake(), "t", ["a"], "f", fit=True)
        self.assertGreaterEqual(self.boxes[0][0], fleet.PEEK_MIN_HEIGHT)
        self.assertGreaterEqual(self.boxes[0][1], fleet.PEEK_MIN_WIDTH)

    def test_a_fitted_box_never_outgrows_the_pane(self):
        fleet.overlay(self.Fake(), "t" * 400, ["x" * 400] * 80, "f", fit=True)
        self.assertEqual(self.boxes[0][:2], (int(50 * fleet.PEEK_RATIO), int(200 * fleet.PEEK_RATIO)))


class ReadNote(unittest.TestCase):
    class Screen(object):
        def __init__(self, keys):
            self.keys = list(keys)
            self.timeouts = []

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            return self.keys.pop(0)

        def timeout(self, value):
            self.timeouts.append(value)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self._saved = (fleet.curses.flushinp, fleet.curses.doupdate, fleet.curses.curs_set)
        fleet.curses.flushinp = lambda: None
        fleet.curses.doupdate = lambda: None
        fleet.curses.curs_set = lambda value: None

    def tearDown(self):
        fleet.curses.flushinp, fleet.curses.doupdate, fleet.curses.curs_set = self._saved

    def _read(self, keys):
        screen = self.Screen(keys)
        return fleet.read_note(screen, "complete note for abc12345: "), screen

    def test_typed_text_comes_back_on_enter(self):
        text, screen = self._read([ord(c) for c in "PR #7"] + [10])
        self.assertEqual(text, "PR #7")
        self.assertEqual(screen.timeouts, [-1, fleet.POLL_MS])

    def test_escape_cancels_instead_of_yielding_a_note(self):
        text, screen = self._read([ord("a"), ord("b"), 27])
        self.assertIsNone(text)
        self.assertEqual(screen.timeouts, [-1, fleet.POLL_MS])

    def test_enter_on_an_empty_note_yields_the_empty_string(self):
        text, _screen = self._read([10])
        self.assertEqual(text, "")
        self.assertEqual(fleet.status_note(text, "awaiting"), "marked awaiting from fleet")

    def test_backspace_erases_the_last_character(self):
        text, _screen = self._read([ord("a"), ord("b"), 127, ord("c"), 10])
        self.assertEqual(text, "ac")

    def test_backspace_on_an_empty_note_is_harmless(self):
        text, _screen = self._read([curses_backspace(), 10])
        self.assertEqual(text, "")

    def test_a_very_long_note_is_capped(self):
        text, _screen = self._read([ord("x")] * (fleet.NOTE_LIMIT + 40) + [10])
        self.assertEqual(len(text), fleet.NOTE_LIMIT)

    def test_arrow_keys_are_ignored(self):
        text, _screen = self._read([fleet.curses.KEY_DOWN, ord("o"), fleet.curses.KEY_UP, ord("k"), 10])
        self.assertEqual(text, "ok")

    def test_utf8_bytes_are_reassembled(self):
        text, _screen = self._read(list("é".encode("utf-8")) + [10])
        self.assertEqual(text, "é")


def curses_backspace():
    return fleet.curses.KEY_BACKSPACE


class Footer(unittest.TestCase):
    def test_footer_advertises_the_menu_and_the_survivors(self):
        self.assertEqual(fleet.FOOTER, "[enter]actions [space]peek [j/k]move [q]quit")

    def test_footer_no_longer_lists_the_keys_the_menu_teaches(self):
        for hint in ("[p]star", "[s]stop", "[r]rm", "[enter]pair"):
            self.assertNotIn(hint, fleet.FOOTER)


if __name__ == "__main__":
    unittest.main()
