# Board info cards

Status: ready for implementation

## Outcome and accepted decisions

When a person asks Sinner for their Google tasks or calendar, Sinner uses its existing Google skill and publishes the result to readable Todo and Calendar cards on `faces/board/index.html`.

Round 3's `ok` accepts every round 2 recommendation: reuse the working Google skill, add panels over the circuit animation, keep cards read-only, refresh Google data on request, and persist the latest results locally until replaced or explicitly cleared. Interpret “cannot” in the earlier answer as “can,” as accepted in round 2. Google authentication stays with Sinner.

No product decisions remain. The installed Google skill's exact name/path was not supplied and is not present in this worktree; discovering and verifying that integration is work in ticket 03, not a claim that it has already been tested.

## Repository evidence

- `faces/board/index.html` renders an animated canvas and HUD, has no existing info-card UI, hides its HUD during cinematic mode, and intercepts Space/C/F keys globally.
- `core.js` polls `/state` every 120 ms for voice animation. Card traffic must remain separate from that loop.
- `server.py` uses Python's standard library, file-backed state, GET endpoints, and a static file server. Reuse these conventions without adding a Google client to the visualizer.
- Root `CLAUDE.md` is absent in this worktree. `docs/agents/issue-tracker.md` requires individual numbered Markdown tickets with `Status:` and dependency lines.

## Data flow and persistence

Sinner Google skill → local publisher → persisted JSON snapshot → `GET /board-cards` → board panels. The browser polls the local endpoint immediately and every 2 seconds with at most one request in flight; this does not refresh Google. Pause polling while hidden and fetch on return.

Add `board_cards.py` as a standard-library storage/validation module and CLI. Both server and CLI honor `--cards-file <path>`, taking precedence over `board_cards_file` in `ai-visualizer.json`, then the default `~/.local/share/ai-visualizer/board-cards.json`. Expand `~` and resolve relative paths against the repository root identically in both entry points. Reject paths resolving to or under the static root, including symlink resolution, before starting the server or modifying storage; exit nonzero with a clear message. Add the key to `server.py`'s `DEFAULTS` and `ai-visualizer.json.example`. Do not store OAuth credentials or complete upstream responses. No browser write endpoint is required.

Use atomic replacement and a portable `O_CREAT|O_EXCL` sidecar lock file, released in `finally`. Wait at most 5 seconds for contention, then fail without mutation; do not automatically steal a lock after a crash. Document removal only after verifying no writer is active. Apply owner-only permissions on POSIX; permission enforcement is best-effort on other platforms and must not prevent Windows operation. Parse RFC 3339 using a small standard-library parser accepting `Z` and numeric offsets, with explicit calendar/offset validation, rather than relying on Python 3.11's trailing-`Z` support. Do not introduce a new Python 3.11 minimum.

CLI contract: `python3 board_cards.py publish` reads one card update from stdin; `python3 board_cards.py clear --card todo|calendar|all` explicitly removes saved content. Publish merges only the named card, preserving the other card. Read and write use the same configuration resolution as the server. Clearing board content never deletes Google items.

Override examples: `python3 server.py --no-open --cards-file /absolute/disposable/cards.json` and `python3 board_cards.py --cards-file /absolute/disposable/cards.json publish` (or `clear --card all`). Tests and every QA step use a disposable path outside the static root through this override; never edit the user's configuration for QA.

`GET /board-cards` returns `{ "version": 1, "cards": [...] }`, with no-store caching. A missing file yields an empty list. Invalid storage yields a controlled 503 response; the UI retains its last valid snapshot and marks it unavailable. Invalid CLI input exits nonzero without modifying storage. Limit the stored document to 256 KiB, 100 items per card, and plain-text titles to 500 characters; reject invalid types, duplicate item IDs, unsupported versions, and malformed timestamps.

Each update has `id` (`todo` or `calendar`), `status` (`loading`, `ready`, or `error`), and `attemptedAt` (RFC 3339 instant). A successful update also has `updatedAt`, `items`, and `totalCount` (integer at least the number supplied). Loading/error updates preserve the last successful items, `totalCount` and `updatedAt`; errors include a short, sanitized `message`. Successful empty results replace old items with `[]`. `updatedAt` means successful retrieval time, not page-load time. Concurrent updates serialize under the writer lock; reject an update older than that card's latest `attemptedAt`. Equal timestamps are accepted: the last writer under the lock wins, allowing loading and its result to share an attempt timestamp.

Todo items: `id`, `title`, optional `dueDate` (`YYYY-MM-DD`). The adapter supplies incomplete tasks in upstream order; no checkboxes or mutation controls. Calendar items: `id`, `title`, `allDay`; timed entries have `start` and `end` RFC 3339 instants, and all-day entries have `startDate` and exclusive `endDate` calendar dates. Keep date-only values as dates, avoiding timezone shifts.

Calendar `ready` updates require `range: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}` and `timezone: "<IANA name>"`. Range end is exclusive and must be later than start; all date-only fields must be real Gregorian dates in that exact format, and all-day end must be later than start. Validate timezone as a trimmed non-empty string; the producer must supply an actual IANA name, without requiring a platform timezone database in the storage layer. Loading/error updates retain the last successful `range` and `timezone` with the items; before a first success these fields are absent and no range is displayed. New ranges replace previous ranges only on success.

## Display behavior

Use two semantic DOM panels over the canvas, Todo then Calendar. Keep the center chip visible on wide screens. On narrow screens stack panels in a scrollable region below the top HUD; do not let the existing body overflow rule make content unreachable. Match the existing dark/green style with readable text. The only focusable card elements are the two scrollable panels: `tabindex="0"`, `role="region"`, and an accessible name linked to their headings. Give each a visible focus indicator and a normal cursor within its bounds. Space and arrow keys scroll a focused panel using native scrolling. The global keydown guard checks `e.target` for either panel or its descendants and any future interactive control, returning before intercepting Space/C/F. Hide panels during cinematic mode consistently with the HUD, remove them from keyboard navigation while hidden, and restore them afterward.

Show up to 5 tasks and 3 events with an overflow count. Default calendar request is today's ongoing/upcoming events in the viewer's timezone; if none, fetch the next event within the next 30 days and label that range. Explicit user dates override this default. Sort calendar events chronologically, with all-day events first within a day. Use browser-local time for timed display with zero-padded 24-hour `HH:mm`; preserve all-day dates and label them “All day.” If Sinner cannot determine the viewer timezone, it asks within the task conversation before a timezone-dependent Google query.

Before any data: show a short invitation to ask Sinner for tasks/calendar. Distinguish fetching, successfully empty, fetch failure, and local connection failure. Keep last good content visible during loading/errors with the last successful update time. Never silently substitute examples. Retain supplied ranges and timestamps on old snapshots rather than relabelling them as today's fresh results. Render untrusted titles/messages as text, not HTML.

## Scope and acceptance

No Google writes, inline editing, scheduled Google refresh, generic arbitrary widgets, or browser authentication flow in this release. Test fixtures may contain labelled synthetic data; real execution must use actual skill results.

The `todo|calendar` ID enum deliberately limits the first release to the accepted examples. Any later card type must explicitly extend this contract and its corresponding validation, renderer and producer; widening the enum alone is not sufficient.

The Sinner handoff artifact is `docs/agents/board-info-cards.md`, containing the verified Google invocation, normalization rules and publisher commands. For this release, explicitly load that document into the Sinner session before requesting card publication; document this prerequisite in README and use it in live acceptance. Automatic installation into Sinner's home is not part of this artifact or the acceptance claim.

Acceptance: a Sinner request produces real cards without reloading; requesting only one source preserves the other; partial provider failure preserves that card's previous content with an error; successful empty retrieval clears old content; reload and server restart restore snapshots; explicit clear removes them. Verify long/untrusted titles, all-day and DST cases, mobile overflow, cinematic behavior, and uninterrupted voice animation. A live skill-to-board check is required before claiming integration complete.

## Implementation frontier

Ticket 03's discovery checkbox is an explicit early-work exception and runs first, before 01 implementation; it does not wait for 01/02. Its result provides actual upstream shapes and exposes access blockers before dependent work. After discovery, 01 has no ticket dependencies, 02 depends on 01, and 03's publication/live acceptance work depends on 01 and 02. All three retain the user's explicit `ready-for-agent` status; this is a user-approved handoff, not an automatic scan of open/unclaimed tickets. Planning is complete; implementation and live verification remain pending.

## QA Plan

For every step, start the server and run every publisher/clear command with the same explicit `--cards-file <absolute-disposable-path>` outside the static root. Unit tests also pass this override to both entry points. Never edit the user's `ai-visualizer.json` or use their normal snapshot. Use labelled synthetic fixtures for destructive/error cases and the existing authorized Google skill for the live integration check. Record pass/fail evidence without recording private task or event contents.

1. Start the server with no snapshot file and open `/faces/board/index.html`. Request `GET /board-cards`. Pass: the API returns HTTP 200 with version 1, an empty cards list and `Cache-Control: no-store`; the board invites the user to ask the configured agent (`name` in config, default JARVIS) for tasks/calendar without showing fabricated results.
2. Publish valid Todo and Calendar fixtures through the CLI while the board stays open. Include 7 tasks and 5 events. Pass: the API returns both cards; after the next successful poll, the board shows 5 tasks and 3 events, correct overflow counts, calendar range and last successful retrieval times without reloading.
3. Publish an update for Todo only, followed by an older Todo update. Pass: the new Todo content appears, Calendar remains unchanged, and the older update is rejected without replacing the newer snapshot. Publish both card types concurrently; pass: both updates survive and the stored file remains valid JSON.
4. Submit malformed JSON, an unsupported version, duplicate item IDs, malformed timestamps and an oversized payload through the CLI. Pass: each command exits nonzero, the stored snapshot remains unchanged and the board retains the last valid content.
5. Publish loading and then error updates for one populated card. Then publish a successful empty result for that card. Pass: loading/error states retain its previous items and successful retrieval time with a visible status; the empty success removes old items and displays an empty state. The other card remains unchanged throughout.
6. Stop the local server, then restart it; separately replace the disposable snapshot with corrupt JSON and restore it. Pass: the open board retains its last good content and reports unavailability; corrupt storage produces a controlled HTTP 503; normal display recovers after service/data restoration. Reload the page and restart the server with valid storage; pass: saved cards and their original timestamps return.
7. Use a QA browser whose `Intl.DateTimeFormat().resolvedOptions().timeZone` is verified as `Europe/London`; record this value. Publish HTML-like and 500-character titles, a task due `2026-03-29`, an all-day event from `2026-03-29` to exclusive `2026-03-30`, and a timed event from `2026-03-29T00:30:00Z` to `2026-03-29T02:30:00Z`. Pass: the timed endpoints render exactly `00:30` and `03:30`, both date-only items stay on March 29, and the all-day item says `All day`. Titles render literally without markup execution, long text is readable, and ordering/range labels match the fixture. A different browser timezone cannot pass this fixture check.
8. Inspect the board at 390px and 1440px viewport widths using `/browse`. Tab into each labelled panel and use Space/arrow keys to scroll overflowing fixtures. Pass: only the two panel regions enter the card tab order, each has a visible focus indicator and readable accessible name, scrolling reaches all content, narrow panels stack, the wide center chip stays visible and text does not overlap the HUD.
9. With focus outside the panels, exercise Space/C cinematic toggling and F fullscreen; repeat with a panel focused. Cycle idle/listening/thinking/speaking states. Pass: outside focus allows the shortcuts, focused panels scroll without triggering them, hidden cinematic panels leave the tab order, and cards restore while voice animation continues. For polling evidence, use `/browse` JavaScript evaluation to install a temporary wrapper around `window.fetch` that records `performance.now()` at each `/board-cards` start and in its `finally`, plus `visibilitychange` timestamps and `document.visibilityState`. Observe at least 6 seconds visible, 6 seconds genuinely hidden (verify the recorded state), then visible again; remove the wrapper afterward. Pass: each request starts after the prior one settles, normal visible start intervals are at least 2 seconds, no new request starts during the hidden interval (an existing request may finish), and a fetch starts on return or after any still-running request settles. Cross-check completed requests with `performance.getEntriesByType('resource').filter(e => new URL(e.name).pathname === '/board-cards')`; `/state` continues on its separate loop. If the automation cannot produce a genuinely hidden page, record that subcheck as blocked rather than passing a synthetic event.
10. Explicitly load `docs/agents/board-info-cards.md` into Sinner's session, including the QA `--cards-file` override, then ask for actual Google tasks and calendar through the verified existing skill and request only one source. Pass: real results appear without page reload, incomplete tasks and calendar scope match the retrieved data, and the untouched source remains unchanged. Verify an explicit date request and an empty-today fixture; pass: the explicit range is honored, or the next event within 30 days is shown with its range labelled. If viewer timezone is unknown, Sinner resolves it before the date-dependent query. Fixture-only execution cannot pass the live integration check.
11. Exercise a controlled Google retrieval failure for one source while the other succeeds. Pass: Sinner publishes a sanitized error for the failed card, retains its previous result, and updates the successful card. No Google credentials or raw provider response appear in the board API, persisted snapshot or UI.
12. Run board-only clear for Todo, then for all cards, and reload. Pass: clearing Todo preserves Calendar, clearing all returns the invitation state, cleared results stay absent after reload/restart, and Google tasks/events remain unchanged. Confirm POSIX owner-only permissions where applicable and that direct static requests cannot retrieve the snapshot. Try a `--cards-file` path beneath the static root on both entry points; pass: both refuse it with a clear message and nonzero exit before writing or serving anything.

## Review Log

### Round 1

1. Addressed: calendar `range`/`timezone` fields, date validation and retention are specified across the contract and tickets; 01 covers their validation/retention tests.
2. Addressed: shared `--cards-file` precedence, resolution and static-root rejection; mandatory isolated override in tests and all QA steps.
3. Addressed: two labelled, focusable scroll regions, explicit keydown guard, native scrolling and observable focus QA replace nonexistent controls.
4. Addressed: portable exclusive lock file, POSIX/best-effort permission policy and RFC 3339 parser without a new Python 3.11 floor.
5. Addressed: 01 names `ai-visualizer.json.example` and `server.py`'s `DEFAULTS` alongside README.
6. Rebuttal: do not reset ticket statuses. The user explicitly instructed all tickets to be `ready-for-agent` after approval. That instruction takes precedence over the reviewer's suggested `open` state. The frontier description now reflects that handoff while incorporating finding 7's early discovery exception.
7. Addressed: 03's first discovery step is explicitly unblocked and must run before 01; it records skill identity, invocation and redacted output shapes before implementation proceeds.
8. Addressed: the repository handoff document is the artifact; explicit loading into Sinner is a documented live-test prerequisite. No automatic home installation is claimed.
9. Addressed: 02 now has one fixture smoke check and links to QA steps 7–9 for the full sweep; evidence belongs in Comments.
10. Addressed: QA step 9 names fetch start/settle and real visibility instrumentation via `/browse`, resource-timing cross-checks and explicit pass/blocked conditions.
11. Addressed: London timezone and a March 29, 2026 DST fixture specify exact `00:30`/`03:30` output; display format is fixed to 24-hour `HH:mm`.
12. Addressed: equal attempt timestamps are accepted, last serialized writer wins; 01 tests equality as well as older rejection.
13. Addressed in intent: first-release enum narrowing is now explicitly deliberate. Rebuttal to “enum is the only place to widen”: a new card type also requires validation, rendering and producer support; documenting an enum-only change would be technically incorrect.
