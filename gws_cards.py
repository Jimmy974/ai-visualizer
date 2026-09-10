#!/usr/bin/env python3
# ai-visualizer: give your AI agent a face.
# Copyright (C) 2026 Jared Rhodenizer
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalize Sinner's `gws` Google Tasks/Calendar JSON into board card updates.

Does not talk to Google. Sinner (or tests) feed verified `gws` payloads on
stdin; this module prints one card update for `board_cards.py publish`.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys

import board_cards

MAX_TITLE_CHARS = board_cards.MAX_TITLE_CHARS
MAX_ITEMS = board_cards.MAX_ITEMS
MAX_ERROR_MESSAGE_CHARS = board_cards.MAX_ERROR_MESSAGE_CHARS
_DATE_RE = board_cards._DATE_RE
_DUE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_KEYRING_RE = re.compile(r"^Using keyring backend:.*$", re.M)
_SECRET_RE = re.compile(
    r"(client_secret(?:\.json)?|credentials(?:\.enc|\.json)?|"
    r"ya29\.[A-Za-z0-9._~-]+|Bearer\s+\S+|token=?\s*\S+)",
    re.I,
)


def parse_gws_json(raw):
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    text = _KEYRING_RE.sub("", raw).strip()
    if not text:
        raise ValueError("empty gws payload")
    data = json.loads(text)
    if not isinstance(data, (dict, list)):
        raise ValueError("gws payload must be a JSON object or array")
    return data


def _now_rfc3339():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _clip_title(title):
    if not isinstance(title, str):
        return ""
    title = title.replace("\x00", "")
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS]
    return title


def _due_to_date(due):
    if not due or not isinstance(due, str):
        return None
    match = _DUE_PREFIX.match(due.strip())
    if not match:
        return None
    ymd = match.group(1)
    datetime.date.fromisoformat(ymd)
    return ymd


def _add_days(ymd, days):
    dt = datetime.date.fromisoformat(ymd) + datetime.timedelta(days=days)
    return dt.isoformat()


def validate_range_and_timezone(range_start, range_end, timezone):
    try:
        tz = board_cards.parse_timezone(timezone)
        rng = board_cards.parse_range({"start": range_start, "end": range_end})
    except board_cards.ValidationError as exc:
        raise ValueError(str(exc))
    return rng, tz


def _tzinfo(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return datetime.timezone.utc


def _as_aware(now):
    if now is None:
        return datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=datetime.timezone.utc)
    return now


def item_has_ended(item, now, timezone):
    local_now = _as_aware(now).astimezone(_tzinfo(timezone))
    if item.get("allDay"):
        end = datetime.date.fromisoformat(item["endDate"])
        return local_now.date() >= end
    end = board_cards.parse_rfc3339(item["end"])
    return local_now >= end


def _event_start_instant(item, timezone):
    tz = _tzinfo(timezone)
    if item.get("allDay"):
        day = datetime.date.fromisoformat(item["startDate"])
        return datetime.datetime.combine(day, datetime.time.min, tzinfo=tz)
    return board_cards.parse_rfc3339(item["start"]).astimezone(tz)


def _item_sort_key(item, timezone):
    all_day = 0 if item.get("allDay") else 1
    return (_event_start_instant(item, timezone), all_day)


def _overlaps_today_upcoming(item, now, timezone, today):
    if item_has_ended(item, now, timezone):
        return False
    tomorrow = _add_days(today, 1)
    if item.get("allDay"):
        return item["startDate"] < tomorrow and item["endDate"] > today
    start = board_cards.parse_rfc3339(item["start"]).astimezone(_tzinfo(timezone))
    tomorrow_dt = datetime.datetime.combine(
        datetime.date.fromisoformat(tomorrow),
        datetime.time.min,
        tzinfo=_tzinfo(timezone),
    )
    return start < tomorrow_dt


def select_calendar_scope(
    items,
    timezone,
    now=None,
    today=None,
    explicit_start=None,
    explicit_end=None,
):
    if explicit_start and explicit_end:
        rng, _tz = validate_range_and_timezone(
            explicit_start, explicit_end, timezone
        )
        return list(items), rng
    today = today or _as_aware(now).astimezone(_tzinfo(timezone)).date().isoformat()
    upcoming_today = [
        item for item in items
        if _overlaps_today_upcoming(item, now, timezone, today)
    ]
    if upcoming_today:
        upcoming_today.sort(key=lambda item: _item_sort_key(item, timezone))
        rng, _tz = validate_range_and_timezone(
            today, _add_days(today, 1), timezone
        )
        return upcoming_today, rng
    rest = [item for item in items if not item_has_ended(item, now, timezone)]
    rest.sort(key=lambda item: _item_sort_key(item, timezone))
    if rest:
        rng, _tz = validate_range_and_timezone(
            today, _add_days(today, 30), timezone
        )
        return [rest[0]], rng
    rng, _tz = validate_range_and_timezone(today, _add_days(today, 1), timezone)
    return [], rng


def loading_update(card_id, attempted_at=None):
    if card_id not in board_cards.CARD_IDS:
        raise ValueError("card must be todo or calendar")
    return {
        "id": card_id,
        "status": "loading",
        "attemptedAt": attempted_at or _now_rfc3339(),
    }


def error_update(card_id, attempted_at, message):
    if card_id not in board_cards.CARD_IDS:
        raise ValueError("card must be todo or calendar")
    text = message if isinstance(message, str) else "Google request failed"
    text = _SECRET_RE.sub("[redacted]", text)
    try:
        text = board_cards.sanitize_message(text)
    except board_cards.ValidationError:
        text = "Google request failed"
    return {
        "id": card_id,
        "status": "error",
        "attemptedAt": attempted_at or _now_rfc3339(),
        "message": text,
    }


def _iter_task_groups(payload):
    if isinstance(payload, list):
        yield payload
        return
    if not isinstance(payload, dict):
        return
    if "tasklists" in payload:
        for lst in payload.get("tasklists") or []:
            yield (lst or {}).get("items") or []
        return
    if "items" in payload:
        yield payload.get("items") or []


def normalize_tasks(payload, attempted_at=None):
    attempted_at = attempted_at or _now_rfc3339()
    items = []
    seen = set()
    for group in _iter_task_groups(payload):
        for task in group:
            if not isinstance(task, dict):
                continue
            if task.get("status") and task.get("status") != "needsAction":
                continue
            title = _clip_title(task.get("title") or "")
            if not title.strip():
                continue
            tid = task.get("id")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            item = {"id": str(tid), "title": title}
            due = _due_to_date(task.get("due"))
            if due:
                item["dueDate"] = due
            items.append(item)
    total = len(items)
    return {
        "id": "todo",
        "status": "ready",
        "attemptedAt": attempted_at,
        "updatedAt": attempted_at,
        "items": items[:MAX_ITEMS],
        "totalCount": total,
    }


def _stable_id(*parts):
    blob = "|".join("" if p is None else str(p) for p in parts)
    return "gws-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _as_rfc_or_date(value):
    if isinstance(value, dict):
        if value.get("date"):
            return ("date", value["date"])
        if value.get("dateTime"):
            return ("datetime", value["dateTime"])
        return None
    if isinstance(value, str):
        if _DATE_RE.fullmatch(value):
            return ("date", value)
        return ("datetime", value)
    return None


def _collect_events(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if "events" in payload:
        return payload.get("events") or []
    if "calendars" in payload:
        out = []
        for cal in payload.get("calendars") or []:
            out.extend((cal or {}).get("items") or [])
        return out
    return payload.get("items") or []


def _event_item(event):
    if not isinstance(event, dict):
        return None
    if event.get("status") == "cancelled":
        return None
    start = _as_rfc_or_date(event.get("start"))
    end = _as_rfc_or_date(event.get("end"))
    if not start or not end:
        return None
    title = _clip_title(event.get("summary") or event.get("title") or "")
    if not title.strip():
        return None
    eid = event.get("id") or event.get("iCalUID")
    if not eid:
        eid = _stable_id(
            event.get("calendar"), start[1], end[1], title
        )
    if start[0] == "date" or end[0] == "date":
        if not _DATE_RE.fullmatch(start[1]) or not _DATE_RE.fullmatch(end[1]):
            return None
        if end[1] <= start[1]:
            return None
        return {
            "id": str(eid),
            "title": title,
            "allDay": True,
            "startDate": start[1],
            "endDate": end[1],
        }
    return {
        "id": str(eid),
        "title": title,
        "allDay": False,
        "start": start[1],
        "end": end[1],
    }


def calendar_card(items, range_start, range_end, timezone, attempted_at=None):
    rng, tz = validate_range_and_timezone(range_start, range_end, timezone)
    attempted_at = attempted_at or _now_rfc3339()
    out = list(items)
    out.sort(key=lambda item: _item_sort_key(item, timezone))
    return {
        "id": "calendar",
        "status": "ready",
        "attemptedAt": attempted_at,
        "updatedAt": attempted_at,
        "timezone": tz,
        "range": rng,
        "items": out[:MAX_ITEMS],
        "totalCount": len(out),
    }


def collect_event_items(payload):
    items = []
    seen = set()
    for event in _collect_events(payload):
        item = _event_item(event)
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    return items


def normalize_events(
    payload,
    range_start,
    range_end,
    timezone,
    attempted_at=None,
):
    return calendar_card(
        collect_event_items(payload), range_start, range_end, timezone, attempted_at
    )


def _dump(card):
    return json.dumps(card, ensure_ascii=False, separators=(",", ":"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Normalize gws JSON into one board card update."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    load_p = sub.add_parser("loading")
    load_p.add_argument("--card", required=True, choices=["todo", "calendar"])
    load_p.add_argument("--attempted-at")
    err_p = sub.add_parser("error")
    err_p.add_argument("--card", required=True, choices=["todo", "calendar"])
    err_p.add_argument("--message", required=True)
    err_p.add_argument("--attempted-at")
    tasks_p = sub.add_parser("tasks")
    tasks_p.add_argument("--attempted-at")
    ev_p = sub.add_parser("events")
    ev_p.add_argument("--attempted-at")
    ev_p.add_argument("--timezone", required=True)
    ev_p.add_argument("--range-start")
    ev_p.add_argument("--range-end")
    ev_p.add_argument("--auto-scope", action="store_true")
    ev_p.add_argument("--now")
    ev_p.add_argument("--today")
    args = parser.parse_args(argv)
    try:
        if args.command == "loading":
            card = loading_update(args.card, args.attempted_at)
        elif args.command == "error":
            card = error_update(args.card, args.attempted_at, args.message)
        else:
            payload = parse_gws_json(sys.stdin.read())
            if args.command == "tasks":
                card = normalize_tasks(payload, args.attempted_at)
            else:
                if args.auto_scope:
                    now = board_cards.parse_rfc3339(args.now) if args.now else None
                    selected, rng = select_calendar_scope(
                        collect_event_items(payload),
                        args.timezone,
                        now=now,
                        today=args.today,
                    )
                    card = calendar_card(
                        selected,
                        rng["start"],
                        rng["end"],
                        args.timezone,
                        args.attempted_at,
                    )
                elif not args.range_start or not args.range_end:
                    raise ValueError(
                        "events requires --range-start and --range-end, or --auto-scope"
                    )
                else:
                    card = normalize_events(
                        payload,
                        args.range_start,
                        args.range_end,
                        args.timezone,
                        args.attempted_at,
                    )
        sys.stdout.write(_dump(card) + "\n")
    except (ValueError, KeyError, json.JSONDecodeError, board_cards.ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
