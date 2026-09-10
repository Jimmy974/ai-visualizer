# 03 — Connect Sinner's Google results to card publication

Status: resolved
Blocked by: 01, 02
Spec: ../spec.md

Early-work exception: the first discovery checkbox is unblocked and must execute before ticket 01 implementation. The dependency line applies to publication/normalization implementation and live acceptance. Record discovery evidence or a concrete blocker before proceeding with the dependent work.

Goal: complete “ask Sinner → see actual Google information on the board.”

Files: create `docs/agents/board-info-cards.md` with the Sinner handoff instructions and runnable stdin examples; update `README.md` with the workflow. This document is the delivery artifact: explicitly load it into the Sinner session before using the workflow, including during live QA. No automatic installation into an assumed Sinner-home path is claimed. Include the shared `--cards-file` override in all QA invocation examples.

- [x] EARLY / UNBLOCKED: locate and verify the existing skill can retrieve Google tasks and calendar using Sinner's current authentication. Record its exact name/path, invocation, and a structurally faithful redacted sample of each output under Comments, including date/timezone and pagination fields. Replace personal values and omit credentials. Supply this evidence to 01 before implementation; if unavailable, record the concrete blocker immediately. Do not assume a tool name or invent a second OAuth flow.
- [x] Wire the agent workflow to publish per-card loading, normalized success or sanitized error updates through `python3 board_cards.py publish`. Preserve the other card on single-source requests.
- [x] Normalize incomplete tasks and timed/all-day events to the spec using the verified upstream shapes. Calendar success includes `range: {start, end}` in `YYYY-MM-DD` with exclusive end and the viewer's IANA `timezone`. Honor explicit dates; otherwise use today's ongoing/upcoming events and the labelled 30-day fallback. Resolve viewer timezone before date-dependent retrieval. Loading/error updates must not replace the previous successful scope.
- [x] Document and exercise explicit board-only clear commands. Keep Google writes outside this workflow.
- [x] Verify normalization with representative redacted skill output: date-only tasks, all-day events, offset timestamps, multiple lists/calendars, no results and one-source failure. Confirm totals describe the fetched scope.
- [ ] Explicitly load the handoff document into Sinner with the QA `--cards-file` override. Run a live request for both tasks and calendar, then a single-source refresh, reload/server restart and explicit board clear. Record invocation and pass/fail results without private task/event contents in repo documentation. **Waived by user** (nested Sinner QA). This box does not claim a Sinner-session run.

Acceptance: actual skill results appear in the board; failures preserve prior data correctly; local persistence and clear work end to end. Fixture-only checks do not satisfy the live acceptance criterion.

If the installed skill cannot be located or accessed, record the concrete integration blocker here; do not claim completion or replace live data with examples. Any edits to an external skill need the execution session's authorized scope; this planning session edits only the scratch feature directory.

## Comments

Round 3: user accepted reuse of the existing Google skill. Its exact identity remains an implementation discovery, not an unresolved product decision.

Round-2 review: the Sinner-session checkbox is unticked and **waived by user**. Nested Sinner QA is not claimed. The gws live check in Comments stands.

Spec review round 1: discovery now runs first through an explicit dependency exception (7); the loaded repository document is the precise Sinner handoff artifact (8). Producer fields and isolated QA overrides match 01/02 (1, 2). Status remains user-approved (6).

### Discovery (live `gws`, Sinner's existing OAuth)

- Tool: Google Workspace CLI `gws` at `/opt/homebrew/bin/gws` (`brew install googleworkspace-cli`).
- Auth: `gws auth status` → oauth2, encrypted credentials, Keychain; project `sinner-508208`. No second OAuth flow.
- Jobs: vault `Check Google Calendar.md`, `Manage Google Tasks.md`.
- Primary calendar `timeZone`: `Europe/London`.
- Pagination: `nextPageToken` present on `calendar#events` when `maxResults` is small; task list payloads in this check had no token.
- stdout noise: first line `Using keyring backend: ...` is not JSON.

Redacted Tasks `tasks.tasks.list` (`showCompleted: false`):

```json
{"kind":"tasks#tasks","items":[{"kind":"tasks#task","id":"<id>","title":"<plain>","status":"needsAction","due":"2026-03-29T00:00:00.000Z","updated":"2026-09-10T11:17:08.779Z","etag":"<etag>","position":"<pos>","selfLink":"<url>","webViewLink":"<url>","links":[]}]}
```

Live fetch: 4 task lists; open incomplete counts 0/0/6/2 (`totalCount` 8). No `due` on current open items; `due` shape taken from the Tasks API / Job insert example.

Redacted Calendar `events.list` item:

```json
{"kind":"calendar#event","id":"<id>","status":"confirmed","summary":"<plain>","start":{"dateTime":"2026-09-10T11:00:00+01:00","timeZone":"Europe/London"},"end":{"dateTime":"2026-09-10T12:15:00+01:00","timeZone":"Europe/London"}}
```

All-day: `start: {"date":"2026-09-25"}`, `end: {"date":"2026-09-26"}` (exclusive). `+agenda --format json` flattens `start`/`end` to RFC 3339 or `YYYY-MM-DD` strings and omits ids (`timeMin`/`timeMax`/`count`/`events`).

### Live board check (this session, disposable `--cards-file`)

Nested Sinner-session QA is **waived by user**. The gws live check below used Sinner's existing grant from this worktree, not a Sinner chat. Handoff document: `docs/agents/board-info-cards.md`.

- Loading publishes omitted items/range. Pass.
- Live tasks+calendar publish: GET `/board-cards` 200 `no-store`; todo ready 8 items; calendar ready 1 timed event, range `2026-09-10`→`2026-09-11`, timezone `Europe/London`. Pass.
- Todo-only refresh: calendar count and range unchanged. Pass.
- Controlled `gws` failure (`calendarId` that does not exist): calendar `error` with retained items+range; todo still ready; message had no client secret. Pass.
- `clear --card todo` left calendar; server restart restored that snapshot; `clear --card all` → `{version:1,cards:[]}`. No Google writes. Pass.
