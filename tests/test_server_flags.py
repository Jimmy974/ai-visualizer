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
import socket
import subprocess
import sys
import time
import unittest
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


class RunningServer:
    """A server that is expected to keep running. Always --no-open, always
    killed on exit, so a test can never leave a process or a browser tab."""

    def __init__(self, argv_for_port):
        self.port = free_port()
        self.proc = subprocess.Popen(
            [sys.executable, SERVER, *argv_for_port(self.port)],
            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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


if __name__ == "__main__":
    unittest.main()
