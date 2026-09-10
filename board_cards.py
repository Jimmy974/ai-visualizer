#!/usr/bin/env python3
# ai-visualizer: give your AI agent a face.
# Copyright (C) 2026 Jared Rhodenizer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Board card snapshot storage, validation, and CLI.

Persists Todo and Calendar cards as a version-1 JSON snapshot served at
GET /board-cards. Writes use an exclusive sidecar lock file (O_CREAT|O_EXCL)
held for at most LOCK_TIMEOUT_S seconds. Locks are never stolen after a
crash: if a *.lock sidecar remains, confirm no publisher is running, then
delete that lock file by hand to recover.
"""
import argparse
import datetime
import errno
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = 1
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_ITEMS = 100
MAX_TITLE_CHARS = 500
MAX_ERROR_MESSAGE_CHARS = 200
LOCK_TIMEOUT_S = 5
CARD_IDS = ("todo", "calendar")
STATUSES = ("loading", "ready", "error")
DEFAULT_CARDS_FILE = "~/.local/share/ai-visualizer/board-cards.json"

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RFC3339_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?"
    r"(Z|[+-]\d{2}:\d{2})$"
)
_TAG_RE = re.compile(r"<[^>]*>")


class ValidationError(Exception):
    pass


class StaleUpdateError(Exception):
    pass


class LockTimeout(Exception):
    pass


class CorruptStorageError(Exception):
    pass


class StaticRootError(Exception):
    pass


def empty_snapshot():
    return {"version": VERSION, "cards": []}


def load_visualizer_config(repo_root=None):
    root = Path(repo_root) if repo_root is not None else HERE
    try:
        data = json.loads((root / "ai-visualizer.json").read_text())
    except FileNotFoundError:
        return {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_cards_path(cli_path=None, config_path=None, repo_root=None):
    root = Path(repo_root) if repo_root is not None else HERE
    if cli_path:
        raw = cli_path
    elif config_path:
        raw = config_path
    else:
        raw = DEFAULT_CARDS_FILE
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def is_under_static_root(path, static_root=None):
    static = Path(static_root if static_root is not None else HERE).resolve()
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(static)
        return True
    except ValueError:
        return False


def refuse_under_static_root(path, static_root=None):
    if is_under_static_root(path, static_root):
        raise StaticRootError(
            "cards file %s resolves under the static root; refusing to use "
            "a path that could be served as a static file" % path
        )


def parse_rfc3339(value):
    if not isinstance(value, str):
        raise ValidationError("timestamp must be a string")
    match = _RFC3339_RE.fullmatch(value)
    if not match:
        raise ValidationError("malformed RFC 3339 timestamp: %r" % value)
    year, month, day, hour, minute, second, frac, off = match.groups()
    try:
        date = datetime.date(int(year), int(month), int(day))
    except ValueError:
        raise ValidationError("invalid calendar date in timestamp: %r" % value)
    hour, minute, second = int(hour), int(minute), int(second)
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValidationError("invalid clock time in timestamp: %r" % value)
    micro = 0
    if frac:
        micro = int(frac[:6].ljust(6, "0"))
    if off == "Z":
        tz = datetime.timezone.utc
    else:
        sign = 1 if off[0] == "+" else -1
        off_h, off_m = int(off[1:3]), int(off[4:6])
        if not (0 <= off_h <= 23 and 0 <= off_m <= 59):
            raise ValidationError("invalid UTC offset: %r" % off)
        tz = datetime.timezone(
            sign * datetime.timedelta(hours=off_h, minutes=off_m)
        )
    return datetime.datetime(
        date.year, date.month, date.day, hour, minute, second, micro, tzinfo=tz
    )


def _as_utc(value):
    return parse_rfc3339(value).astimezone(datetime.timezone.utc)


def parse_calendar_date(value, field="date"):
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValidationError("%s must be YYYY-MM-DD" % field)
    try:
        return datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        raise ValidationError(
            "%s is not a real Gregorian date: %r" % (field, value)
        )


def parse_timezone(value):
    if not isinstance(value, str):
        raise ValidationError("timezone must be a string")
    name = value.strip()
    if not name:
        raise ValidationError("timezone must be a non-empty IANA name")
    return name


def parse_range(value):
    if not isinstance(value, dict):
        raise ValidationError("range must be an object")
    if "start" not in value or "end" not in value:
        raise ValidationError("range requires start and end")
    start = parse_calendar_date(value["start"], "range.start")
    end = parse_calendar_date(value["end"], "range.end")
    if end <= start:
        raise ValidationError(
            "range end must be an exclusive date later than start"
        )
    return {"start": value["start"], "end": value["end"]}


def _parse_title(value):
    if not isinstance(value, str):
        raise ValidationError("title must be a string")
    if "\x00" in value:
        raise ValidationError("title contains NUL")
    if len(value) > MAX_TITLE_CHARS:
        raise ValidationError("title exceeds 500 characters")
    if value.strip() == "":
        raise ValidationError("title must be non-empty")
    return value


def _parse_item_id(value):
    if not isinstance(value, str) or value.strip() == "":
        raise ValidationError("item id must be a non-empty string")
    return value


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def sanitize_message(value):
    if not isinstance(value, str):
        raise ValidationError("error message must be a string")
    text = _TAG_RE.sub("", value.replace("\x00", ""))
    text = " ".join(text.split())
    if not text:
        raise ValidationError("error message must be non-empty")
    if len(text) > MAX_ERROR_MESSAGE_CHARS:
        text = text[:MAX_ERROR_MESSAGE_CHARS].rstrip()
    return text


def _parse_todo_item(item):
    if not isinstance(item, dict):
        raise ValidationError("todo item must be an object")
    out = {"id": _parse_item_id(item.get("id")), "title": _parse_title(item.get("title"))}
    due = item.get("dueDate", None)
    if due is not None:
        parse_calendar_date(due, "dueDate")
        out["dueDate"] = due
    return out


def _parse_calendar_item(item):
    if not isinstance(item, dict):
        raise ValidationError("calendar item must be an object")
    all_day = item.get("allDay")
    if not isinstance(all_day, bool):
        raise ValidationError("allDay must be a boolean")
    out = {
        "id": _parse_item_id(item.get("id")),
        "title": _parse_title(item.get("title")),
        "allDay": all_day,
    }
    if all_day:
        if "start" in item or "end" in item:
            raise ValidationError("all-day items must not include start/end instants")
        start = parse_calendar_date(item.get("startDate"), "startDate")
        end = parse_calendar_date(item.get("endDate"), "endDate")
        if end <= start:
            raise ValidationError(
                "all-day endDate must be exclusive and later than startDate"
            )
        out["startDate"] = item["startDate"]
        out["endDate"] = item["endDate"]
    else:
        if "startDate" in item or "endDate" in item:
            raise ValidationError("timed items must not include startDate/endDate")
        start = parse_rfc3339(item.get("start"))
        end = parse_rfc3339(item.get("end"))
        if end <= start:
            raise ValidationError("timed event end must be later than start")
        out["start"] = item["start"]
        out["end"] = item["end"]
    return out


def _parse_items(card_id, items):
    if not isinstance(items, list):
        raise ValidationError("items must be an array")
    if len(items) > MAX_ITEMS:
        raise ValidationError("more than 100 items")
    parser = _parse_todo_item if card_id == "todo" else _parse_calendar_item
    parsed = []
    seen = set()
    for item in items:
        parsed_item = parser(item)
        if parsed_item["id"] in seen:
            raise ValidationError("duplicate item id")
        seen.add(parsed_item["id"])
        parsed.append(parsed_item)
    return parsed


def _parse_total_count(value, n_items):
    if not _is_int(value) or value < n_items:
        raise ValidationError("totalCount must be an integer >= number of items")
    return value


def validate_update(payload):
    if not isinstance(payload, dict):
        raise ValidationError("card update must be a JSON object")
    if "version" in payload and payload.get("version") != VERSION:
        raise ValidationError("unsupported snapshot version")
    card_id = payload.get("id")
    if card_id not in CARD_IDS:
        raise ValidationError("id must be todo or calendar")
    status = payload.get("status")
    if status not in STATUSES:
        raise ValidationError("status must be loading, ready, or error")
    parse_rfc3339(payload.get("attemptedAt"))
    out = {
        "id": card_id,
        "status": status,
        "attemptedAt": payload["attemptedAt"],
    }
    if status == "ready":
        items = _parse_items(card_id, payload.get("items"))
        out["items"] = items
        out["totalCount"] = _parse_total_count(payload.get("totalCount"), len(items))
        parse_rfc3339(payload.get("updatedAt"))
        out["updatedAt"] = payload["updatedAt"]
        if card_id == "calendar":
            if "range" not in payload or "timezone" not in payload:
                raise ValidationError(
                    "calendar ready updates require range and timezone"
                )
            out["range"] = parse_range(payload.get("range"))
            out["timezone"] = parse_timezone(payload.get("timezone"))
    elif status == "error":
        out["message"] = sanitize_message(payload.get("message"))
    return out


def _validate_stored_card(card):
    if not isinstance(card, dict):
        raise ValidationError("card must be an object")
    card_id = card.get("id")
    if card_id not in CARD_IDS:
        raise ValidationError("invalid card id")
    status = card.get("status")
    if status not in STATUSES:
        raise ValidationError("invalid status")
    parse_rfc3339(card.get("attemptedAt"))
    out = {
        "id": card_id,
        "status": status,
        "attemptedAt": card["attemptedAt"],
    }
    if status == "error":
        out["message"] = sanitize_message(card.get("message"))
    has_items = "items" in card or "updatedAt" in card or "totalCount" in card
    if status == "ready" or has_items:
        items = _parse_items(card_id, card.get("items"))
        out["items"] = items
        out["totalCount"] = _parse_total_count(card.get("totalCount"), len(items))
        parse_rfc3339(card.get("updatedAt"))
        out["updatedAt"] = card["updatedAt"]
    if card_id == "calendar":
        if status == "ready":
            out["range"] = parse_range(card.get("range"))
            out["timezone"] = parse_timezone(card.get("timezone"))
        else:
            if "range" in card:
                out["range"] = parse_range(card.get("range"))
            if "timezone" in card:
                out["timezone"] = parse_timezone(card.get("timezone"))
    return out


def validate_snapshot(data):
    try:
        if not isinstance(data, dict):
            raise ValidationError("snapshot must be an object")
        if data.get("version") != VERSION:
            raise ValidationError("unsupported snapshot version")
        cards = data.get("cards")
        if not isinstance(cards, list):
            raise ValidationError("cards must be an array")
        seen = set()
        out_cards = []
        for card in cards:
            stored = _validate_stored_card(card)
            if stored["id"] in seen:
                raise ValidationError("duplicate card id")
            seen.add(stored["id"])
            out_cards.append(stored)
        return {"version": VERSION, "cards": out_cards}
    except ValidationError as exc:
        raise CorruptStorageError(str(exc))


def load_snapshot(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return empty_snapshot(), None
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise CorruptStorageError("stored document exceeds 256 KiB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CorruptStorageError("stored document is not valid JSON")
    return validate_snapshot(data), raw


def merge_update(snapshot, update):
    cards = list(snapshot.get("cards") or [])
    existing = None
    index = None
    for i, card in enumerate(cards):
        if card.get("id") == update["id"]:
            existing = card
            index = i
            break
    if existing is not None:
        if _as_utc(update["attemptedAt"]) < _as_utc(existing["attemptedAt"]):
            raise StaleUpdateError(
                "update is older than the stored attemptedAt for %s" % update["id"]
            )
    merged = dict(update)
    if update["status"] in ("loading", "error") and existing is not None:
        for key in ("updatedAt", "items", "totalCount", "range", "timezone"):
            if key in existing:
                merged[key] = existing[key]
        if update["status"] == "error":
            merged["message"] = update["message"]
    if index is None:
        cards.append(merged)
        order = {name: i for i, name in enumerate(CARD_IDS)}
        cards.sort(key=lambda card: order.get(card["id"], 99))
    else:
        cards[index] = merged
    return {"version": VERSION, "cards": cards}


def _best_effort_owner_only(path):
    if os.name != "posix":
        return
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass


def _atomic_write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        _best_effort_owner_only(tmp_path)
        os.replace(str(tmp_path), str(path))
        tmp_path = None
        _best_effort_owner_only(path)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _dump(snapshot):
    blob = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(blob) > MAX_DOCUMENT_BYTES:
        raise ValidationError("stored document would exceed 256 KiB")
    return blob


@contextmanager
def writer_lock(path):
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    fd = None
    acquired = False
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            acquired = True
            break
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            if time.monotonic() >= deadline:
                raise LockTimeout(
                    "timed out after %ss waiting for %s; if no writer is "
                    "running, remove the stale lock file" % (LOCK_TIMEOUT_S, lock_path)
                )
            time.sleep(0.05)
    try:
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
        except OSError:
            pass
        _best_effort_owner_only(lock_path)
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if acquired:
            try:
                os.unlink(str(lock_path))
            except OSError:
                pass


def publish_update(path, payload, static_root=None):
    path = Path(path)
    refuse_under_static_root(path, static_root)
    update = validate_update(payload)
    with writer_lock(path):
        snapshot, _raw = load_snapshot(path)
        merged = merge_update(snapshot, update)
        _atomic_write_bytes(path, _dump(merged))
    return merged


def clear_cards(path, which, static_root=None):
    if which not in ("todo", "calendar", "all"):
        raise ValidationError("card must be todo, calendar, or all")
    path = Path(path)
    refuse_under_static_root(path, static_root)
    with writer_lock(path):
        snapshot, _raw = load_snapshot(path)
        if which == "all":
            cards = []
        else:
            cards = [card for card in snapshot["cards"] if card["id"] != which]
        merged = {"version": VERSION, "cards": cards}
        _atomic_write_bytes(path, _dump(merged))
    return merged


def http_get_payload(path):
    try:
        snapshot, raw = load_snapshot(path)
        if raw is None:
            return 200, empty_snapshot()
        return 200, snapshot
    except (CorruptStorageError, ValidationError, OSError):
        return 503, {"error": "board cards storage is invalid"}


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Publish or clear board info cards.",
    )
    parser.add_argument("--cards-file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("publish", help="Read one card update from stdin.")
    clear_p = sub.add_parser("clear", help="Remove saved board card content.")
    clear_p.add_argument("--card", required=True, choices=["todo", "calendar", "all"])
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    cfg = load_visualizer_config(HERE)
    try:
        path = resolve_cards_path(args.cards_file, cfg.get("board_cards_file"), HERE)
        refuse_under_static_root(path, HERE)
        if args.command == "publish":
            raw = sys.stdin.buffer.read(MAX_DOCUMENT_BYTES + 1)
            if len(raw) > MAX_DOCUMENT_BYTES:
                print("payload exceeds 256 KiB", file=sys.stderr)
                return 1
            if not raw.strip():
                print("stdin is empty", file=sys.stderr)
                return 1
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                print("invalid JSON: %s" % exc, file=sys.stderr)
                return 1
            publish_update(path, payload, HERE)
        else:
            clear_cards(path, args.card, HERE)
    except (
        ValidationError,
        StaleUpdateError,
        LockTimeout,
        CorruptStorageError,
        StaticRootError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
