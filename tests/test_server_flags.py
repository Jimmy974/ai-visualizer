#!/usr/bin/env python3
# Tests for server.py command-line flag handling.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
import subprocess
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
