# Board info cards — Sinner handoff

Load this file into the Sinner session **before** asking for tasks or calendar on the board. This repository does not install itself into Sinner's home. Google authentication stays with Sinner's existing `gws` grant; do not start a second OAuth flow.

Every publisher, clear, and server command in this document (and in live QA) uses `--cards-file <absolute-disposable-path>` outside the visualizer folder. Never edit `ai-visualizer.json` for QA and never write Google tasks or events from this workflow.

## Skill identity (verified)

| | |
|---|---|
| Tool | Google Workspace CLI `gws` |
| Path | `/opt/homebrew/bin/gws` (`brew install googleworkspace-cli`) |
| Auth | Sinner's existing OAuth (`gws auth status`); client file `~/.config/gws/client_secret.json`, token in Keychain. Never paste either into a note or the snapshot. |
| Jobs | Vault `07 - Resources/Jobs/Check Google Calendar.md` and `Manage Google Tasks.md` |
| Account timezone | `gws calendar calendars get --params '{"calendarId":"primary"}'` → `timeZone` (verified: `Europe/London`) |

If `gws` is missing or `gws auth status` is not authenticated, stop. Do not invent another Google client.

Strip the first line `Using keyring backend: ...` before treating stdout as JSON. `gws_cards.py` does this automatically.

## Viewer timezone

Resolve timezone **before** any date-dependent calendar query.

1. Read `timeZone` from the primary calendar (command above).
2. If that field is missing or empty, ask in the conversation. Do not guess.

Pass the IANA name to `gws_cards.py events --timezone`.

## Publish path

Visualizer root is this repository. Replace `/ABS/cards.json` with the QA disposable path.

```
# loading (does not replace a previous successful range/items; storage retains them)
python3 gws_cards.py loading --card todo | python3 board_cards.py --cards-file /ABS/cards.json publish
python3 gws_cards.py loading --card calendar | python3 board_cards.py --cards-file /ABS/cards.json publish

# success / error (one card per publish; the other card is preserved)
python3 gws_cards.py tasks | python3 board_cards.py --cards-file /ABS/cards.json publish
python3 gws_cards.py events --timezone Europe/London --range-start YYYY-MM-DD --range-end YYYY-MM-DD | python3 board_cards.py --cards-file /ABS/cards.json publish
python3 gws_cards.py error --card calendar --message "Google request failed" | python3 board_cards.py --cards-file /ABS/cards.json publish
```

Start the visualizer with the same file:

```
python3 server.py --no-open --cards-file /ABS/cards.json
```

## Google Tasks

List every task list, then incomplete tasks in each, following `nextPageToken` until it is absent. Combine into one JSON object and normalize.

```
gws tasks tasklists list
gws tasks tasks list --params '{"tasklist":"<id>","showCompleted":false,"maxResults":100}'
```

Combined stdin shape (redacted):

```json
{
  "tasklists": [
    {
      "id": "<list-id>",
      "title": "<list-title>",
      "items": [
        {
          "kind": "tasks#task",
          "id": "<task-id>",
          "title": "<plain title>",
          "status": "needsAction",
          "due": "2026-03-29T00:00:00.000Z",
          "updated": "2026-09-10T11:17:08.779Z"
        }
      ]
    }
  ]
}
```

Normalization:

- Keep `status=needsAction` only, list order then item order.
- `due` → `dueDate` as the `YYYY-MM-DD` prefix (midnight UTC is that calendar date, not a local shift).
- Omit `dueDate` when `due` is absent.
- `totalCount` is the number of incomplete tasks in the fetched lists (including those beyond the 100 stored items).

A list with no open tasks is a successful empty card (`items: []`, `totalCount: 0`), not an error.

## Google Calendar

Default window, after timezone is known:

1. Today in the viewer timezone: `timeMin` = today's midnight, `timeMax` = tomorrow's midnight (exclusive end).
2. If that window has no ongoing/upcoming events, query the next 30 days (`timeMax` = today + 30) and label that range.
3. An explicit user date range overrides both. End is exclusive `YYYY-MM-DD`.

`gws calendar +agenda --today` / `--days 30` is the human Job helper (flattened `start`/`end` strings, no event id). For board publication prefer `events.list` so items keep Google ids, and page with `nextPageToken` / `gws --page-all`. Query each calendar from `gws calendar calendarList list` (or `calendarId=primary` when the request is one calendar).

Raw `events.list` item (redacted):

```json
{
  "kind": "calendar#events",
  "timeZone": "Europe/London",
  "items": [
    {
      "id": "<event-id>",
      "status": "confirmed",
      "summary": "<plain title>",
      "start": {"date": "2026-03-29"},
      "end": {"date": "2026-03-30"}
    },
    {
      "id": "<event-id>",
      "status": "confirmed",
      "summary": "<plain title>",
      "start": {"dateTime": "2026-03-29T00:30:00+00:00", "timeZone": "Europe/London"},
      "end": {"dateTime": "2026-03-29T02:30:00+00:00", "timeZone": "Europe/London"}
    }
  ]
}
```

`+agenda --format json` item (redacted): `start`/`end` are either `YYYY-MM-DD` (all-day, exclusive end) or RFC 3339 with a numeric offset. `gws_cards.py events` accepts both shapes.

Normalization:

- Skip `status=cancelled`.
- All-day: `startDate`/`endDate` from `date` fields (end exclusive, later than start).
- Timed: keep the RFC 3339 `dateTime` / helper strings as `start`/`end`.
- Ready calendar updates always include `range: {start, end}` and `timezone`.
- `totalCount` describes the fetched window, not the three events the board displays.
- Loading and error publishes omit `range`/`timezone`/`items`; `board_cards.py` keeps the last successful scope.

## Single-source requests

Publish loading then success/error for **only** the requested card. Do not clear or rewrite the other card.

## Board-only clear

Does not change Google.

```
python3 board_cards.py --cards-file /ABS/cards.json clear --card todo
python3 board_cards.py --cards-file /ABS/cards.json clear --card calendar
python3 board_cards.py --cards-file /ABS/cards.json clear --card all
```

## Errors

On a `gws` failure, publish `gws_cards.py error --card todo|calendar --message "<short sanitized reason>"`. Do not put OAuth tokens, client secrets, or raw provider JSON on the board.

## Runnable stdin example (synthetic)

```
python3 gws_cards.py tasks --attempted-at 2026-09-10T17:00:00Z <<'JSON' | python3 board_cards.py --cards-file /ABS/cards.json publish
{"items":[{"id":"t1","title":"Example incomplete task","status":"needsAction","due":"2026-03-29T00:00:00.000Z"}]}
JSON
```
