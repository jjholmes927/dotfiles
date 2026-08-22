import importlib.util, importlib.machinery, json, os, pathlib, tempfile, threading, time, unittest

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
        state.sessions = fleet.enrich_sessions([session], {})
        fleet.remodel(state)
        return fleet.model_rows(state.model)[0]

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
        self.assertTrue(fleet.format_row(row, 120, False)[0].startswith(" ● aaaaaaaa"))

    def test_star_replaces_the_dot_and_keeps_the_width(self):
        plain = {"short": "aaaaaaaa", "name": "n", "age": "2h", "context": "c", "starred": False, "bucket": "WORKING"}
        starred = dict(plain, starred=True)
        first = fleet.format_row(plain, 120, False)[0]
        second = fleet.format_row(starred, 120, False)[0]
        self.assertTrue(second.startswith(" ★ aaaaaaaa"))
        self.assertNotIn("●", second)
        self.assertEqual(len(first), len(second))

    def test_parts_line_up_with_the_rendered_line(self):
        row = {"short": "aaaaaaaa", "name": "mn3/thing", "age": "12m", "context": "c", "starred": False, "bucket": "BLOCKED", "pr": "#9403"}
        parts, text = fleet.row_parts(row, 120)
        self.assertEqual([role for _column, _chunk, role in parts], ["glyph", "short", "name", "age", "badge"])
        for column, chunk, _role in parts:
            self.assertEqual(text[column : column + len(chunk)], chunk)


class SelectionBar(unittest.TestCase):
    def _row(self, **extra):
        row = {"short": "aaaaaaaa", "name": "mn3/thing", "age": "12m", "context": "some ctx",
               "starred": False, "bucket": "WORKING", "pr": None}
        row.update(extra)
        return row

    def _state(self):
        state = fleet.FleetState()
        state.colors = {"cyan": 4096, "red": 256, "dim": fleet.curses.A_DIM}
        return state

    def test_the_selected_row_carries_the_bar_on_both_lines(self):
        lines = fleet.format_row(self._row(), 120, True)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.startswith(fleet.BAR_GLYPH) for line in lines))

    def test_an_unselected_row_keeps_a_blank_leading_column(self):
        for line in fleet.format_row(self._row(), 120, False):
            self.assertTrue(line.startswith(" "))
            self.assertNotIn(fleet.BAR_GLYPH, line)

    def test_the_bar_costs_exactly_what_the_blank_costs(self):
        selected = fleet.format_row(self._row(), 120, True)
        plain = fleet.format_row(self._row(), 120, False)
        for barred, blank in zip(selected, plain):
            self.assertEqual(fleet.cell_width(barred), fleet.cell_width(blank))

    def test_the_glyph_sits_one_column_in_on_every_row(self):
        for selected in (False, True):
            line = fleet.format_row(self._row(), 120, selected)[0]
            self.assertEqual(line[1], "●")
            self.assertEqual(line[3:11], "aaaaaaaa")

    def test_the_bar_is_the_first_part_at_column_zero(self):
        parts, _text = fleet.row_parts(self._row(), 120, True)
        self.assertEqual(parts[0], (0, fleet.BAR_GLYPH, "bar"))

    def test_an_unselected_row_has_no_bar_part(self):
        parts, _text = fleet.row_parts(self._row(), 120, False)
        self.assertNotIn("bar", [role for _column, _chunk, role in parts])

    def test_parts_still_line_up_with_the_rendered_line_either_way(self):
        for selected in (False, True):
            parts, text = fleet.row_parts(self._row(pr="#9403"), 120, selected)
            for column, chunk, _role in parts:
                self.assertEqual(text[column : column + len(chunk)], chunk)

    def test_the_bar_takes_the_row_state_colour_in_bold(self):
        state = self._state()
        self.assertEqual(fleet.part_attr(state, "bar", self._row()), 4096 | fleet.curses.A_BOLD)
        self.assertEqual(fleet.part_attr(state, "bar", self._row(bucket="BLOCKED")), 256 | fleet.curses.A_BOLD)

    def test_the_selected_name_goes_bold(self):
        state = self._state()
        self.assertTrue(fleet.part_attr(state, "name", self._row(), True) & fleet.curses.A_BOLD)
        self.assertFalse(fleet.part_attr(state, "name", self._row(), False) & fleet.curses.A_BOLD)

    def test_nothing_on_a_selected_row_uses_reverse_video(self):
        state = self._state()
        for kind in ("row", "context"):
            self.assertFalse(fleet.line_attr(state, kind, self._row(), True) & fleet.curses.A_REVERSE)
        for role in ("bar", "glyph", "short", "name", "age", "badge"):
            self.assertFalse(fleet.part_attr(state, role, self._row(), True) & fleet.curses.A_REVERSE)

    def test_the_context_line_stays_dim_under_the_selection(self):
        self.assertTrue(fleet.line_attr(self._state(), "context", self._row(), True) & fleet.curses.A_DIM)

    def test_only_the_selected_row_gets_a_bar_in_the_body(self):
        rows = [self._row(session_id="0", name="first"), self._row(session_id="1", name="second")]
        state = fleet.FleetState()
        state.rows = rows
        state.selected = 1
        state.model = {"counts": {}, "lanes": [], "groups": [("WORKING", rows)]}
        barred = set(index for text, _kind, _payload, index in fleet.body_lines(state, 120) if text.startswith(fleet.BAR_GLYPH))
        self.assertEqual(barred, {1})


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


class MarkdownRendering(unittest.TestCase):
    SAMPLE = "# Title\n\n**Done** — ran `pytest`\n\n- a bullet\n\n> quoted\n\n```sh\nmake test\n```\n\n[docs](https://x/y)"

    def _render(self, text, width=40):
        return fleet.render_markdown(text, width)

    def _texts(self, rendered):
        return [text for text, _spans in rendered]

    def _only(self, text, width=40):
        rendered = self._render(text, width)
        self.assertEqual(len(rendered), 1)
        return rendered[0]

    def test_bold_markers_go_and_the_span_lands_on_the_words(self):
        text, spans = self._only("**Done** — ran it")
        self.assertEqual(text, "Done — ran it")
        self.assertEqual(spans, [(0, 4, "bold")])
        self.assertEqual(text[spans[0][0] : spans[0][0] + spans[0][1]], "Done")

    def test_a_bold_phrase_stays_one_span_across_its_space(self):
        text, spans = self._only("tail **two words** here")
        self.assertEqual(text, "tail two words here")
        self.assertEqual([text[column : column + length] for column, length, _style in spans], ["two words"])

    def test_inline_code_is_cyan_without_the_backticks(self):
        text, spans = self._only("ran `pytest -q` twice")
        self.assertEqual(text, "ran pytest -q twice")
        self.assertEqual(spans, [(4, 9, "code")])
        self.assertEqual(fleet.STYLE_COLORS["code"], "cyan")

    def test_a_mixed_line_keeps_every_span_in_place(self):
        text, spans = self._only("**Ran** `pytest` — see [the docs](https://x/y)")
        self.assertEqual(text, "Ran pytest — see the docs")
        self.assertEqual([style for _column, _length, style in spans], ["bold", "code", "link"])
        self.assertEqual(
            [text[column : column + length] for column, length, _style in spans], ["Ran", "pytest", "the docs"]
        )
        self.assertNotIn("https", text)

    def test_a_link_keeps_the_text_and_drops_the_url(self):
        text, spans = self._only("see [the docs](https://example.com/a/b) now")
        self.assertEqual(text, "see the docs now")
        self.assertEqual(spans, [(4, 8, "link")])

    def test_a_link_nested_in_bold_still_loses_its_url(self):
        text, spans = self._only("**→ Created [INT-842](https://linear.app/a/b)** — assigned")
        self.assertEqual(text, "→ Created INT-842 — assigned")
        self.assertEqual([style for _column, _length, style in spans], ["bold", "link"])
        self.assertEqual([text[column : column + length] for column, length, _style in spans], ["→ Created ", "INT-842"])

    def test_code_inside_a_fence_of_backticks_is_left_verbatim(self):
        self.assertEqual(self._only("`**not bold**`"), ("**not bold**", [(0, 12, "code")]))

    def test_a_header_absorbs_its_inline_markers(self):
        text, spans = self._only("## Head with **bold** and `code`")
        self.assertEqual(text, "Head with bold and code")
        self.assertEqual(spans, [(0, len(text), "header")])

    def test_headers_lose_their_hashes_and_take_the_header_style(self):
        for source in ("# Plan", "## Plan", "### Plan"):
            text, spans = self._only(source)
            self.assertEqual(text, "Plan")
            self.assertEqual(spans, [(0, 4, "header")])
        self.assertEqual(fleet.STYLE_COLORS["header"], "yellow")

    def test_a_fourth_hash_is_not_a_header(self):
        text, spans = self._only("#### too deep")
        self.assertEqual(text, "#### too deep")
        self.assertEqual(spans, [])

    def test_fenced_lines_are_dim_and_verbatim_without_the_fences(self):
        rendered = self._render("before\n```python\ndef f():\n    return  1\n```\nafter")
        self.assertEqual(self._texts(rendered), ["before", "def f():", "    return  1", "after"])
        self.assertEqual(
            [spans for _text, spans in rendered], [[], [(0, 8, "dim")], [(0, 13, "dim")], []]
        )

    def test_markdown_inside_a_fence_is_left_alone(self):
        rendered = self._render("```\n**not bold** and `not code`\n```")
        self.assertEqual(self._texts(rendered), ["**not bold** and `not code`"])
        self.assertEqual(rendered[0][1], [(0, len(rendered[0][0]), "dim")])

    def test_a_long_fenced_line_wraps_keeping_the_indent(self):
        texts = self._texts(self._render("```\n    " + "x" * 60 + "\n```", 20))
        self.assertGreater(len(texts), 1)
        for text in texts:
            self.assertLessEqual(fleet.cell_width(text), 20)
            self.assertTrue(text.startswith("    "))
        self.assertEqual("".join(text[4:] for text in texts), "x" * 60)

    def test_bullets_become_glyphs_with_a_two_space_wrap_indent(self):
        texts = self._texts(self._render("- a bullet long enough to wrap twice over the box", 20))
        self.assertGreater(len(texts), 1)
        self.assertTrue(texts[0].startswith("• "))
        for text in texts[1:]:
            self.assertTrue(text.startswith("  "))
            self.assertFalse(text.startswith("   "))
        self.assertEqual(" ".join(text.strip() for text in texts).replace("• ", ""), "a bullet long enough to wrap twice over the box")

    def test_star_bullets_get_the_same_glyph(self):
        self.assertEqual(self._texts(self._render("* starred item")), ["• starred item"])

    def test_a_bullet_keeps_its_inline_spans_after_the_glyph(self):
        text, spans = self._only("- ran **the** suite")
        self.assertEqual(text, "• ran the suite")
        self.assertEqual([text[column : column + length] for column, length, _style in spans], ["the"])

    def test_quotes_are_dim_behind_a_bar(self):
        text, spans = self._only("> mind the gap")
        self.assertEqual(text, "▏ mind the gap")
        self.assertEqual(spans, [(0, len(text), "quote")])

    def test_blank_lines_survive_as_paragraph_spacing(self):
        self.assertEqual(self._texts(self._render("one\n\n\ntwo")), ["one", "", "", "two"])

    def test_prose_wraps_to_the_overlay_width(self):
        rendered = self._render("word " * 40, 30)
        self.assertGreater(len(rendered), 1)
        for text, _spans in rendered:
            self.assertLessEqual(fleet.cell_width(text), 30)

    def test_wide_characters_never_spill_past_the_width(self):
        rendered = self._render("進捗: " + "日本語のテキスト " * 6, 24)
        for text, _spans in rendered:
            self.assertLessEqual(fleet.cell_width(text), 24)
        self.assertIn("日本語のテキスト", "".join(self._texts(rendered)))

    def test_a_word_longer_than_the_width_is_split_not_dropped(self):
        self.assertEqual("".join(self._texts(self._render("x" * 50, 20))), "x" * 50)

    def test_a_single_asterisk_is_still_left_alone(self):
        self.assertEqual(self._only("2 * 3 stays"), ("2 * 3 stays", []))

    def test_no_marker_survives_onto_the_screen(self):
        joined = "\n".join(self._texts(self._render(self.SAMPLE)))
        self.assertNotIn("**", joined)
        self.assertNotIn("`", joined)
        self.assertNotIn("](", joined)

    def test_ansi_noise_is_stripped_before_the_markdown_is_read(self):
        raw = "\x1b[31m**Done**\x1b[0m — ran `it`"
        text, spans = self._only("\n".join(fleet.capture_lines(raw)))
        self.assertEqual(text, "Done — ran it")
        self.assertNotIn("\x1b", text)
        self.assertEqual([style for _column, _length, style in spans], ["bold", "code"])

    def test_every_span_stays_inside_its_own_line(self):
        for text, spans in self._render(self.SAMPLE, 18):
            for column, length, style in spans:
                self.assertGreaterEqual(column, 0)
                self.assertLessEqual(column + length, len(text))
                self.assertIn(style, fleet.STYLE_ATTRS)

    def test_an_unusable_width_renders_nothing(self):
        self.assertEqual(fleet.render_markdown("**anything**", 0), [])


class MarkdownStyleAttributes(unittest.TestCase):
    def test_each_tag_maps_to_a_visible_attribute(self):
        self.assertTrue(fleet.style_attr("bold") & fleet.curses.A_BOLD)
        self.assertTrue(fleet.style_attr("header") & fleet.curses.A_BOLD)
        self.assertTrue(fleet.style_attr("dim") & fleet.curses.A_DIM)
        self.assertTrue(fleet.style_attr("quote") & fleet.curses.A_DIM)
        self.assertTrue(fleet.style_attr("link") & fleet.curses.A_UNDERLINE)

    def test_an_unknown_tag_is_plain(self):
        self.assertEqual(fleet.style_attr("nope"), fleet.curses.A_NORMAL)

    def test_colour_tags_reuse_the_pairs_the_rows_already_use(self):
        saved = (fleet.curses.has_colors, fleet.curses.color_pair)
        names = [name for name, _color in fleet.COLOR_SLOTS]
        try:
            fleet.curses.has_colors = lambda: True
            fleet.curses.color_pair = lambda slot: slot * 256
            self.assertEqual(fleet.style_attr("code"), (names.index("cyan") + 1) * 256)
            self.assertEqual(fleet.style_attr("header"), fleet.curses.A_BOLD | (names.index("yellow") + 1) * 256)
        finally:
            fleet.curses.has_colors, fleet.curses.color_pair = saved

    def test_a_terminal_without_colour_still_gets_the_plain_attribute(self):
        saved = fleet.curses.has_colors
        try:
            fleet.curses.has_colors = lambda: False
            self.assertEqual(fleet.style_attr("code"), fleet.curses.A_NORMAL)
            self.assertEqual(fleet.style_attr("header"), fleet.curses.A_BOLD)
        finally:
            fleet.curses.has_colors = saved

    def test_a_curses_that_refuses_to_answer_never_raises(self):
        saved = fleet.curses.has_colors

        def boom():
            raise fleet.curses.error("must call initscr() first")

        try:
            fleet.curses.has_colors = boom
            self.assertEqual(fleet.style_attr("code"), fleet.curses.A_NORMAL)
        finally:
            fleet.curses.has_colors = saved


class OverlayMarkdownPainting(unittest.TestCase):
    class Fake(object):
        def __init__(self, painted):
            self.painted = painted

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            return ord("x")

        def addnstr(self, y, x, text, room, attr):
            self.painted.append((y, x, text, attr))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.painted = []
        self._saved = (fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate, fleet.curses.has_colors)
        fleet.curses.newwin = lambda *args: self.Fake(self.painted)
        fleet.curses.flushinp = lambda: None
        fleet.curses.doupdate = lambda: None
        fleet.curses.has_colors = lambda: False

    def tearDown(self):
        fleet.curses.newwin, fleet.curses.flushinp, fleet.curses.doupdate, fleet.curses.has_colors = self._saved

    def _overlay(self, lines, markdown=True):
        fleet.overlay(self.Fake(self.painted), "abc12345 row", lines, "any key close", markdown=markdown)
        return self.painted

    def test_the_plain_line_is_laid_down_before_its_spans(self):
        painted = self._overlay(["ran **the** suite"])
        body = [(x, text, attr) for _y, x, text, attr in painted if "suite" in text or text == "the"]
        self.assertEqual([text for _x, text, _attr in body], ["ran the suite", "the"])
        self.assertEqual(body[0][2], fleet.curses.A_NORMAL)
        self.assertTrue(body[1][2] & fleet.curses.A_BOLD)

    def test_a_span_is_painted_at_its_own_screen_column(self):
        painted = self._overlay(["ran **the** suite"])
        line = [(x, text) for _y, x, text, _attr in painted if text == "ran the suite"][0]
        bold = [(x, text) for _y, x, text, _attr in painted if text == "the"][0]
        self.assertEqual(bold[0] - line[0], line[1].index("the"))

    def test_wide_characters_push_a_span_to_the_right_column(self):
        painted = self._overlay(["日本 **bold**"])
        line = [(x, text) for _y, x, text, _attr in painted if text.startswith("日本")][0]
        bold = [(x, text) for _y, x, text, _attr in painted if text == "bold"][0]
        self.assertEqual(bold[0] - line[0], fleet.cell_width("日本 "))

    def test_a_fenced_body_is_painted_dim(self):
        painted = self._overlay(["```", "make test", "```"])
        attrs = [attr for _y, _x, text, attr in painted if text == "make test"]
        self.assertEqual(len(attrs), 2)
        self.assertTrue(attrs[1] & fleet.curses.A_DIM)

    def test_a_plain_overlay_still_paints_only_the_text(self):
        painted = self._overlay(["ran **the** suite"], markdown=False)
        self.assertIn("ran **the** suite", [text for _y, _x, text, _attr in painted])
        self.assertEqual([text for _y, _x, text, _attr in painted if text == "the"], [])


class PeekRendersMarkdown(unittest.TestCase):
    def setUp(self):
        self._saved = (fleet.overlay, fleet.transcript_tail, dict(os.environ))
        self.seen = {}

        def fake(screen, title, lines, footer, fit=False, markdown=False):
            self.seen.update(title=title, lines=lines, footer=footer, fit=fit, markdown=markdown)
            return ord("x")

        fleet.overlay = fake
        os.environ.pop("TMUX", None)

    def tearDown(self):
        fleet.overlay, fleet.transcript_tail = self._saved[:2]
        os.environ.clear()
        os.environ.update(self._saved[2])

    def _peek(self, text, bucket="COMPLETE"):
        fleet.transcript_tail = lambda cwd, session_id: text
        row = {"bucket": bucket, "short": "abc12345", "name": "n", "cwd": "/e", "session_id": "a" * 36}
        return fleet.peek(None, row)

    def test_the_transcript_peek_asks_for_markdown(self):
        self.assertEqual(self._peek("**Done**"), ("", ""))
        self.assertTrue(self.seen["markdown"])
        self.assertEqual(self.seen["footer"], fleet.PEEK_FOOTER)

    def test_the_markers_and_the_blank_lines_reach_the_renderer_intact(self):
        self._peek("**Done**\n\n- one\n-  two   spaced")
        self.assertEqual(self.seen["lines"], ["**Done**", "", "- one", "-  two   spaced"])

    def test_a_blocked_row_without_tmux_still_renders_markdown(self):
        self._peek("## Question", bucket="BLOCKED")
        self.assertTrue(self.seen["markdown"])
        self.assertEqual(self.seen["footer"], fleet.NO_TMUX_FOOTER)

    def test_an_empty_transcript_falls_back_to_the_placeholder(self):
        self._peek("")
        self.assertEqual(self.seen["lines"], [fleet.EMPTY_PEEK])

    def test_the_gate_capture_is_never_run_through_the_renderer(self):
        captured = {}

        def fake_gate(screen, row, short):
            captured["short"] = short
            return "", ""

        saved = fleet.gate_answer
        try:
            fleet.gate_answer = fake_gate
            os.environ["TMUX"] = "/tmp/sock,1,0"
            self._peek("**Done**", bucket="BLOCKED")
        finally:
            fleet.gate_answer = saved
        self.assertEqual(captured["short"], "abc12345")
        self.assertEqual(self.seen, {})


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
    def _model(self, pairs):
        rows = [{"session_id": session_id, "bucket": bucket} for session_id, bucket in pairs]
        return {"counts": {}, "lanes": [], "groups": [("ALL", rows)]}

    def _state(self, pairs):
        state = fleet.FleetState()
        state.model = self._model(pairs)
        return state

    def _poll(self, state, pairs):
        state.model = self._model(pairs)
        return fleet.bell_check(state)

    def test_a_folded_row_still_rings(self):
        state = self._state([("a", "WORKING")])
        fleet.bell_check(state)
        state.model = {
            "counts": {},
            "lanes": [],
            "groups": [("COMPLETE", [{"session_id": "a", "bucket": "COMPLETE", "age_seconds": fleet.FOLD_AFTER + 60}])],
        }
        fleet.reflow(state)
        self.assertEqual(state.rows, [])
        self.assertTrue(fleet.bell_check(state))

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
            "pair_in",
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
        fleet.pair_in = lambda screen, state, short: self._record("pair", short)
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
        self.assertEqual([kind for kind, _detail in self.log], ["prompt", "mark", "remodel", "refresh"])
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


class PairTargetDecision(unittest.TestCase):
    def test_a_free_pair_window_somewhere_else_takes_the_handoff(self):
        self.assertEqual(fleet.pair_target(["deck", "pair"], "bash", "%1", "%9", True), "handoff")

    def test_no_pair_window_attaches_in_place(self):
        self.assertEqual(fleet.pair_target(["deck"], "", "%1", "", True), "inplace")

    def test_a_busy_pair_window_attaches_in_place(self):
        self.assertEqual(fleet.pair_target(["pair"], "python3", "%1", "%9", True), "inplace")

    def test_fleet_sitting_in_the_pair_window_attaches_in_place(self):
        self.assertEqual(fleet.pair_target(["pair"], "bash", "%9", "%9", True), "inplace")

    def test_no_tmux_at_all_attaches_in_place(self):
        self.assertEqual(fleet.pair_target(["pair"], "bash", "", "%9", False), "inplace")

    def test_every_shell_the_pair_window_may_run_still_hands_off(self):
        for shell in fleet.SHELL_COMMANDS:
            self.assertEqual(fleet.pair_target(["pair"], shell, "%1", "%9", True), "handoff")

    def test_unknown_pane_ids_do_not_block_the_handoff(self):
        self.assertEqual(fleet.pair_target(["pair"], "bash", "", "", True), "handoff")


class PairProbe(unittest.TestCase):
    def setUp(self):
        self._saved = (fleet.run_out, dict(os.environ))
        self.calls = []

    def tearDown(self):
        fleet.run_out = self._saved[0]
        os.environ.clear()
        os.environ.update(self._saved[1])

    def _stub(self, replies):
        def fake(args, timeout=10):
            self.calls.append(args)
            return replies.pop(0)

        fleet.run_out = fake

    def test_outside_tmux_it_shells_out_to_nothing(self):
        os.environ.pop("TMUX", None)
        self._stub([])
        self.assertEqual(fleet.pair_target(*fleet.pair_probe()), "inplace")
        self.assertEqual(self.calls, [])

    def test_one_display_message_carries_both_the_command_and_the_pane(self):
        os.environ["TMUX"] = "/tmp/sock,1,0"
        os.environ["TMUX_PANE"] = "%3"
        self._stub([(0, "deck\npair\n"), (0, "bash %9\n")])
        windows, command, own_pane, pair_pane, has_tmux = fleet.pair_probe()
        self.assertEqual((windows, command, own_pane, pair_pane, has_tmux), (["deck", "pair"], "bash", "%3", "%9", True))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(fleet.pair_target(windows, command, own_pane, pair_pane, has_tmux), "handoff")

    def test_a_missing_pair_window_skips_the_second_call(self):
        os.environ["TMUX"] = "/tmp/sock,1,0"
        os.environ["TMUX_PANE"] = "%3"
        self._stub([(0, "deck\n")])
        self.assertEqual(fleet.pair_target(*fleet.pair_probe()), "inplace")
        self.assertEqual(len(self.calls), 1)

    def test_fleet_running_in_the_pair_window_is_recognised_as_itself(self):
        os.environ["TMUX"] = "/tmp/sock,1,0"
        os.environ["TMUX_PANE"] = "%9"
        self._stub([(0, "pair\n"), (0, "python3 %9\n")])
        self.assertEqual(fleet.pair_target(*fleet.pair_probe()), "inplace")

    def test_a_failed_list_windows_falls_back_to_in_place(self):
        os.environ["TMUX"] = "/tmp/sock,1,0"
        self._stub([(127, "no server running")])
        self.assertEqual(fleet.pair_target(*fleet.pair_probe()), "inplace")


class PairInRouting(unittest.TestCase):
    def setUp(self):
        self.names = ("pair_probe", "pair_target", "pair_handoff", "attach_in_place")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self.log = []
        fleet.pair_probe = lambda: ("facts",)
        fleet.pair_handoff = lambda short: self.log.append(("handoff", short)) or "pair → %s" % short
        fleet.attach_in_place = (
            lambda screen, state, short: self.log.append(("inplace", short)) or "back from %s" % short
        )

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def _pair(self, decision, short="abc12345"):
        fleet.pair_target = lambda *facts: decision
        return fleet.pair_in(None, fleet.FleetState(), short)

    def test_handoff_goes_to_the_pair_window(self):
        self.assertEqual(self._pair("handoff"), "pair → abc12345")
        self.assertEqual(self.log, [("handoff", "abc12345")])

    def test_inplace_attaches_over_the_fleet_screen(self):
        self.assertEqual(self._pair("inplace"), "back from abc12345")
        self.assertEqual(self.log, [("inplace", "abc12345")])

    def test_an_empty_selection_probes_nothing(self):
        fleet.pair_probe = lambda: self.log.append(("probe", "")) or ("facts",)
        self.assertEqual(self._pair("handoff", ""), "nothing selected")
        self.assertEqual(self.log, [])


class AttachInPlace(unittest.TestCase):
    class Screen(object):
        def __init__(self, log):
            self.log = log

        def refresh(self):
            self.log.append("refresh")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.log = []
        self._saved = (
            fleet.subprocess.call,
            fleet.curses.endwin,
            fleet.curses.flushinp,
            fleet.curses.curs_set,
            fleet.refresh_model,
        )
        fleet.curses.endwin = lambda: self.log.append("endwin")
        fleet.curses.flushinp = lambda: None
        fleet.curses.curs_set = lambda value: None
        fleet.refresh_model = lambda state, **kwargs: self.log.append("model")

    def tearDown(self):
        (
            fleet.subprocess.call,
            fleet.curses.endwin,
            fleet.curses.flushinp,
            fleet.curses.curs_set,
            fleet.refresh_model,
        ) = self._saved

    def _attach(self, rc):
        def fake(args):
            self.log.append(("call", tuple(args)))
            return rc

        fleet.subprocess.call = fake
        return fleet.attach_in_place(self.Screen(self.log), fleet.FleetState(), "abc12345")

    def test_the_screen_is_released_before_claude_takes_the_tty(self):
        message = self._attach(0)
        self.assertEqual(self.log[0], "endwin")
        self.assertEqual(self.log[1], ("call", ("claude", "attach", "abc12345")))
        self.assertEqual(message, "back from abc12345")

    def test_the_repaint_and_the_model_refresh_both_follow_the_attach(self):
        self._attach(0)
        self.assertEqual(self.log, ["endwin", ("call", ("claude", "attach", "abc12345")), "refresh", "model"])

    def test_a_failing_attach_still_resumes_and_names_the_code(self):
        message = self._attach(3)
        self.assertIn("abc12345", message)
        self.assertIn("3", message)
        self.assertIn("refresh", self.log)
        self.assertIn("model", self.log)

    def test_a_missing_claude_binary_is_reported_not_raised(self):
        def boom(args):
            raise OSError("no such file or directory: claude")

        fleet.subprocess.call = boom
        message = fleet.attach_in_place(self.Screen(self.log), fleet.FleetState(), "abc12345")
        self.assertIn("127", message)
        self.assertEqual(self.log[-2:], ["refresh", "model"])


class Footer(unittest.TestCase):
    def test_footer_advertises_the_menu_and_the_survivors(self):
        self.assertEqual(fleet.FOOTER, "[enter]actions [space]peek [n]new [j/k]move [q]quit")

    def test_footer_teaches_the_new_stream_key(self):
        self.assertIn("[n]new", fleet.FOOTER)

    def test_footer_no_longer_lists_the_keys_the_menu_teaches(self):
        for hint in ("[p]star", "[s]stop", "[r]rm", "[enter]pair"):
            self.assertNotIn(hint, fleet.FOOTER)


class CtrlC(unittest.TestCase):
    class Sys(object):
        class Tty(object):
            def isatty(self):
                return True

        def __init__(self):
            self.stdout = self.Tty()

    def setUp(self):
        self._saved = (fleet.curses.wrapper, fleet.sys)
        fleet.sys = self.Sys()

    def tearDown(self):
        fleet.curses.wrapper, fleet.sys = self._saved

    def test_ctrl_c_exits_quietly_instead_of_raising(self):
        def interrupt(func, *args):
            raise KeyboardInterrupt

        fleet.curses.wrapper = interrupt
        self.assertEqual(fleet.main(), 0)


class SnapshotHolderSemantics(unittest.TestCase):
    def _snapshot(self, tag):
        return fleet.Snapshot([{"sessionId": tag}], [], 1.0, "")

    def test_an_empty_holder_hands_back_nothing(self):
        self.assertIsNone(fleet.SnapshotHolder().consume())

    def test_a_published_snapshot_is_consumed_exactly_once(self):
        holder = fleet.SnapshotHolder()
        holder.publish(self._snapshot("a"))
        self.assertEqual(holder.consume().sessions[0]["sessionId"], "a")
        self.assertIsNone(holder.consume())

    def test_the_latest_publish_wins_and_the_stale_one_is_dropped(self):
        holder = fleet.SnapshotHolder()
        holder.publish(self._snapshot("old"))
        holder.publish(self._snapshot("new"))
        self.assertEqual(holder.consume().sessions[0]["sessionId"], "new")
        self.assertIsNone(holder.consume())

    def test_a_published_snapshot_cannot_be_rewritten(self):
        snapshot = self._snapshot("a")
        with self.assertRaises(AttributeError):
            snapshot.error = "boom"

    def test_concurrent_publishers_never_lose_the_holder(self):
        holder = fleet.SnapshotHolder()
        threads = [threading.Thread(target=holder.publish, args=(self._snapshot(str(n)),)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertIsNotNone(holder.consume())
        self.assertIsNone(holder.consume())


class ForceRefreshRequest(unittest.TestCase):
    def test_a_plain_request_wakes_the_worker_without_forcing_the_lanes(self):
        worker = fleet.DataWorker()
        fleet.request_refresh(worker)
        self.assertTrue(worker.wake.is_set())
        self.assertFalse(worker.lane_wake.is_set())

    def test_a_lane_request_wakes_both(self):
        worker = fleet.DataWorker()
        fleet.request_refresh(worker, lanes=True)
        self.assertTrue(worker.wake.is_set())
        self.assertTrue(worker.lane_wake.is_set())

    def test_refresh_model_only_asks_the_worker_and_never_fetches(self):
        state = fleet.FleetState()
        state.worker = fleet.DataWorker()
        fleet.refresh_model(state, lanes=True)
        self.assertTrue(state.worker.wake.is_set())
        self.assertTrue(state.worker.lane_wake.is_set())
        self.assertEqual(state.sessions, [])

    def test_a_state_without_a_worker_is_inert(self):
        fleet.refresh_model(fleet.FleetState(), lanes=True)


class ActionsAskForAnImmediateSweep(unittest.TestCase):
    class Screen(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.names = ("confirm", "stop_session", "remove_session", "read_note", "mark_status", "remodel")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self.state = fleet.FleetState()
        self.state.worker = fleet.DataWorker()
        self.when_acted = []
        fleet.confirm = lambda screen, prompt: True
        fleet.remodel = lambda state: None
        fleet.read_note = lambda screen, prompt: "note"
        fleet.stop_session = lambda row: self._acted("stopped")
        fleet.remove_session = lambda row: self._acted("removed")
        fleet.mark_status = lambda row, action, note: self._acted("marked")

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def _acted(self, message):
        self.when_acted.append(self.state.worker.wake.is_set())
        return message

    def _dispatch(self, action):
        row = {"short": "abc12345", "session_id": "a" * 36, "bucket": "AWAITING", "starred": False, "cwd": "/e"}
        fleet.dispatch_action(self.Screen(), self.state, row, action)

    def test_stop_wakes_the_worker_only_after_the_stop_lands(self):
        self._dispatch("stop")
        self.assertEqual(self.when_acted, [False])
        self.assertTrue(self.state.worker.wake.is_set())

    def test_remove_wakes_the_worker_only_after_the_rm_lands(self):
        self._dispatch("remove")
        self.assertEqual(self.when_acted, [False])
        self.assertTrue(self.state.worker.wake.is_set())

    def test_marking_wakes_the_worker_after_recording(self):
        self._dispatch("complete")
        self.assertEqual(self.when_acted, [False])
        self.assertTrue(self.state.worker.wake.is_set())

    def test_a_declined_confirm_leaves_the_worker_alone(self):
        fleet.confirm = lambda screen, prompt: False
        self._dispatch("stop")
        self.assertEqual(self.when_acted, [])
        self.assertFalse(self.state.worker.wake.is_set())


class WorkerCycle(unittest.TestCase):
    def setUp(self):
        self.names = ("fetch_sessions", "lane_status", "lane_roots")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self.worker = fleet.DataWorker()
        self.lane_calls = []
        fleet.lane_roots = lambda sessions: ["/e/mn1"]
        fleet.lane_status = lambda root, timeout=10: self.lane_calls.append(root) or {"name": "mn1", "error": False}
        fleet.fetch_sessions = lambda root, timeout=10: [self._session()]

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def _session(self):
        return {"sessionId": "a" * 36, "id": "aaaaaaaa", "name": "n", "state": "working", "status": "running", "cwd": "/e/mn1", "startedAt": 1}

    def _explode(self, error):
        def boom(*args, **kwargs):
            raise error

        return boom

    def test_a_good_cycle_publishes_enriched_sessions_lanes_and_a_stamp(self):
        snapshot = fleet.worker_cycle(self.worker, now=100.0)
        self.assertEqual(snapshot.error, "")
        self.assertEqual(snapshot.sessions[0]["context_text"], "running")
        self.assertEqual([lane["name"] for lane in snapshot.lanes], ["mn1"])
        self.assertEqual(snapshot.fetched_at, 100.0)
        self.assertIs(self.worker.holder.consume(), snapshot)

    def test_a_failed_fetch_publishes_the_error_and_keeps_the_last_good_sessions(self):
        fleet.worker_cycle(self.worker, now=100.0)
        fleet.fetch_sessions = self._explode(fleet.FleetError("claude agents --json --all failed"))
        snapshot = fleet.worker_cycle(self.worker, now=103.0)
        self.assertEqual(snapshot.error, "claude agents --json --all failed")
        self.assertEqual([session["sessionId"] for session in snapshot.sessions], ["a" * 36])
        self.assertEqual([lane["name"] for lane in snapshot.lanes], ["mn1"])

    def test_a_recovered_fetch_clears_the_error(self):
        fleet.fetch_sessions = self._explode(fleet.FleetError("down"))
        fleet.worker_cycle(self.worker, now=100.0)
        fleet.fetch_sessions = lambda root, timeout=10: [self._session()]
        self.assertEqual(fleet.worker_cycle(self.worker, now=103.0).error, "")

    def test_an_unexpected_fetch_explosion_is_still_reported_not_raised(self):
        fleet.fetch_sessions = self._explode(OSError("claude vanished"))
        self.assertIn("claude vanished", fleet.worker_cycle(self.worker, now=100.0).error)

    def test_lanes_are_swept_on_the_first_cycle_then_on_the_lane_interval(self):
        fleet.worker_cycle(self.worker, now=100.0)
        fleet.worker_cycle(self.worker, now=100.0 + fleet.LANE_INTERVAL - 1)
        self.assertEqual(len(self.lane_calls), 1)
        fleet.worker_cycle(self.worker, now=100.0 + fleet.LANE_INTERVAL)
        self.assertEqual(len(self.lane_calls), 2)

    def test_a_forced_lane_sweep_runs_on_the_next_cycle_and_clears(self):
        fleet.worker_cycle(self.worker, now=100.0)
        fleet.request_refresh(self.worker, lanes=True)
        fleet.worker_cycle(self.worker, now=101.0)
        self.assertEqual(len(self.lane_calls), 2)
        self.assertFalse(self.worker.lane_wake.is_set())
        fleet.worker_cycle(self.worker, now=102.0)
        self.assertEqual(len(self.lane_calls), 2)

    def test_an_exploding_lane_sweep_never_escapes_the_tick(self):
        fleet.lane_status = self._explode(RuntimeError("git went sideways"))
        self.assertIsNone(fleet.worker_tick(self.worker, now=100.0))

    def test_a_healthy_tick_still_returns_its_snapshot(self):
        self.assertIsNotNone(fleet.worker_tick(self.worker, now=100.0))


class WorkerThread(unittest.TestCase):
    def setUp(self):
        self.names = ("fetch_sessions", "lane_roots")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self.called = threading.Event()
        fleet.lane_roots = lambda sessions: []
        fleet.fetch_sessions = lambda root, timeout=10: self.called.set() or []
        self.worker = None

    def tearDown(self):
        if self.worker:
            self.worker.stopping.set()
            self.worker.wake.set()
        for name in self.names:
            setattr(fleet, name, self._saved[name])

    def test_the_data_thread_is_a_daemon_that_publishes_on_its_own(self):
        state = fleet.FleetState()
        self.worker = fleet.start_worker(state)
        self.assertTrue(self.called.wait(5))
        threads = [thread for thread in threading.enumerate() if thread.name == fleet.WORKER_NAME]
        self.assertEqual(len(threads), 1)
        self.assertTrue(threads[0].daemon)
        self.assertTrue(fleet.take_snapshot(state))
        self.worker.stopping.set()
        self.worker.wake.set()
        threads[0].join(5)
        self.assertFalse(threads[0].is_alive())


class SnapshotIntoTheUiState(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self._saved = (fleet.SIDECAR_DIR, fleet.STARS_PATH, fleet.curses.beep)
        fleet.SIDECAR_DIR = os.path.join(self._temp.name, "fleet-status")
        fleet.STARS_PATH = os.path.join(self._temp.name, "fleet-stars")
        self.beeps = []
        fleet.curses.beep = lambda: self.beeps.append(1)

    def tearDown(self):
        fleet.SIDECAR_DIR, fleet.STARS_PATH, fleet.curses.beep = self._saved
        self._temp.cleanup()

    def _session(self, state):
        return {"sessionId": "a" * 36, "id": "aaaaaaaa", "name": "n", "state": state, "cwd": "/e", "startedAt": 1, "context_text": "ctx"}

    def _snapshot(self, state, error="", at=1.0):
        return fleet.Snapshot([self._session(state)], [], at, error)

    def test_the_first_snapshot_is_a_silent_baseline(self):
        state = fleet.FleetState()
        fleet.apply_snapshot(state, self._snapshot("blocked"))
        self.assertEqual(state.rows[0]["bucket"], "BLOCKED")
        self.assertEqual(self.beeps, [])

    def test_a_later_flip_into_blocked_rings_once(self):
        state = fleet.FleetState()
        fleet.apply_snapshot(state, self._snapshot("working"))
        fleet.apply_snapshot(state, self._snapshot("blocked"))
        self.assertEqual(len(self.beeps), 1)
        fleet.apply_snapshot(state, self._snapshot("blocked"))
        self.assertEqual(len(self.beeps), 1)

    def test_an_error_snapshot_stamps_the_stale_banner_and_keeps_the_rows(self):
        state = fleet.FleetState()
        fleet.apply_snapshot(state, self._snapshot("working"))
        fleet.apply_snapshot(state, self._snapshot("working", error="claude agents --json --all failed", at=4.0))
        self.assertTrue(state.stale_since)
        self.assertIn(fleet.STALE_PREFIX, fleet.format_banner(state, 120))
        self.assertEqual(len(state.rows), 1)

    def test_the_stale_stamp_never_moves_while_the_fetch_stays_down(self):
        state = fleet.FleetState()
        state.stale_since = "09:00"
        fleet.apply_snapshot(state, self._snapshot("working", error="down"))
        self.assertEqual(state.stale_since, "09:00")

    def test_a_good_snapshot_clears_the_banner(self):
        state = fleet.FleetState()
        state.stale_since = "09:00"
        fleet.apply_snapshot(state, self._snapshot("working"))
        self.assertEqual(state.stale_since, "")
        self.assertNotIn(fleet.STALE_PREFIX, fleet.format_banner(state, 120))

    def test_taking_a_snapshot_happens_once_per_publish(self):
        state = fleet.FleetState()
        state.worker = fleet.DataWorker()
        self.assertFalse(fleet.take_snapshot(state))
        state.worker.holder.publish(self._snapshot("working"))
        self.assertTrue(fleet.take_snapshot(state))
        self.assertFalse(fleet.take_snapshot(state))
        self.assertEqual(state.fetched_at, 1.0)


class UiLoopPainting(unittest.TestCase):
    class Screen(object):
        def __init__(self, keys, on_idle=None):
            self.keys = list(keys)
            self.on_idle = on_idle

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            key = self.keys.pop(0) if self.keys else ord("q")
            if key == -1 and self.on_idle:
                self.on_idle()
            return key

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.paints = []
        self.names = ("paint", "init_colors", "start_worker")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self._curs_set = fleet.curses.curs_set
        self.worker = fleet.DataWorker()
        fleet.paint = lambda screen, state: self.paints.append(state.selected)
        fleet.init_colors = lambda: {}
        fleet.start_worker = self._start
        fleet.curses.curs_set = lambda value: None

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])
        fleet.curses.curs_set = self._curs_set

    def _start(self, state):
        state.worker = self.worker
        return self.worker

    def _state(self, rows=0):
        state = fleet.FleetState()
        state.rows = [{"session_id": str(index)} for index in range(rows)]
        return state

    def _run(self, keys, state=None, on_idle=None):
        state = state if state is not None else self._state()
        return fleet.run(self.Screen(keys, on_idle), state), state

    def test_idle_ticks_never_repaint(self):
        code, _state = self._run([-1] * 20 + [ord("q")])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.paints), 1)

    def test_every_move_repaints_and_lands_on_its_row(self):
        _code, state = self._run([ord("j")] * 3 + [ord("q")], self._state(5))
        self.assertEqual(self.paints, [0, 1, 2, 3])
        self.assertEqual(state.selected, 3)

    def test_a_fresh_snapshot_repaints_without_a_keypress(self):
        published = []

        def publish():
            if published:
                return
            published.append(1)
            self.worker.holder.publish(fleet.Snapshot([], [], 1.0, ""))

        self._run([-1, -1, -1, ord("q")], on_idle=publish)
        self.assertEqual(len(self.paints), 2)

    def test_R_asks_the_worker_for_an_immediate_sweep_with_lanes(self):
        self._run([ord("R"), ord("q")])
        self.assertTrue(self.worker.wake.is_set())
        self.assertTrue(self.worker.lane_wake.is_set())

    def test_quitting_tells_the_worker_to_stop(self):
        self._run([ord("q")])
        self.assertTrue(self.worker.stopping.is_set())
        self.assertTrue(self.worker.wake.is_set())

    def test_a_crash_in_the_loop_still_stops_the_worker(self):
        fleet.paint = self._boom
        with self.assertRaises(RuntimeError):
            self._run([ord("q")])
        self.assertTrue(self.worker.stopping.is_set())

    def _boom(self, screen, state):
        raise RuntimeError("paint blew up")


class FakeProc(object):
    def __init__(self, rc=0, alive=0):
        self.rc = rc
        self.alive = alive
        self.returncode = None
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.polls <= self.alive:
            return None
        self.returncode = self.rc
        return self.rc


class DispatchCase(unittest.TestCase):
    class Screen(object):
        def getmaxyx(self):
            return 40, 120

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.eng = self._temp.name
        for name in ("t1", "t2"):
            os.makedirs(os.path.join(self.eng, name))
        self.names = ("read_note", "ENG_ROOT")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self._popen = fleet.subprocess.Popen
        fleet.ENG_ROOT = self.eng
        fleet.subprocess.Popen = self._fake_popen
        self.typed = []
        self.prompts = []
        self.argvs = []
        self.streams = []
        self.output = ""
        self.rc = 0
        self.alive = 0
        self.procs = []
        self.logs = []
        self.explode = None
        fleet.read_note = self._fake_read_note

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])
        fleet.subprocess.Popen = self._popen
        self._temp.cleanup()

    def _fake_read_note(self, screen, prompt, limit=None):
        self.prompts.append((prompt, limit))
        return self.typed.pop(0) if self.typed else ""

    def _fake_popen(self, argv, stdin=None, stdout=None, stderr=None):
        self.argvs.append(list(argv))
        self.streams.append((stdin, stderr))
        if self.explode:
            raise self.explode
        self.logs.append(getattr(stdout, "name", ""))
        if stdout is not None and self.output:
            stdout.write(self.output.encode("utf-8"))
            stdout.flush()
        proc = FakeProc(self.rc, self.alive)
        self.procs.append(proc)
        return proc

    def _state(self):
        state = fleet.FleetState()
        state.worker = fleet.DataWorker()
        return state

    def _new_stream(self, *typed):
        self.typed = list(typed)
        state = self._state()
        message = fleet.new_stream(self.Screen(), state)
        return message, state


class LaneInputValidation(DispatchCase):
    def test_a_real_lane_directory_passes(self):
        self.assertTrue(fleet.lane_exists("t1"))
        self.assertTrue(fleet.lane_exists("t2", self.eng))

    def test_junk_is_not_a_lane(self):
        for junk in ("nope", "", "t1/x", "../etc", "/tmp", ".hidden", "t3"):
            self.assertFalse(fleet.lane_exists(junk), junk)

    def test_a_file_under_eng_root_is_not_a_lane(self):
        with open(os.path.join(self.eng, "notes.txt"), "w") as handle:
            handle.write("x\n")
        self.assertFalse(fleet.lane_exists("notes.txt"))

    def test_only_the_first_token_is_the_lane(self):
        self.assertEqual(fleet.split_lane_input("t1 --effort low"), ("t1", ["--effort", "low"]))
        self.assertEqual(fleet.split_lane_input("  t1  "), ("t1", []))
        self.assertEqual(fleet.split_lane_input(""), ("", []))
        self.assertEqual(fleet.split_lane_input(None), ("", []))

    def test_junk_lane_is_refused_with_a_message_and_no_dispatch(self):
        message, state = self._new_stream("nope", "some prompt")
        self.assertEqual(message, fleet.DISPATCH_NO_LANE % "nope")
        self.assertEqual(self.argvs, [])
        self.assertIsNone(state.dispatch)

    def test_an_empty_lane_line_is_refused_before_the_prompt(self):
        message, state = self._new_stream("   ", "some prompt")
        self.assertEqual(message, fleet.DISPATCH_NO_INPUT)
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(self.argvs, [])
        self.assertIsNone(state.dispatch)

    def test_a_path_escape_never_reaches_new_agent(self):
        message, _state = self._new_stream("../%s" % os.path.basename(self.eng), "some prompt")
        self.assertIn("no such lane", message)
        self.assertEqual(self.argvs, [])


class DispatchArgv(DispatchCase):
    def test_the_plain_case_is_tool_lane_prompt(self):
        message, state = self._new_stream("t1", "fix the thing")
        self.assertEqual(self.argvs, [["new-agent", "t1", "fix the thing"]])
        self.assertEqual(message, fleet.DISPATCH_STARTED % "t1")
        self.assertIsNotNone(state.dispatch)

    def test_extra_words_pass_through_verbatim(self):
        self._new_stream("t2 --effort low --safe", "fix the thing")
        self.assertEqual(self.argvs, [["new-agent", "t2", "--effort", "low", "--safe", "fix the thing"]])

    def test_argv_builder_is_pure(self):
        self.assertEqual(fleet.dispatch_argv("mn3", [], "hi"), ["new-agent", "mn3", "hi"])
        self.assertEqual(fleet.dispatch_argv("mn3", ["--safe"], "hi"), ["new-agent", "mn3", "--safe", "hi"])
        self.assertEqual(fleet.dispatch_argv("mn3", None, "hi"), ["new-agent", "mn3", "hi"])

    def test_the_prompt_is_never_split_into_argv(self):
        self._new_stream("t1", "fix the thing --safe now")
        self.assertEqual(self.argvs[0][2:], ["fix the thing --safe now"])

    def test_the_child_never_shares_the_curses_terminal(self):
        self._new_stream("t1", "fix the thing")
        stdin, stderr = self.streams[0]
        self.assertEqual(stdin, fleet.subprocess.DEVNULL)
        self.assertEqual(stderr, fleet.subprocess.STDOUT)

    def test_the_stream_prompt_takes_more_than_a_note(self):
        self._new_stream("t1", "fix the thing")
        self.assertEqual(self.prompts[0][0], fleet.LANE_PROMPT)
        self.assertEqual(self.prompts[1][0], fleet.STREAM_PROMPT % "t1")
        self.assertEqual(self.prompts[1][1], fleet.PROMPT_LIMIT)
        self.assertGreater(fleet.PROMPT_LIMIT, fleet.NOTE_LIMIT)

    def test_a_failed_spawn_reports_instead_of_raising(self):
        self.explode = OSError("new-agent: not found")
        message, state = self._new_stream("t1", "fix the thing")
        self.assertIn("new-agent", message)
        self.assertIsNone(state.dispatch)


class DispatchOutcomeParsing(unittest.TestCase):
    def test_a_backgrounded_block_yields_the_short_and_the_name(self):
        text = "warm-up noise\nbackgrounded · abc12345 · mn3/thing\nattach with: claude attach abc12345\n"
        self.assertEqual(fleet.dispatch_outcome(0, text), "dispatched abc12345 mn3/thing")

    def test_ansi_paint_does_not_hide_the_block(self):
        text = "\x1b[32mbackgrounded\x1b[0m · aaaabbbb · t1/test\n"
        self.assertEqual(fleet.dispatch_outcome(0, text), "dispatched aaaabbbb t1/test")

    def test_the_last_block_wins_when_the_log_repeats_itself(self):
        text = "backgrounded · 11111111 · a/one\nbackgrounded · 22222222 · b/two\n"
        self.assertEqual(fleet.dispatch_outcome(0, text), "dispatched 22222222 b/two")

    def test_a_failure_shows_the_last_non_empty_line(self):
        text = "fetching origin\nno such lane: zz\n\n   \n"
        self.assertEqual(fleet.dispatch_outcome(1, text), fleet.DISPATCH_FAILED % "no such lane: zz")

    def test_a_silent_failure_still_says_something(self):
        self.assertEqual(fleet.dispatch_outcome(1, ""), fleet.DISPATCH_FAILED % fleet.DISPATCH_NO_OUTPUT)

    def test_a_clean_exit_without_a_block_is_not_reported_as_a_stream(self):
        message = fleet.dispatch_outcome(0, "worktree ready\n")
        self.assertNotIn("dispatched", message)
        self.assertIn("worktree ready", message)


class DispatchLifecycle(DispatchCase):
    def test_a_running_dispatch_keeps_the_ui_quiet(self):
        self.alive = 2
        _message, state = self._new_stream("t1", "fix the thing")
        state.message = fleet.DISPATCH_STARTED % "t1"
        self.assertFalse(fleet.poll_dispatch(state))
        self.assertEqual(state.message, fleet.DISPATCH_STARTED % "t1")
        self.assertFalse(state.worker.wake.is_set())
        self.assertIsNotNone(state.dispatch)

    def test_a_finished_dispatch_surfaces_the_stream_and_asks_for_a_sweep(self):
        self.output = "backgrounded · aaaabbbb · t1/test\n"
        _message, state = self._new_stream("t1", "fix the thing")
        self.assertTrue(fleet.poll_dispatch(state))
        self.assertEqual(state.message, "dispatched aaaabbbb t1/test")
        self.assertTrue(state.worker.wake.is_set())
        self.assertIsNone(state.dispatch)

    def test_a_failed_dispatch_surfaces_the_last_line(self):
        self.rc = 1
        self.output = "no such lane: t9\n"
        _message, state = self._new_stream("t1", "fix the thing")
        self.assertTrue(fleet.poll_dispatch(state))
        self.assertEqual(state.message, fleet.DISPATCH_FAILED % "no such lane: t9")

    def test_the_scratch_log_is_cleaned_up(self):
        self.output = "backgrounded · aaaabbbb · t1/test\n"
        _message, state = self._new_stream("t1", "fix the thing")
        fleet.poll_dispatch(state)
        self.assertTrue(self.logs[0])
        self.assertFalse(os.path.exists(self.logs[0]))

    def test_polling_an_idle_state_is_inert(self):
        state = self._state()
        self.assertFalse(fleet.poll_dispatch(state))
        self.assertEqual(state.message, "")
        self.assertFalse(state.worker.wake.is_set())

    def test_a_second_new_stream_while_one_runs_is_refused(self):
        self.alive = 5
        _message, state = self._new_stream("t1", "fix the thing")
        self.prompts = []
        self.typed = ["t2", "another thing"]
        self.assertEqual(fleet.new_stream(self.Screen(), state), fleet.DISPATCH_BUSY)
        self.assertEqual(self.prompts, [])
        self.assertEqual(len(self.argvs), 1)

    def test_the_next_stream_goes_out_once_the_first_lands(self):
        self.output = "backgrounded · aaaabbbb · t1/test\n"
        _message, state = self._new_stream("t1", "fix the thing")
        fleet.poll_dispatch(state)
        self.typed = ["t2", "another thing"]
        self.assertEqual(fleet.new_stream(self.Screen(), state), fleet.DISPATCH_STARTED % "t2")
        self.assertEqual(len(self.argvs), 2)


class DispatchCancelling(DispatchCase):
    def test_escape_at_the_lane_prompt_spawns_nothing(self):
        message, state = self._new_stream(None, "fix the thing")
        self.assertEqual(message, fleet.NOTE_CANCELLED)
        self.assertEqual(self.argvs, [])
        self.assertEqual(len(self.prompts), 1)
        self.assertIsNone(state.dispatch)

    def test_escape_at_the_stream_prompt_spawns_nothing(self):
        message, state = self._new_stream("t1", None)
        self.assertEqual(message, fleet.NOTE_CANCELLED)
        self.assertEqual(self.argvs, [])
        self.assertEqual(len(self.prompts), 2)
        self.assertIsNone(state.dispatch)

    def test_an_empty_stream_prompt_spawns_nothing(self):
        message, state = self._new_stream("t1", "   ")
        self.assertEqual(message, fleet.NOTE_CANCELLED)
        self.assertEqual(self.argvs, [])
        self.assertIsNone(state.dispatch)


class NewStreamKey(unittest.TestCase):
    class Screen(object):
        def __init__(self, keys):
            self.keys = list(keys)

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            return self.keys.pop(0) if self.keys else ord("q")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.names = ("paint", "init_colors", "start_worker", "new_stream", "open_menu", "poll_dispatch")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self._curs_set = fleet.curses.curs_set
        self.worker = fleet.DataWorker()
        self.calls = []
        self.messages = []
        fleet.paint = lambda screen, state: self.messages.append(state.message)
        fleet.init_colors = lambda: {}
        fleet.start_worker = self._start
        fleet.open_menu = lambda screen, state, row: self.calls.append("menu")
        fleet.new_stream = lambda screen, state: self.calls.append("new") or "dispatching t1…"
        fleet.curses.curs_set = lambda value: None

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])
        fleet.curses.curs_set = self._curs_set

    def _start(self, state):
        state.worker = self.worker
        return self.worker

    def _run(self, keys):
        state = fleet.FleetState()
        state.rows = [{"session_id": "0"}]
        fleet.run(self.Screen(keys), state)
        return state

    def test_n_anywhere_in_the_main_view_starts_a_new_stream(self):
        self._run([ord("n"), ord("q")])
        self.assertEqual(self.calls, ["new"])
        self.assertIn("dispatching t1…", self.messages)

    def test_the_action_menu_never_offers_a_dispatch(self):
        for action, label, hint in fleet.menu_items({"bucket": "WORKING", "starred": False}):
            self.assertNotIn(action, ("new", "dispatch"))
            self.assertNotIn("new stream", label)
            self.assertNotEqual(hint, "n")
        self.assertNotIn(fleet.DISPATCH_KEY, fleet.ACTION_KEYS)

    def test_enter_still_opens_the_per_row_menu(self):
        self._run([10, ord("q")])
        self.assertEqual(self.calls, ["menu"])

    def test_the_loop_polls_the_dispatch_every_tick(self):
        polls = []
        fleet.poll_dispatch = lambda state: polls.append(1) and False
        self._run([-1, -1, ord("q")])
        self.assertGreaterEqual(len(polls), 3)


OLD_ENOUGH = fleet.FOLD_AFTER + 60
STILL_FRESH = fleet.FOLD_AFTER - 60


def fold_row_fixture(bucket, age, starred=False, session_id="a"):
    return {
        "session_id": session_id,
        "short": session_id,
        "name": "row-%s" % session_id,
        "age": "1d",
        "age_seconds": age,
        "starred": starred,
        "bucket": bucket,
        "context": "context",
        "pr": None,
    }


def fold_state(groups, expanded=False):
    state = fleet.FleetState()
    state.model = {"counts": {}, "lanes": [], "groups": groups}
    state.expanded = expanded
    fleet.reflow(state)
    return state


class FoldRules(unittest.TestCase):
    def test_every_bucket_folds_only_where_it_should(self):
        expected = {
            ("BLOCKED", True): False,
            ("BLOCKED", False): False,
            ("WORKING", True): False,
            ("WORKING", False): False,
            ("COMPLETE", True): True,
            ("COMPLETE", False): False,
            ("AWAITING", True): True,
            ("AWAITING", False): False,
            ("STOPPED", True): True,
            ("STOPPED", False): True,
        }
        for (bucket, old), folded in sorted(expected.items()):
            age = OLD_ENOUGH if old else STILL_FRESH
            self.assertEqual(fleet.fold_row(bucket, age, False), folded, (bucket, old))
            self.assertFalse(fleet.fold_row(bucket, age, True), (bucket, old))
            self.assertFalse(fleet.fold_row(bucket, age, False, True), (bucket, old))

    def test_every_bucket_is_covered_by_the_rule(self):
        self.assertEqual(sorted(fleet.FOLD_BUCKETS + fleet.FOLD_ALWAYS), ["AWAITING", "COMPLETE", "STOPPED"])

    def test_the_threshold_is_forty_eight_hours_and_exclusive(self):
        self.assertEqual(fleet.FOLD_AFTER, 48 * 3600)
        self.assertFalse(fleet.fold_row("COMPLETE", fleet.FOLD_AFTER, False))
        self.assertTrue(fleet.fold_row("COMPLETE", fleet.FOLD_AFTER + 1, False))

    def test_an_unreadable_age_folds_only_the_stopped_row(self):
        self.assertFalse(fleet.fold_row("COMPLETE", None, False))
        self.assertFalse(fleet.fold_row("AWAITING", None, False))
        self.assertTrue(fleet.fold_row("STOPPED", None, False))

    def test_the_row_wrapper_reads_the_same_fields_the_model_writes(self):
        self.assertTrue(fleet.row_folded(fold_row_fixture("AWAITING", OLD_ENOUGH)))
        self.assertFalse(fleet.row_folded(fold_row_fixture("AWAITING", OLD_ENOUGH, starred=True)))
        self.assertFalse(fleet.row_folded(fold_row_fixture("AWAITING", OLD_ENOUGH), True))

    def test_age_seconds_reads_the_stamp_the_age_column_reads(self):
        started = 1000.0 * 1000
        self.assertEqual(fleet.age_seconds(started, 1000.0 + fleet.FOLD_AFTER), fleet.FOLD_AFTER)
        self.assertEqual(fleet.format_age(started, 1000.0 + fleet.FOLD_AFTER), "2d")
        self.assertEqual(fleet.age_seconds(started, 500.0), 0.0)
        self.assertIsNone(fleet.age_seconds("not-a-stamp"))
        self.assertEqual(fleet.format_age("not-a-stamp"), "?")

    def test_the_model_carries_the_age_in_seconds(self):
        sessions = [
            {"sessionId": "z" * 36, "id": "zzzzzzzz", "name": "n", "state": "done", "status": "idle", "cwd": "/e", "startedAt": 1}
        ]
        row = fleet.build_model(sessions, {}, set(), [])["groups"][0][1][0]
        self.assertGreater(row["age_seconds"], fleet.FOLD_AFTER)
        self.assertTrue(fleet.row_folded(row))


class FoldedGroups(unittest.TestCase):
    def test_fold_groups_splits_visible_rows_from_a_hidden_count(self):
        rows = [
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="fresh"),
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="old"),
        ]
        self.assertEqual(fleet.fold_groups([("COMPLETE", rows)]), [("COMPLETE", [rows[0]], 1)])
        self.assertEqual(fleet.fold_groups([("COMPLETE", rows)], True), [("COMPLETE", rows, 0)])

    def test_a_starred_old_row_survives_the_fold(self):
        rows = [
            fold_row_fixture("STOPPED", OLD_ENOUGH, starred=True, session_id="star"),
            fold_row_fixture("STOPPED", STILL_FRESH, session_id="plain"),
        ]
        self.assertEqual(fleet.fold_groups([("STOPPED", rows)]), [("STOPPED", [rows[0]], 1)])

    def test_foldable_count_ignores_the_current_view(self):
        rows = [
            fold_row_fixture("AWAITING", OLD_ENOUGH, session_id="a"),
            fold_row_fixture("AWAITING", OLD_ENOUGH, session_id="b"),
            fold_row_fixture("AWAITING", STILL_FRESH, session_id="c"),
        ]
        self.assertEqual(fleet.foldable_count([("AWAITING", rows)]), 2)

    def test_a_fully_folded_group_renders_only_its_header(self):
        rows = [fold_row_fixture("STOPPED", STILL_FRESH, session_id=str(index)) for index in range(3)]
        state = fold_state([("STOPPED", rows)])
        lines = fleet.body_lines(state, 120)
        self.assertEqual([line[1] for line in lines], ["spacer", "header"])
        self.assertTrue(lines[1][0].endswith("· 3 hidden"))
        self.assertEqual(state.rows, [])

    def test_a_partly_folded_group_keeps_its_rows_and_counts_the_rest(self):
        rows = [
            fold_row_fixture("AWAITING", STILL_FRESH, session_id="live"),
            fold_row_fixture("AWAITING", OLD_ENOUGH, session_id="old"),
        ]
        state = fold_state([("AWAITING", rows)])
        lines = fleet.body_lines(state, 120)
        self.assertEqual([line[1] for line in lines], ["spacer", "header", "row", "context"])
        self.assertTrue(lines[1][0].endswith("· 1 hidden"))
        self.assertEqual([line[3] for line in lines if line[1] == "row"], [0])

    def test_no_spacer_is_left_where_a_folded_row_used_to_sit(self):
        rows = [
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="a"),
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="b"),
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="c"),
        ]
        kinds = [line[1] for line in fleet.body_lines(fold_state([("COMPLETE", rows)]), 120)]
        self.assertEqual(kinds, ["spacer", "header", "row", "context", "spacer", "row", "context"])

    def test_an_unfolded_header_carries_no_count(self):
        rows = [fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="a")]
        header = fleet.body_lines(fold_state([("COMPLETE", rows)], expanded=True), 120)[1][0]
        self.assertNotIn("hidden", header)
        self.assertEqual(header, fleet.format_group_header("COMPLETE", 120))

    def test_the_header_count_stays_inside_a_narrow_window(self):
        header = fleet.format_group_header("COMPLETE", 24, 4)
        self.assertLessEqual(fleet.cell_width(header), 24)

    def test_the_body_index_still_addresses_the_visible_rows(self):
        rows = [
            fold_row_fixture("STOPPED", STILL_FRESH, session_id="gone"),
            fold_row_fixture("AWAITING", STILL_FRESH, session_id="here"),
        ]
        state = fold_state([("STOPPED", [rows[0]]), ("AWAITING", [rows[1]])])
        state.selected = 0
        lines = fleet.body_lines(state, 120)
        selected = [line[2] for line in lines if line[3] == 0 and line[1] == "row"]
        self.assertEqual(state.rows, [rows[1]])
        self.assertEqual(selected, [rows[1]])

    def test_the_banner_counts_everything_even_when_nothing_shows(self):
        sessions = [
            {"sessionId": "s" * 36, "id": "ssssssss", "name": "old", "state": "stopped", "status": "idle", "cwd": "/e", "startedAt": 1}
        ]
        state = fleet.FleetState()
        state.model = fleet.build_model(sessions, {}, set(), [])
        fleet.reflow(state)
        self.assertEqual(state.rows, [])
        self.assertEqual(state.model["counts"]["STOPPED"], 1)
        self.assertIn("1 STOPPED", fleet.format_banner(state, 120))


class FoldFooter(unittest.TestCase):
    def _state(self, groups, expanded=False):
        return fold_state(groups, expanded)

    def test_nothing_foldable_leaves_the_footer_alone(self):
        rows = [fold_row_fixture("WORKING", OLD_ENOUGH, session_id="w")]
        self.assertEqual(fleet.footer_text(self._state([("WORKING", rows)])), fleet.FOOTER)
        self.assertEqual(fleet.fold_hint(0, False), "")
        self.assertEqual(fleet.fold_hint(0, True), "")

    def test_hidden_rows_advertise_the_show_key_with_the_live_count(self):
        rows = [
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="a"),
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="b"),
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="c"),
        ]
        self.assertEqual(fleet.footer_text(self._state([("COMPLETE", rows)])), fleet.FOOTER + " [S]show 2")

    def test_the_expanded_footer_offers_to_hide_them_again(self):
        rows = [fold_row_fixture("STOPPED", STILL_FRESH, session_id="a")]
        self.assertEqual(fleet.footer_text(self._state([("STOPPED", rows)], True)), fleet.FOOTER + " [S]hide")

    def test_an_empty_fleet_keeps_the_plain_footer(self):
        self.assertEqual(fleet.footer_text(fleet.FleetState()), fleet.FOOTER)


class FoldToggle(unittest.TestCase):
    def _rows(self):
        return [
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="live"),
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="old"),
        ]

    def test_toggling_flips_the_view_both_ways(self):
        state = fold_state([("COMPLETE", self._rows())])
        self.assertEqual(len(state.rows), 1)
        self.assertTrue(fleet.toggle_fold(state))
        self.assertEqual(len(state.rows), 2)
        self.assertTrue(fleet.toggle_fold(state))
        self.assertEqual(len(state.rows), 1)

    def test_toggling_is_a_no_op_when_nothing_would_fold(self):
        rows = [fold_row_fixture("WORKING", OLD_ENOUGH, session_id="w")]
        state = fold_state([("WORKING", rows)])
        self.assertFalse(fleet.toggle_fold(state))
        self.assertFalse(state.expanded)
        self.assertEqual(len(state.rows), 1)

    def test_refolding_moves_the_selection_off_the_hidden_row(self):
        rows = self._rows()
        state = fold_state([("COMPLETE", rows)], expanded=True)
        state.selected, state.selected_id = 1, "old"
        fleet.toggle_fold(state)
        self.assertEqual(state.rows, [rows[0]])
        self.assertEqual((state.selected, state.selected_id), (0, "live"))
        self.assertEqual(fleet.selected_row(state), rows[0])

    def test_a_visible_selection_survives_the_toggle(self):
        rows = self._rows()
        state = fold_state([("COMPLETE", rows)])
        self.assertEqual(state.selected_id, "live")
        fleet.toggle_fold(state)
        self.assertEqual((state.selected, state.selected_id), (0, "live"))

    def test_folding_everything_empties_the_selection_until_it_is_shown(self):
        rows = [fold_row_fixture("STOPPED", STILL_FRESH, session_id=name) for name in ("s1", "s2")]
        state = fold_state([("STOPPED", rows)])
        self.assertEqual((state.rows, state.selected, state.selected_id), ([], 0, ""))
        self.assertIsNone(fleet.selected_row(state))
        fleet.toggle_fold(state)
        self.assertEqual(len(state.rows), 2)
        self.assertEqual(state.selected_id, "s1")


class FoldKeyRouting(unittest.TestCase):
    class Screen(object):
        def __init__(self, keys):
            self.keys = list(keys)

        def getmaxyx(self):
            return 40, 120

        def getch(self):
            return self.keys.pop(0) if self.keys else ord("q")

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    def setUp(self):
        self.names = ("paint", "init_colors", "start_worker")
        self._saved = dict((name, getattr(fleet, name)) for name in self.names)
        self._curs_set = fleet.curses.curs_set
        self.worker = fleet.DataWorker()
        self.footers = []
        fleet.paint = lambda screen, state: self.footers.append(fleet.footer_text(state))
        fleet.init_colors = lambda: {}
        fleet.start_worker = self._start
        fleet.curses.curs_set = lambda value: None

    def tearDown(self):
        for name in self.names:
            setattr(fleet, name, self._saved[name])
        fleet.curses.curs_set = self._curs_set

    def _start(self, state):
        state.worker = self.worker
        return self.worker

    def _state(self):
        rows = [
            fold_row_fixture("COMPLETE", STILL_FRESH, session_id="live"),
            fold_row_fixture("COMPLETE", OLD_ENOUGH, session_id="old"),
        ]
        return fold_state([("COMPLETE", rows)])

    def _run(self, keys, state):
        fleet.run(self.Screen(keys), state)
        return state

    def test_S_shows_the_folded_rows_and_hides_them_again(self):
        state = self._run([fleet.FOLD_KEY, fleet.FOLD_KEY, ord("q")], self._state())
        self.assertEqual(
            self.footers,
            [fleet.FOOTER + " [S]show 1", fleet.FOOTER + " [S]hide", fleet.FOOTER + " [S]show 1"],
        )
        self.assertFalse(state.expanded)
        self.assertEqual(len(state.rows), 1)

    def test_S_does_nothing_when_nothing_would_fold(self):
        rows = [fold_row_fixture("WORKING", OLD_ENOUGH, session_id="w")]
        state = self._run([fleet.FOLD_KEY, ord("q")], fold_state([("WORKING", rows)]))
        self.assertFalse(state.expanded)
        self.assertEqual(self.footers, [fleet.FOOTER, fleet.FOOTER])

    def test_the_fold_key_never_collides_with_the_action_keys(self):
        self.assertEqual(fleet.FOLD_KEY, ord("S"))
        self.assertNotIn(fleet.FOLD_KEY, fleet.ACTION_KEYS)
        self.assertEqual(fleet.ACTION_KEYS[ord("s")], "stop")
        self.assertNotEqual(fleet.FOLD_KEY, fleet.DISPATCH_KEY)


class InputLoopLatency(unittest.TestCase):
    def test_the_key_poll_stays_snappy(self):
        self.assertLessEqual(fleet.POLL_MS, 50)

    def test_the_worker_keeps_the_old_fetch_cadence(self):
        self.assertEqual((fleet.SESSION_INTERVAL, fleet.LANE_INTERVAL), (3.0, 15.0))


if __name__ == "__main__":
    unittest.main()
