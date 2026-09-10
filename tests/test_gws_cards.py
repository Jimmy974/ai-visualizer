#!/usr/bin/env python3
# Tests for gws → board-card normalization (verified Sinner gws shapes).
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import board_cards  # noqa: E402
import gws_cards  # noqa: E402

AT = "2026-09-10T17:00:00Z"


def _run(*args, stdin=""):
    return subprocess.run(
        [sys.executable, str(REPO / "gws_cards.py"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


class TestGwsNoiseAndTasks(unittest.TestCase):
    def test_strips_keyring_line_and_normalizes_incomplete_tasks(self):
        raw = (
            "Using keyring backend: keyring\n"
            + json.dumps({
                "kind": "tasks#tasks",
                "items": [
                    {
                        "kind": "tasks#task",
                        "id": "task-open-1",
                        "title": "Open without due",
                        "status": "needsAction",
                        "updated": "2026-09-10T11:17:08.779Z",
                    },
                    {
                        "kind": "tasks#task",
                        "id": "task-done",
                        "title": "Already done",
                        "status": "completed",
                        "due": "2026-03-29T00:00:00.000Z",
                    },
                    {
                        "kind": "tasks#task",
                        "id": "task-due",
                        "title": "Date-only due",
                        "status": "needsAction",
                        "due": "2026-03-29T00:00:00.000Z",
                    },
                ],
            })
        )
        card = gws_cards.normalize_tasks(gws_cards.parse_gws_json(raw), attempted_at=AT)
        self.assertEqual(card["id"], "todo")
        self.assertEqual(card["status"], "ready")
        self.assertEqual(card["attemptedAt"], AT)
        self.assertEqual(card["updatedAt"], AT)
        ids = [i["id"] for i in card["items"]]
        self.assertEqual(ids, ["task-open-1", "task-due"])
        self.assertNotIn("dueDate", card["items"][0])
        self.assertEqual(card["items"][1]["dueDate"], "2026-03-29")
        self.assertEqual(card["totalCount"], 2)

    def test_multiple_lists_preserve_order_and_count_scope(self):
        payload = {
            "tasklists": [
                {
                    "id": "list-a",
                    "title": "List A",
                    "items": [
                        {"id": "a1", "title": "A1", "status": "needsAction"},
                        {"id": "a2", "title": "A2", "status": "completed"},
                    ],
                },
                {
                    "id": "list-b",
                    "title": "List B",
                    "items": [
                        {"id": "b1", "title": "B1", "status": "needsAction"},
                    ],
                },
            ]
        }
        card = gws_cards.normalize_tasks(payload, attempted_at=AT)
        self.assertEqual([i["id"] for i in card["items"]], ["a1", "b1"])
        self.assertEqual(card["totalCount"], 2)

    def test_empty_tasks_are_successful_empty(self):
        card = gws_cards.normalize_tasks({"kind": "tasks#tasks", "items": []}, attempted_at=AT)
        self.assertEqual(card["items"], [])
        self.assertEqual(card["totalCount"], 0)
        self.assertEqual(card["status"], "ready")


class TestGwsCalendar(unittest.TestCase):
    def test_raw_events_list_all_day_and_offset_timestamps(self):
        payload = {
            "kind": "calendar#events",
            "timeZone": "Europe/London",
            "items": [
                {
                    "id": "all-day-1",
                    "status": "confirmed",
                    "summary": "Bank holiday",
                    "start": {"date": "2026-03-29"},
                    "end": {"date": "2026-03-30"},
                },
                {
                    "id": "timed-1",
                    "status": "confirmed",
                    "summary": "Call",
                    "start": {
                        "dateTime": "2026-03-29T00:30:00+00:00",
                        "timeZone": "Europe/London",
                    },
                    "end": {
                        "dateTime": "2026-03-29T02:30:00+00:00",
                        "timeZone": "Europe/London",
                    },
                },
                {
                    "id": "cancelled-1",
                    "status": "cancelled",
                    "summary": "Nope",
                    "start": {"date": "2026-03-29"},
                    "end": {"date": "2026-03-30"},
                },
            ],
        }
        card = gws_cards.normalize_events(
            payload,
            range_start="2026-03-29",
            range_end="2026-03-30",
            timezone="Europe/London",
            attempted_at=AT,
        )
        self.assertEqual(card["id"], "calendar")
        self.assertEqual(card["range"], {"start": "2026-03-29", "end": "2026-03-30"})
        self.assertEqual(card["timezone"], "Europe/London")
        self.assertEqual(card["totalCount"], 2)
        self.assertEqual(card["items"][0]["allDay"], True)
        self.assertEqual(card["items"][0]["startDate"], "2026-03-29")
        self.assertEqual(card["items"][0]["endDate"], "2026-03-30")
        self.assertEqual(card["items"][1]["allDay"], False)
        self.assertEqual(card["items"][1]["start"], "2026-03-29T00:30:00+00:00")
        self.assertEqual(card["items"][1]["end"], "2026-03-29T02:30:00+00:00")
        self.assertEqual([i["id"] for i in card["items"]], ["all-day-1", "timed-1"])

    def test_agenda_helper_shape_and_multiple_calendars(self):
        payload = {
            "count": 2,
            "timeMin": "2026-09-10T00:00:00+01:00",
            "timeMax": "2026-09-11T00:00:00+01:00",
            "events": [
                {
                    "calendar": "Work",
                    "summary": "Standup",
                    "start": "2026-09-10T11:00:00+01:00",
                    "end": "2026-09-10T12:15:00+01:00",
                    "location": "Gym",
                },
                {
                    "calendar": "Holidays",
                    "summary": "Day off",
                    "start": "2026-09-10",
                    "end": "2026-09-11",
                },
            ],
        }
        card = gws_cards.normalize_events(
            payload,
            range_start="2026-09-10",
            range_end="2026-09-11",
            timezone="Europe/London",
            attempted_at=AT,
        )
        self.assertEqual(card["totalCount"], 2)
        self.assertTrue(card["items"][0]["allDay"])
        self.assertFalse(card["items"][1]["allDay"])
        self.assertTrue(card["items"][0]["id"])
        self.assertTrue(card["items"][1]["id"])

    def test_default_today_range_and_30_day_fallback(self):
        today = gws_cards.calendar_window(
            today="2026-09-10",
            timezone="Europe/London",
            today_count=2,
            fallback_count=0,
        )
        self.assertEqual(today, {"start": "2026-09-10", "end": "2026-09-11"})
        empty_today = gws_cards.calendar_window(
            today="2026-09-10",
            timezone="Europe/London",
            today_count=0,
            fallback_count=5,
        )
        self.assertEqual(empty_today, {"start": "2026-09-10", "end": "2026-10-10"})
        explicit = gws_cards.calendar_window(
            today="2026-09-10",
            timezone="Europe/London",
            today_count=0,
            fallback_count=0,
            explicit_start="2026-03-29",
            explicit_end="2026-03-30",
        )
        self.assertEqual(explicit, {"start": "2026-03-29", "end": "2026-03-30"})

    def test_empty_calendar_still_has_range_and_timezone(self):
        card = gws_cards.normalize_events(
            {"items": []},
            range_start="2026-09-10",
            range_end="2026-09-11",
            timezone="Europe/London",
            attempted_at=AT,
        )
        self.assertEqual(card["items"], [])
        self.assertEqual(card["totalCount"], 0)
        self.assertEqual(card["range"]["start"], "2026-09-10")
        self.assertEqual(card["timezone"], "Europe/London")


class TestLoadingErrorAndCli(unittest.TestCase):
    def test_loading_and_sanitized_error_payloads(self):
        loading = gws_cards.loading_update("calendar", AT)
        self.assertEqual(loading, {
            "id": "calendar",
            "status": "loading",
            "attemptedAt": AT,
        })
        err = gws_cards.error_update(
            "todo",
            AT,
            "failed reading /Users/jimmywong/.config/gws/client_secret.json token=ya29.secret",
        )
        self.assertEqual(err["status"], "error")
        self.assertNotIn("ya29", err["message"])
        self.assertNotIn("client_secret", err["message"])
        self.assertIn("failed", err["message"].lower())

    def test_cli_and_single_source_preserves_other_card(self):
        todo_in = json.dumps({
            "items": [{"id": "t1", "title": "Milk", "status": "needsAction"}],
        })
        proc = _run("tasks", "--attempted-at", AT, stdin=todo_in)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        todo_card = json.loads(proc.stdout)
        cal_in = json.dumps({
            "items": [{
                "id": "e1",
                "status": "confirmed",
                "summary": "Call",
                "start": {"dateTime": "2026-09-10T11:00:00+01:00", "timeZone": "Europe/London"},
                "end": {"dateTime": "2026-09-10T12:15:00+01:00", "timeZone": "Europe/London"},
            }]
        })
        proc = _run(
            "events",
            "--attempted-at", AT,
            "--timezone", "Europe/London",
            "--range-start", "2026-09-10",
            "--range-end", "2026-09-11",
            stdin=cal_in,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cal_card = json.loads(proc.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cards.json"
            board_cards.publish_update(path, todo_card, static_root=REPO)
            board_cards.publish_update(path, cal_card, static_root=REPO)
            only_todo = json.loads(json.dumps(todo_card))
            only_todo["attemptedAt"] = "2026-09-10T18:00:00Z"
            only_todo["updatedAt"] = "2026-09-10T18:00:00Z"
            only_todo["items"] = [{"id": "t9", "title": "Only todo"}]
            only_todo["totalCount"] = 1
            board_cards.publish_update(path, only_todo, static_root=REPO)
            snap, _ = board_cards.load_snapshot(path)
            ids = {c["id"]: c for c in snap["cards"]}
            self.assertEqual(ids["todo"]["items"][0]["id"], "t9")
            self.assertEqual(ids["calendar"]["items"][0]["id"], "e1")

            err_proc = _run(
                "error", "--card", "calendar", "--attempted-at",
                "2026-09-10T18:01:00Z", "--message", "Google request failed",
            )
            self.assertEqual(err_proc.returncode, 0, err_proc.stderr)
            board_cards.publish_update(path, json.loads(err_proc.stdout), static_root=REPO)
            snap, _ = board_cards.load_snapshot(path)
            ids = {c["id"]: c for c in snap["cards"]}
            self.assertEqual(ids["calendar"]["status"], "error")
            self.assertEqual(ids["calendar"]["items"][0]["id"], "e1")
            self.assertEqual(ids["calendar"]["range"]["start"], "2026-09-10")
            self.assertEqual(ids["todo"]["items"][0]["id"], "t9")

            clr = subprocess.run(
                [sys.executable, str(REPO / "board_cards.py"),
                 "--cards-file", str(path), "clear", "--card", "todo"],
                capture_output=True, text=True, cwd=str(REPO),
            )
            self.assertEqual(clr.returncode, 0, clr.stderr)
            snap, _ = board_cards.load_snapshot(path)
            self.assertEqual([c["id"] for c in snap["cards"]], ["calendar"])

    def test_handoff_doc_and_readme_name_gws_and_cards_file(self):
        handoff = (REPO / "docs" / "agents" / "board-info-cards.md").read_text()
        readme = (REPO / "README.md").read_text()
        self.assertIn("gws", handoff)
        self.assertIn("--cards-file", handoff)
        self.assertIn("board_cards.py", handoff)
        self.assertIn(" publish", handoff)
        self.assertIn("clear --card", handoff)
        self.assertIn("load", handoff.lower())
        self.assertIn("docs/agents/board-info-cards.md", readme)
        self.assertIn("--cards-file", readme)


if __name__ == "__main__":
    unittest.main()
