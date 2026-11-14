#!/usr/bin/env python3
# Tests for server.py command-line flag handling.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = str(REPO / "server.py")


def run_server(*flags):
    # A bad flag must exit before serving; the timeout keeps a regression
    # (server starts and runs forever) from hanging the suite.
    return subprocess.run(
        [sys.executable, SERVER, "--no-open", "--port", "0", *flags],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_direct(*args, server=SERVER, cwd=REPO):
    """server.py --no-open <args> and nothing else: unlike run_server there is
    no --port 0 in front, so the flag under test is the only one of its kind."""
    return subprocess.run(
        [sys.executable, server, "--no-open", *args],
        cwd=cwd, capture_output=True, text=True, timeout=10,
    )


def http_status(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}",
                                    timeout=2) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


class PrintedAddress:
    """Start the server and read the line it prints on startup. Killed on
    exit, always --no-open."""

    def __init__(self, args, server=SERVER, cwd=REPO):
        self.proc = subprocess.Popen(
            [sys.executable, server, "--no-open", *args], cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        # A server that never prints must fail the test, not hang it.
        watchdog = threading.Timer(10, self.proc.kill)
        watchdog.start()
        try:
            self.line = self.proc.stdout.readline()
        finally:
            watchdog.cancel()
        self.ports = [int(n) for n in
                      re.findall(r"http://127\.0\.0\.1:(\d+)/", self.line)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.kill()
        self.proc.wait()
        self.proc.stdout.close()


class ConfigApp:
    """server.py (and the one module it imports) copied into a scratch folder
    with its own ai-visualizer.json, so a test can feed the server any config
    without ever writing to the repo's. Cleaned up by TemporaryDirectory."""

    def __init__(self, config):
        self.config = config

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for name in ("server.py", "board_cards.py"):
            shutil.copy(REPO / name, self.root / name)
        (self.root / "ai-visualizer.json").write_text(json.dumps(self.config))
        self.server = str(self.root / "server.py")
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def run(self, *args):
        return run_direct(*args, server=self.server, cwd=self.root)

    def serve(self, argv_for_port, port=None):
        return RunningServer(argv_for_port, port=port, server=self.server,
                             cwd=self.root)


class CleanErrorMixin:
    def assert_one_clean_line(self, r, *needles):
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        for needle in needles:
            self.assertIn(needle, r.stderr)


class RunningServer:
    """A server that is expected to keep running. Always --no-open, always
    killed on exit, so a test can never leave a process or a browser tab."""

    def __init__(self, argv_for_port, port=None, server=SERVER, cwd=REPO):
        self.port = free_port() if port is None else port
        self.proc = subprocess.Popen(
            [sys.executable, server, *argv_for_port(self.port)],
            cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def state(self, wait=8.0):
        """The /state value once the server answers, or None if it exited
        or never answered."""
        deadline = time.time() + wait
        url = f"http://127.0.0.1:{self.port}/state"
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return None
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    return json.load(r)["state"]
            except OSError:
                time.sleep(0.1)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.kill()
        self.proc.wait()


class CardsFileFlagTests(unittest.TestCase):
    def test_missing_value_at_end_exits_nonzero(self):
        r = run_server("--cards-file")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--cards-file", r.stderr)
        self.assertIn("expected one argument", r.stderr)

    def test_value_that_is_another_flag_exits_nonzero(self):
        r = run_server("--cards-file", "--mock")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--cards-file", r.stderr)


class MockFlagTests(unittest.TestCase):
    def test_unknown_state_exits_nonzero_and_names_the_flag(self):
        r = run_server("--mock", "bogus")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--mock", r.stderr)
        self.assertIn("bogus", r.stderr)
        for state in ("idle", "listening", "thinking", "speaking"):
            self.assertIn(state, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_valid_states_are_served(self):
        for state in ("idle", "listening", "thinking", "speaking"):
            with self.subTest(state=state):
                with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                              "--mock", state]) as srv:
                    self.assertEqual(srv.state(), state)

    def test_bare_mock_at_end_still_means_speaking(self):
        with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                      "--mock"]) as srv:
            self.assertEqual(srv.state(), "speaking")

    def test_bare_mock_before_another_flag_still_means_speaking(self):
        with RunningServer(lambda p: ["--port", str(p), "--mock",
                                      "--no-open"]) as srv:
            self.assertEqual(srv.state(), "speaking")


class PortFlagTests(unittest.TestCase):
    def assert_clean_port_error(self, r):
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--port", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_non_integer_port_is_a_clean_error(self):
        # run_server puts --port 0 first and argv.index finds that one, so
        # run_bad_port calls the server directly: the bad value is the only
        # --port.
        for bad in ("abc", "80x", "1.5", "-1", ""):
            with self.subTest(port=bad):
                self.assert_clean_port_error(self.run_bad_port(bad))

    def test_out_of_range_port_is_rejected(self):
        for bad in ("65536", "99999999"):
            with self.subTest(port=bad):
                self.assert_clean_port_error(self.run_bad_port(bad))

    def test_port_with_no_value_is_rejected(self):
        r = subprocess.run([sys.executable, SERVER, "--no-open", "--port"],
                           cwd=REPO, capture_output=True, text=True, timeout=10)
        self.assert_clean_port_error(r)
        r = subprocess.run([sys.executable, SERVER, "--port", "--no-open"],
                           cwd=REPO, capture_output=True, text=True, timeout=10)
        self.assert_clean_port_error(r)

    def test_port_zero_is_still_valid(self):
        with RunningServer(lambda p: ["--no-open", "--port", "0",
                                      "--mock", "idle"]) as srv:
            time.sleep(1.0)
            self.assertIsNone(srv.proc.poll())

    @staticmethod
    def run_bad_port(value):
        return subprocess.run(
            [sys.executable, SERVER, "--no-open", "--port", value],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )


class EqualsFormTests(CleanErrorMixin, unittest.TestCase):
    """--flag=value must mean exactly what --flag value means."""

    def test_port_and_mock_equals_form_are_honoured(self):
        with RunningServer(lambda p: ["--no-open", f"--port={p}",
                                      "--mock=idle"]) as srv:
            self.assertEqual(srv.state(), "idle")

    def test_every_mock_state_in_equals_form(self):
        for state in ("idle", "listening", "thinking", "speaking"):
            with self.subTest(state=state):
                with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                              f"--mock={state}"]) as srv:
                    self.assertEqual(srv.state(), state)

    def test_mock_equals_unknown_state_is_a_clean_error(self):
        self.assert_one_clean_line(run_server("--mock=bogus"),
                                   "--mock", "bogus", "idle", "speaking")

    def test_mock_equals_empty_is_an_error_not_bare(self):
        # "--mock=" is an explicit empty value, not the bare "--mock" that
        # means speaking. A server that started would hit the 10 s timeout.
        r = run_server("--mock=")
        self.assert_one_clean_line(r, "--mock", "invalid state ''")

    def test_port_equals_bad_values_are_clean_errors(self):
        for bad in ("abc", "80x", "1.5", "-1", "", "65536", "99999999"):
            with self.subTest(port=bad):
                self.assert_one_clean_line(run_direct(f"--port={bad}"),
                                           "--port", "invalid port",
                                           repr(bad))

    def test_port_equals_empty_does_not_start_a_server(self):
        # Silently ignored it would fall back to the configured port (8790).
        r = run_direct("--port=", "--mock", "idle")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("ai-visualizer on", r.stdout)

    def test_overlong_digit_string_is_a_clean_error(self):
        # int() of a 5000-digit string raises ValueError on its own.
        for form in (["--port", "9" * 5000], ["--port=" + "9" * 5000]):
            with self.subTest(equals_form="=" in form[0]):
                r = run_direct(*form)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn("Traceback", r.stderr)
                self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_port_with_leading_zeros_is_still_accepted(self):
        with RunningServer(lambda p: ["--no-open", f"--port=000{p}",
                                      "--mock", "idle"]) as srv:
            self.assertEqual(srv.state(), "idle")

    def test_cards_file_equals_form_is_honoured(self):
        # A snapshot that is not JSON makes /board-cards answer 503. The
        # default snapshot path would answer 200 (or an empty list).
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "cards.json"
            bad.write_text("{not json")
            with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                          "--mock", "idle",
                                          f"--cards-file={bad}"]) as srv:
                self.assertEqual(srv.state(), "idle")
                self.assertEqual(http_status(srv.port, "/board-cards"), 503)

    def test_cards_file_equals_form_is_checked_like_the_space_form(self):
        # A path under the static root is refused. Honoured, so it is refused.
        for form in (["--cards-file", "README.md"], ["--cards-file=README.md"]):
            with self.subTest(form=form[0]):
                r = run_server(*form)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("static root", r.stdout + r.stderr)

    def test_cards_file_empty_value_is_an_error_in_both_forms(self):
        for form in (["--cards-file", ""], ["--cards-file="]):
            with self.subTest(form=form[0]):
                self.assert_one_clean_line(run_server(*form),
                                           "--cards-file", "non-empty path")


class RepeatedFlagTests(CleanErrorMixin, unittest.TestCase):
    """A repeated flag: the last occurrence wins, and every occurrence is
    still checked, in either form."""

    def test_last_valid_port_wins(self):
        for form in (
            lambda a, b: ["--port", str(a), "--port", str(b)],
            lambda a, b: ["--port", str(a), f"--port={b}"],
            lambda a, b: [f"--port={a}", "--port", str(b)],
            lambda a, b: [f"--port={a}", f"--port={b}"],
        ):
            with self.subTest(form=form(1, 2)):
                first = free_port()
                with RunningServer(
                        lambda last: ["--no-open", *form(first, last),
                                      "--mock", "idle"]) as srv:
                    self.assertEqual(srv.state(), "idle")

    def test_last_valid_mock_wins(self):
        for argv in (["--mock", "speaking", "--mock", "idle"],
                     ["--mock=thinking", "--mock=idle"],
                     ["--mock", "speaking", "--mock=idle"],
                     ["--mock=speaking", "--mock", "idle"]):
            with self.subTest(argv=argv):
                with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                              *argv]) as srv:
                    self.assertEqual(srv.state(), "idle")

    def test_last_bare_mock_means_speaking(self):
        with RunningServer(lambda p: ["--no-open", "--port", str(p),
                                      "--mock", "idle", "--mock"]) as srv:
            self.assertEqual(srv.state(), "speaking")

    def test_valid_mock_after_a_bare_one_wins(self):
        with RunningServer(lambda p: ["--port", str(p), "--mock",
                                      "--mock", "idle", "--no-open"]) as srv:
            self.assertEqual(srv.state(), "idle")

    def test_last_invalid_mock_fails(self):
        for argv in (["--mock", "idle", "--mock", "bogus"],
                     ["--mock", "idle", "--mock=bogus"],
                     ["--mock=idle", "--mock="]):
            with self.subTest(argv=argv):
                self.assert_one_clean_line(run_server(*argv), "--mock")

    def test_earlier_invalid_mock_fails_too(self):
        for argv in (["--mock", "bogus", "--mock", "idle"],
                     ["--mock=bogus", "--mock=idle"]):
            with self.subTest(argv=argv):
                self.assert_one_clean_line(run_server(*argv), "--mock",
                                           "bogus")

    def test_last_invalid_port_fails(self):
        # Both ports are real flags here: the bad one is last, so it counts.
        for argv in (["--port", "0", "--port", "abc"],
                     ["--port", "0", "--port=abc"],
                     ["--port=0", "--port="],
                     ["--port", "0", "--port", "65536"]):
            with self.subTest(argv=argv):
                self.assert_one_clean_line(run_direct(*argv, "--mock", "idle"),
                                           "--port", "invalid port")

    def test_earlier_invalid_port_fails_too(self):
        for argv in (["--port", "abc", "--port", "0"],
                     ["--port=abc", "--port=0"]):
            with self.subTest(argv=argv):
                self.assert_one_clean_line(run_direct(*argv, "--mock", "idle"),
                                           "--port", "'abc'")

    def test_any_occurrence_missing_its_value_fails(self):
        for argv in (["--port", "0", "--port"],
                     ["--port", "--port", "0"],
                     ["--port", "--port=0"]):
            with self.subTest(argv=argv):
                self.assert_one_clean_line(run_direct(*argv, "--mock", "idle"),
                                           "--port", "expected one argument")

    def test_repeated_cards_file_last_wins_and_all_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json")
            missing = Path(tmp) / "none.json"       # absent file: 200, empty
            for first, last, want in ((bad, missing, 200), (missing, bad, 503)):
                with self.subTest(last=last.name):
                    with RunningServer(
                            lambda p: ["--no-open", "--port", str(p),
                                       "--mock", "idle",
                                       "--cards-file", str(first),
                                       f"--cards-file={last}"]) as srv:
                        self.assertEqual(srv.state(), "idle")
                        self.assertEqual(
                            http_status(srv.port, "/board-cards"), want)
        self.assert_one_clean_line(
            run_server("--cards-file", "x.json", "--cards-file"),
            "--cards-file", "expected one argument")


class ConfigPortTests(CleanErrorMixin, unittest.TestCase):
    """The "port" in ai-visualizer.json. Every test runs against a scratch
    copy of the app, never the repo's own config."""

    BAD = ("abc", None, True, False, 1.5, 8790.0, 70000, -1, "", "80x",
           "-1", "65536", [], {}, ["8790"], "\uff18\uff17\uff19\uff10",
           "9" * 5000)

    def test_bad_config_port_is_one_clean_line_naming_the_file(self):
        for bad in self.BAD:
            with self.subTest(port=bad if not isinstance(bad, str)
                              else bad[:20]):
                with ConfigApp({"port": bad}) as app:
                    r = app.run("--mock", "idle")
                self.assert_one_clean_line(r, "ai-visualizer.json", '"port"',
                                           "expected an integer from 0 to "
                                           "65535", "--port")

    def test_error_shows_the_value_the_way_json_writes_it(self):
        for bad, shown in (("abc", "'abc'"), (None, "null"), (True, "true"),
                           (1.5, "1.5"), (70000, "70000")):
            with self.subTest(port=bad):
                with ConfigApp({"port": bad}) as app:
                    r = app.run("--mock", "idle")
                self.assertIn(f'invalid "port" {shown} (', r.stderr)

    def test_port_flag_overrides_a_bad_config_port(self):
        for bad in ("abc", None, True, 1.5, 70000):
            for form in (lambda p: ["--port", str(p)],
                         lambda p: [f"--port={p}"]):
                with self.subTest(port=bad, form=form(1)[0][:6]):
                    with ConfigApp({"port": bad}) as app:
                        with app.serve(lambda p: ["--no-open", *form(p),
                                                  "--mock", "idle"]) as srv:
                            self.assertEqual(srv.state(), "idle")

    def test_valid_config_ports_are_used_without_a_port_flag(self):
        for as_config in (lambda p: p, lambda p: str(p)):
            port = free_port()
            with self.subTest(port=type(as_config(port)).__name__):
                with ConfigApp({"port": as_config(port)}) as app:
                    with app.serve(lambda p: ["--no-open", "--mock", "idle"],
                                   port=port) as srv:
                        self.assertEqual(srv.state(), "idle")

    def test_config_port_zero_is_valid_and_prints_a_real_port(self):
        with ConfigApp({"port": 0}) as app:
            with PrintedAddress(["--mock", "idle"], server=app.server,
                                cwd=app.root) as srv:
                self.assertTrue(srv.ports, srv.line)
                self.assertNotIn(0, srv.ports)

    def test_a_bad_config_port_is_not_reached_when_another_flag_is_bad(self):
        # Flags are checked first; their message is the one the user sees.
        with ConfigApp({"port": "abc"}) as app:
            r = app.run("--mock", "bogus")
        self.assert_one_clean_line(r, "--mock", "bogus")
        self.assertNotIn("ai-visualizer.json", r.stderr)


class PortZeroTests(unittest.TestCase):
    """--port 0 asks the OS for a free port. The address printed (and the
    one the browser is sent to) must be the one actually bound."""

    def check(self, args):
        with PrintedAddress(args) as srv:
            self.assertTrue(srv.ports, f"no address in {srv.line!r}")
            self.assertNotIn(0, srv.ports, srv.line)
            self.assertEqual(len(set(srv.ports)), 1, srv.line)
            port = srv.ports[0]
            self.assertEqual(http_status(port, "/state"), 200)

    def test_port_zero_prints_a_real_port_that_answers(self):
        self.check(["--port", "0", "--mock", "idle"])

    def test_port_equals_zero_prints_a_real_port_that_answers(self):
        self.check(["--port=0", "--mock=idle"])


if __name__ == "__main__":
    unittest.main()
