#!/usr/bin/env python3
# Tests for board card storage, CLI, and GET /board-cards.
import errno
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import board_cards  # noqa: E402
import server  # noqa: E402


TODO_READY = {
    "id": "todo",
    "status": "ready",
    "attemptedAt": "2026-03-29T12:00:00Z",
    "updatedAt": "2026-03-29T12:00:00Z",
    "totalCount": 2,
    "items": [
        {"id": "t1", "title": "Buy milk", "dueDate": "2026-03-29"},
        {"id": "t2", "title": "Write tests"},
    ],
}

CAL_READY = {
    "id": "calendar",
    "status": "ready",
    "attemptedAt": "2026-03-29T12:00:00Z",
    "updatedAt": "2026-03-29T12:00:00Z",
    "totalCount": 2,
    "timezone": "Europe/London",
    "range": {"start": "2026-03-29", "end": "2026-03-30"},
    "items": [
        {
            "id": "e1",
            "title": "All day off",
            "allDay": True,
            "startDate": "2026-03-29",
            "endDate": "2026-03-30",
        },
        {
            "id": "e2",
            "title": "Call",
            "allDay": False,
            "start": "2026-03-29T00:30:00Z",
            "end": "2026-03-29T02:30:00Z",
        },
    ],
}


def _unused_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run_cli(args, stdin=None, stdin_bytes=None):
    cmd = [sys.executable, str(REPO / "board_cards.py"), *args]
    if stdin_bytes is not None:
        return subprocess.run(
            cmd, input=stdin_bytes, capture_output=True, cwd=str(REPO)
        )
    return subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, cwd=str(REPO)
    )


class CardsTemp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)
        self.path = self.dir / "cards.json"

    def tearDown(self):
        self._td.cleanup()

    def publish(self, payload):
        return board_cards.publish_update(self.path, payload, static_root=REPO)

    def load(self):
        snap, _raw = board_cards.load_snapshot(self.path)
        return snap

    def card(self, card_id):
        for card in self.load()["cards"]:
            if card["id"] == card_id:
                return card
        self.fail("missing card %s" % card_id)


class TestRfc3339(unittest.TestCase):
    def test_parses_z_and_numeric_offsets_as_instants(self):
        z = board_cards.parse_rfc3339("2026-03-29T00:30:00Z")
        offset = board_cards.parse_rfc3339("2026-03-29T01:30:00+01:00")
        negative = board_cards.parse_rfc3339("2026-03-28T19:30:00-05:00")
        self.assertEqual(z.astimezone(timezone.utc), offset.astimezone(timezone.utc))
        self.assertEqual(z.astimezone(timezone.utc), negative.astimezone(timezone.utc))
        self.assertIsInstance(z, datetime)

    def test_rejects_malformed_and_impossible_timestamps(self):
        for value in (
            "not-a-date",
            "2026-03-29 00:30:00Z",
            "2026-03-29T00:30:00",
            "2026-02-30T00:00:00Z",
            "2026-03-29T24:00:00Z",
            "2026-03-29T00:30:00+25:00",
            "2026-03-29T00:30:00+00:60",
        ):
            with self.subTest(value=value):
                with self.assertRaises(board_cards.ValidationError):
                    board_cards.parse_rfc3339(value)


class TestDatesAndRange(CardsTemp):
    def test_ready_calendar_requires_real_range_and_timezone(self):
        payload = json.loads(json.dumps(CAL_READY))
        del payload["range"]
        with self.assertRaises(board_cards.ValidationError):
            self.publish(payload)
        self.assertFalse(self.path.exists())

        payload = json.loads(json.dumps(CAL_READY))
        del payload["timezone"]
        with self.assertRaises(board_cards.ValidationError):
            self.publish(payload)

    def test_missing_invalid_dates_and_blank_timezone_are_rejected(self):
        cases = []
        missing_end = json.loads(json.dumps(CAL_READY))
        del missing_end["range"]["end"]
        cases.append(missing_end)

        invalid = json.loads(json.dumps(CAL_READY))
        invalid["range"]["start"] = "2026-02-30"
        cases.append(invalid)

        unpadded = json.loads(json.dumps(CAL_READY))
        unpadded["range"]["start"] = "2026-3-29"
        cases.append(unpadded)

        blank_tz = json.loads(json.dumps(CAL_READY))
        blank_tz["timezone"] = "   "
        cases.append(blank_tz)

        empty_tz = json.loads(json.dumps(CAL_READY))
        empty_tz["timezone"] = ""
        cases.append(empty_tz)

        bad_all_day = json.loads(json.dumps(CAL_READY))
        bad_all_day["items"][0]["endDate"] = "2026-02-30"
        cases.append(bad_all_day)

        missing_due_format = json.loads(json.dumps(TODO_READY))
        missing_due_format["items"][0]["dueDate"] = "03/29/2026"
        cases.append(missing_due_format)

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(board_cards.ValidationError):
                    self.publish(payload)
                self.assertFalse(self.path.exists())

    def test_exclusive_end_must_be_later_than_start(self):
        same = json.loads(json.dumps(CAL_READY))
        same["range"]["end"] = same["range"]["start"]
        with self.assertRaises(board_cards.ValidationError):
            self.publish(same)

        earlier = json.loads(json.dumps(CAL_READY))
        earlier["range"]["end"] = "2026-03-28"
        with self.assertRaises(board_cards.ValidationError):
            self.publish(earlier)

        all_day_same = json.loads(json.dumps(CAL_READY))
        all_day_same["items"][0]["endDate"] = "2026-03-29"
        with self.assertRaises(board_cards.ValidationError):
            self.publish(all_day_same)

        self.publish(CAL_READY)
        card = self.card("calendar")
        self.assertEqual(card["range"], {"start": "2026-03-29", "end": "2026-03-30"})
        self.assertEqual(card["timezone"], "Europe/London")

    def test_timezone_is_trimmed_and_stored(self):
        payload = json.loads(json.dumps(CAL_READY))
        payload["timezone"] = "  Europe/London  "
        self.publish(payload)
        self.assertEqual(self.card("calendar")["timezone"], "Europe/London")


class TestPathResolution(unittest.TestCase):
    def test_cli_overrides_config_overrides_default(self):
        repo = REPO
        cli = board_cards.resolve_cards_path(
            cli_path="/tmp/cli-cards.json",
            config_path="~/from-config.json",
            repo_root=repo,
        )
        self.assertEqual(cli, Path("/tmp/cli-cards.json").resolve())

        cfg = board_cards.resolve_cards_path(
            cli_path=None,
            config_path="~/from-config.json",
            repo_root=repo,
        )
        self.assertEqual(cfg, (Path.home() / "from-config.json").resolve())

        default = board_cards.resolve_cards_path(
            cli_path=None, config_path=None, repo_root=repo
        )
        self.assertEqual(
            default,
            (Path.home() / ".local/share/ai-visualizer/board-cards.json").resolve(),
        )
        empty_config = board_cards.resolve_cards_path(
            cli_path=None, config_path="", repo_root=repo
        )
        self.assertEqual(empty_config, default)

    def test_relative_paths_resolve_against_repo_root(self):
        resolved = board_cards.resolve_cards_path(
            cli_path="tmp/cards.json", config_path=None, repo_root=REPO
        )
        self.assertEqual(resolved, (REPO / "tmp/cards.json").resolve())

    def test_static_root_and_symlink_targets_are_rejected(self):
        under = board_cards.resolve_cards_path(
            cli_path="faces/board/cards.json", config_path=None, repo_root=REPO
        )
        with self.assertRaises(board_cards.StaticRootError) as ctx:
            board_cards.refuse_under_static_root(under, static_root=REPO)
        self.assertIn("static root", str(ctx.exception).lower())

        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "via-link.json"
            link.symlink_to(REPO / "README.md")
            resolved = board_cards.resolve_cards_path(
                cli_path=str(link), config_path=None, repo_root=REPO
            )
            with self.assertRaises(board_cards.StaticRootError):
                board_cards.refuse_under_static_root(resolved, static_root=REPO)

    def test_defaults_and_example_config_include_board_cards_file(self):
        self.assertIn("board_cards_file", server.DEFAULTS)
        example = json.loads((REPO / "ai-visualizer.json.example").read_text())
        self.assertIn("board_cards_file", example)

    def test_lock_implementation_is_portable(self):
        src = (REPO / "board_cards.py").read_text()
        self.assertNotIn("fcntl", src)
        self.assertIn("O_CREAT", src)
        self.assertIn("O_EXCL", src)
        self.assertEqual(board_cards.LOCK_TIMEOUT_S, 5)


class TestPublishMerge(CardsTemp):
    def test_invalid_input_preserves_existing_bytes(self):
        self.publish(TODO_READY)
        before = self.path.read_bytes()
        invalids = [
            {"id": "todo", "status": "ready"},
            {
                "id": "todo",
                "status": "ready",
                "attemptedAt": "nope",
                "updatedAt": "2026-03-29T12:00:00Z",
                "totalCount": 1,
                "items": [{"id": "a", "title": "x"}],
            },
            {
                "id": "todo",
                "status": "ready",
                "attemptedAt": "2026-03-29T13:00:00Z",
                "updatedAt": "2026-03-29T13:00:00Z",
                "totalCount": 2,
                "items": [
                    {"id": "dup", "title": "one"},
                    {"id": "dup", "title": "two"},
                ],
            },
            {
                "id": "notes",
                "status": "ready",
                "attemptedAt": "2026-03-29T13:00:00Z",
                "updatedAt": "2026-03-29T13:00:00Z",
                "totalCount": 0,
                "items": [],
            },
            {
                "id": "todo",
                "status": "ready",
                "attemptedAt": "2026-03-29T13:00:00Z",
                "updatedAt": "2026-03-29T13:00:00Z",
                "totalCount": 0,
                "items": [{"id": "a", "title": "x" * 501}],
            },
            {
                "id": "todo",
                "status": "ready",
                "attemptedAt": "2026-03-29T13:00:00Z",
                "updatedAt": "2026-03-29T13:00:00Z",
                "totalCount": 0,
                "items": [],
            },
        ]
        # last case: totalCount 0 with 0 items is valid; swap for too-small totalCount
        invalids[-1]["items"] = [{"id": "a", "title": "x"}]
        invalids[-1]["totalCount"] = 0

        for payload in invalids:
            with self.subTest(payload=payload):
                with self.assertRaises(board_cards.ValidationError):
                    self.publish(payload)
                self.assertEqual(self.path.read_bytes(), before)

        proc = _run_cli(
            ["--cards-file", str(self.path), "publish"], stdin="{not json"
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)

        huge = b"{" + (b"x" * (board_cards.MAX_DOCUMENT_BYTES + 1))
        proc = _run_cli(
            ["--cards-file", str(self.path), "publish"], stdin_bytes=huge
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)

        self.path.write_bytes(before)
        self.path.write_text('{"version": 2, "cards": []}')
        corrupt = self.path.read_bytes()
        with self.assertRaises(board_cards.CorruptStorageError):
            self.publish(TODO_READY)
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_per_card_merge_preserves_the_other_card(self):
        self.publish(TODO_READY)
        self.publish(CAL_READY)
        newer_todo = json.loads(json.dumps(TODO_READY))
        newer_todo["attemptedAt"] = "2026-03-29T13:00:00Z"
        newer_todo["updatedAt"] = "2026-03-29T13:00:00Z"
        newer_todo["items"] = [{"id": "t9", "title": "Only todo changed"}]
        newer_todo["totalCount"] = 1
        self.publish(newer_todo)
        snap = self.load()
        ids = {c["id"]: c for c in snap["cards"]}
        self.assertEqual(ids["todo"]["items"][0]["title"], "Only todo changed")
        self.assertEqual(ids["calendar"]["items"][0]["id"], "e1")
        self.assertEqual(snap["version"], 1)

    def test_older_attempt_is_rejected_equal_timestamp_is_accepted(self):
        self.publish(TODO_READY)
        before = self.path.read_bytes()
        older = json.loads(json.dumps(TODO_READY))
        older["attemptedAt"] = "2026-03-29T11:59:59Z"
        older["updatedAt"] = "2026-03-29T11:59:59Z"
        older["items"] = [{"id": "old", "title": "should not land"}]
        older["totalCount"] = 1
        with self.assertRaises(board_cards.StaleUpdateError):
            self.publish(older)
        self.assertEqual(self.path.read_bytes(), before)

        older_offset = json.loads(json.dumps(TODO_READY))
        # 12:00+01:00 is 11:00Z, older than 12:00Z
        older_offset["attemptedAt"] = "2026-03-29T12:00:00+01:00"
        older_offset["updatedAt"] = "2026-03-29T12:00:00+01:00"
        with self.assertRaises(board_cards.StaleUpdateError):
            self.publish(older_offset)

        equal = json.loads(json.dumps(TODO_READY))
        equal["items"] = [{"id": "eq", "title": "last writer wins"}]
        equal["totalCount"] = 1
        self.publish(equal)
        self.assertEqual(self.card("todo")["items"][0]["id"], "eq")

        equal_z = json.loads(json.dumps(TODO_READY))
        equal_z["attemptedAt"] = "2026-03-29T13:00:00+01:00"
        equal_z["updatedAt"] = "2026-03-29T12:00:00Z"
        equal_z["items"] = [{"id": "offset-equal", "title": "same instant"}]
        equal_z["totalCount"] = 1
        # 13:00+01:00 is 12:00Z, equal to stored attemptedAt from TODO_READY
        # Wait: we just published `equal` which still has attemptedAt 12:00Z.
        self.publish(equal_z)
        self.assertEqual(self.card("todo")["items"][0]["id"], "offset-equal")

    def test_loading_and_error_retain_success_and_omit_scope_before_first_success(self):
        first_error = {
            "id": "calendar",
            "status": "error",
            "attemptedAt": "2026-03-29T10:00:00Z",
            "message": "provider failed",
        }
        self.publish(first_error)
        card = self.card("calendar")
        self.assertEqual(card["status"], "error")
        self.assertNotIn("range", card)
        self.assertNotIn("timezone", card)
        self.assertNotIn("items", card)
        self.assertNotIn("updatedAt", card)

        first_loading = {
            "id": "todo",
            "status": "loading",
            "attemptedAt": "2026-03-29T10:00:00Z",
        }
        self.publish(first_loading)
        todo = self.card("todo")
        self.assertEqual(todo["status"], "loading")
        self.assertNotIn("items", todo)

        self.publish(CAL_READY)
        self.publish(TODO_READY)
        loading = {
            "id": "calendar",
            "status": "loading",
            "attemptedAt": "2026-03-29T14:00:00Z",
        }
        self.publish(loading)
        loaded = self.card("calendar")
        self.assertEqual(loaded["status"], "loading")
        self.assertEqual(loaded["items"][0]["id"], "e1")
        self.assertEqual(loaded["totalCount"], 2)
        self.assertEqual(loaded["updatedAt"], CAL_READY["updatedAt"])
        self.assertEqual(loaded["range"], CAL_READY["range"])
        self.assertEqual(loaded["timezone"], "Europe/London")
        self.assertEqual(self.card("todo")["status"], "ready")

        err = {
            "id": "calendar",
            "status": "error",
            "attemptedAt": "2026-03-29T14:01:00Z",
            "message": "<b>boom</b>  extra",
        }
        self.publish(err)
        failed = self.card("calendar")
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["items"][0]["id"], "e1")
        self.assertEqual(failed["range"], CAL_READY["range"])
        self.assertEqual(failed["timezone"], "Europe/London")
        self.assertNotIn("<", failed["message"])
        self.assertIn("boom", failed["message"])

    def test_successful_empty_result_replaces_items(self):
        self.publish(TODO_READY)
        empty = {
            "id": "todo",
            "status": "ready",
            "attemptedAt": "2026-03-29T15:00:00Z",
            "updatedAt": "2026-03-29T15:00:00Z",
            "totalCount": 0,
            "items": [],
        }
        self.publish(empty)
        card = self.card("todo")
        self.assertEqual(card["items"], [])
        self.assertEqual(card["totalCount"], 0)
        self.assertEqual(card["updatedAt"], "2026-03-29T15:00:00Z")

    def test_overlapping_writers_serialize_and_keep_valid_json(self):
        errors = []
        barrier = threading.Barrier(2)

        def write(payload):
            try:
                barrier.wait(timeout=2)
                board_cards.publish_update(self.path, payload, static_root=REPO)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=write, args=(TODO_READY,)),
            threading.Thread(target=write, args=(CAL_READY,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        snap = json.loads(self.path.read_text())
        self.assertEqual(snap["version"], 1)
        self.assertEqual({c["id"] for c in snap["cards"]}, {"todo", "calendar"})


class TestLocking(CardsTemp):
    def test_lock_timeout_does_not_mutate_and_finally_releases(self):
        self.publish(TODO_READY)
        before = self.path.read_bytes()
        lock_path = Path(str(self.path) + ".lock")
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        original_timeout = board_cards.LOCK_TIMEOUT_S
        board_cards.LOCK_TIMEOUT_S = 0.4
        try:
            started = time.monotonic()
            with self.assertRaises(board_cards.LockTimeout):
                self.publish(CAL_READY)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.35)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertTrue(lock_path.exists())
        finally:
            board_cards.LOCK_TIMEOUT_S = original_timeout
            os.close(fd)
            os.unlink(lock_path)

        self.publish(CAL_READY)
        self.assertFalse(lock_path.exists())
        self.assertEqual({c["id"] for c in self.load()["cards"]}, {"todo", "calendar"})

    def test_posix_owner_only_permissions_are_best_effort(self):
        self.publish(TODO_READY)
        if os.name != "posix":
            return
        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


class TestClearAndReload(CardsTemp):
    def test_clear_and_reload_from_disk(self):
        self.publish(TODO_READY)
        self.publish(CAL_READY)
        board_cards.clear_cards(self.path, "todo", static_root=REPO)
        snap = json.loads(self.path.read_text())
        self.assertEqual([c["id"] for c in snap["cards"]], ["calendar"])

        board_cards.clear_cards(self.path, "all", static_root=REPO)
        snap = json.loads(self.path.read_text())
        self.assertEqual(snap, {"version": 1, "cards": []})

        self.publish(CAL_READY)
        reloaded, raw = board_cards.load_snapshot(self.path)
        self.assertEqual(reloaded["cards"][0]["id"], "calendar")
        self.assertEqual(json.loads(raw.decode("utf-8"))["cards"][0]["timezone"],
                         "Europe/London")

        proc = _run_cli(
            ["--cards-file", str(self.path), "clear", "--card", "calendar"]
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(self.path.read_text())["cards"], [])


class TestCliAndServerEntry(unittest.TestCase):
    def test_cli_publish_and_new_process_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            proc = _run_cli(
                ["--cards-file", str(path), "publish"],
                stdin=json.dumps(TODO_READY),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc2 = _run_cli(
                ["--cards-file", str(path), "publish"],
                stdin=json.dumps(CAL_READY),
            )
            self.assertEqual(proc2.returncode, 0, proc2.stderr)
            snap = json.loads(path.read_text())
            self.assertEqual({c["id"] for c in snap["cards"]}, {"todo", "calendar"})

    def test_both_entry_points_refuse_static_root_paths(self):
        relative = "faces/board/secret-cards.json"
        proc = _run_cli(
            ["--cards-file", relative, "publish"],
            stdin=json.dumps(TODO_READY),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("static root", (proc.stderr + proc.stdout).lower())
        self.assertFalse((REPO / relative).exists())

        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link.json"
            link.symlink_to(REPO / "README.md")
            proc = _run_cli(
                ["--cards-file", str(link), "clear", "--card", "all"]
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("static root", (proc.stderr + proc.stdout).lower())

        proc = subprocess.run(
            [
                sys.executable,
                str(REPO / "server.py"),
                "--no-open",
                "--cards-file",
                relative,
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("static root", (proc.stderr + proc.stdout).lower())

    def test_server_cards_file_override_serves_disposable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            board_cards.publish_update(path, TODO_READY, static_root=REPO)
            port = _unused_port()
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(REPO / "server.py"),
                    "--no-open",
                    "--port",
                    str(port),
                    "--cards-file",
                    str(path),
                ],
                cwd=str(REPO),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                body = None
                for _ in range(50):
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:%s/board-cards" % port, timeout=0.2
                        ) as resp:
                            body = json.loads(resp.read().decode("utf-8"))
                            break
                    except (urllib.error.URLError, ConnectionError, TimeoutError):
                        if proc.poll() is not None:
                            self.fail("server exited with %s" % proc.returncode)
                        time.sleep(0.05)
                self.assertIsNotNone(body)
                self.assertEqual(body["cards"][0]["id"], "todo")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


class TestHttpEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.path = Path(cls._td.name) / "cards.json"
        cls._prev = server.CARDS_PATH
        server.CARDS_PATH = cls.path
        cls.httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
            ("127.0.0.1", 0), server.Handler
        )
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%s" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.CARDS_PATH = cls._prev
        cls._td.cleanup()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=2) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers), err.read()

    def test_missing_valid_and_corrupt_snapshots_and_no_store(self):
        if self.path.exists():
            self.path.unlink()
        status, headers, body = self._get("/board-cards")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers.get("Cache-Control", "").lower())
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload, {"version": 1, "cards": []})

        board_cards.publish_update(self.path, TODO_READY, static_root=REPO)
        status, headers, body = self._get("/board-cards")
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers.get("Cache-Control", "").lower())
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["cards"][0]["id"], "todo")

        self.path.write_text("{this is not json")
        status, headers, body = self._get("/board-cards")
        self.assertEqual(status, 503)
        self.assertIn("no-store", headers.get("Cache-Control", "").lower())
        err = json.loads(body.decode("utf-8"))
        self.assertIn("error", err)

    def test_existing_endpoints_still_work(self):
        for path in ("/state", "/config", "/mic"):
            status, _headers, body = self._get(path)
            self.assertEqual(status, 200, path)
            json.loads(body.decode("utf-8"))


class TestReadme(unittest.TestCase):
    def test_readme_documents_config_cli_and_stale_lock(self):
        text = (REPO / "README.md").read_text()
        self.assertIn("--cards-file", text)
        self.assertIn("board_cards_file", text)
        self.assertIn("board_cards.py", text)
        self.assertIn("publish", text)
        self.assertIn("clear", text)
        self.assertIn(".lock", text)
        self.assertIn("/board-cards", text)


if __name__ == "__main__":
    unittest.main()
