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

MAX_TITLE_CHARS = 500
MAX_ITEMS = 100
MAX_ERROR_MESSAGE_CHARS = 200
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
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


def calendar_window(
    today,
    timezone,
    today_count=0,
    fallback_count=0,
    explicit_start=None,
    explicit_end=None,
):
    tz = (timezone or "").strip()
    if not tz:
        raise ValueError("timezone must be a non-empty IANA name")
    if explicit_start and explicit_end:
        if not _DATE_RE.fullmatch(explicit_start) or not _DATE_RE.fullmatch(explicit_end):
            raise ValueError("explicit range must be YYYY-MM-DD")
        if explicit_end <= explicit_start:
            raise ValueError("range end must be exclusive and later than start")
        return {"start": explicit_start, "end": explicit_end}
    if today_count > 0:
        return {"start": today, "end": _add_days(today, 1)}
    if fallback_count > 0:
        return {"start": today, "end": _add_days(today, 30)}
    return {"start": today, "end": _add_days(today, 1)}


def loading_update(card_id, attempted_at=None):
    if card_id not in ("todo", "calendar"):
        raise ValueError("card must be todo or calendar")
    return {
        "id": card_id,
        "status": "loading",
        "attemptedAt": attempted_at or _now_rfc3339(),
    }


def error_update(card_id, attempted_at, message):
    if card_id not in ("todo", "calendar"):
        raise ValueError("card must be todo or calendar")
    text = message if isinstance(message, str) else "Google request failed"
    text = _SECRET_RE.sub("[redacted]", text)
    text = " ".join(text.split())
    if not text:
        text = "Google request failed"
    if len(text) > MAX_ERROR_MESSAGE_CHARS:
        text = text[:MAX_ERROR_MESSAGE_CHARS].rstrip()
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


def _item_sort_key(item):
    if item["allDay"]:
        return (item["startDate"], 0, "")
    return (item["start"][:10], 1, item["start"])


def normalize_events(
    payload,
    range_start,
    range_end,
    timezone,
    attempted_at=None,
):
    tz = (timezone or "").strip()
    if not tz:
        raise ValueError("timezone must be a non-empty IANA name")
    if not _DATE_RE.fullmatch(range_start) or not _DATE_RE.fullmatch(range_end):
        raise ValueError("range must be YYYY-MM-DD")
    if range_end <= range_start:
        raise ValueError("range end must be exclusive and later than start")
    attempted_at = attempted_at or _now_rfc3339()
    items = []
    seen = set()
    for event in _collect_events(payload):
        item = _event_item(event)
        if item is None or item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    items.sort(key=_item_sort_key)
    total = len(items)
    return {
        "id": "calendar",
        "status": "ready",
        "attemptedAt": attempted_at,
        "updatedAt": attempted_at,
        "timezone": tz,
        "range": {"start": range_start, "end": range_end},
        "items": items[:MAX_ITEMS],
        "totalCount": total,
    }


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
    ev_p.add_argument("--range-start", required=True)
    ev_p.add_argument("--range-end", required=True)
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
                card = normalize_events(
                    payload,
                    args.range_start,
                    args.range_end,
                    args.timezone,
                    args.attempted_at,
                )
        sys.stdout.write(_dump(card) + "\n")
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
