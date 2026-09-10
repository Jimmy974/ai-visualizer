VERDICT: FAIL

# QA report: board-info-cards

The `## QA Plan` from `spec.md` was run against HEAD `cc82624` on 2026-09-10.

- **Result:** 9 PASS, 1 FAIL (step 8), 2 BLOCKED (steps 10 and 11).
- **Server:** `python3 server.py --no-open --port 8797 --mock <state> --cards-file $QA/cards.json`. Every publish and clear command used the same `--cards-file`.
- **`$QA`:** the session scratchpad at `/private/tmp/claude-501/…/scratchpad/qa`, outside the repo and its static root.
- **Config:** the worktree has no `ai-visualizer.json`, so defaults apply and the agent name is JARVIS. Your config and normal snapshot were never touched.
- **Evidence:** screenshots are under `.scratch/board-info-cards/qa-evidence/`, and the entries below cite them by filename.

## Steps

### 1. PASS — empty start and invitation
- **Action:** started the server with no snapshot file (the `$QA` directory was empty), ran `curl -i http://127.0.0.1:8797/board-cards`, and opened `/faces/board/index.html` at 1440x900.
- **Evidence:**
  - The API returned `HTTP/1.0 200 OK`, `Cache-Control: no-store` and body `{"version": 1, "cards": []}`.
  - The board showed `TODO — Ask JARVIS for your tasks.` and `CALENDAR — Ask JARVIS for your calendar.`, both with `data-mode="invitation"` and 0 list items.
  - The same invitation state came back after a real fetch of an empty snapshot in step 12c.
  - Screenshot: `01-empty-invitation-1440.png`.

### 2. PASS — 7 tasks and 5 events, no reload
- **Action:**
  - Set `window.__qaMarker` in the open page.
  - Ran `python3 board_cards.py --cards-file $QA/cards.json publish < todo7.json`, then the same with `cal5.json`. Both exited 0.
  - Checked the API, then read the board after the next poll.
- **Evidence:**
  - The API returned both cards: todo ready with 7 items and `totalCount` 7; calendar ready with 5 items, `totalCount` 5 and range `2026-09-10 → 2026-09-11`.
  - The Todo board showed 5 tasks, "Updated 10 Sept 2026, 19:00 · +2 more".
  - The Calendar board showed 3 events: all-day first, then 09:00–10:00, then 12:00–12:30 (from `11:00Z`). The meta line read "2026-09-10 → 2026-09-11 · Europe/London · Updated 10 Sept 2026, 19:00 · +2 more".
  - The marker survived, so the page did not reload.
  - The tab was first opened in the background (`visibilityState: hidden`), and polling correctly made no requests until it was brought to the foreground. The cards then painted within one poll.
  - Screenshot: `02-populated-1440.png`.

### 3. PASS — newer, older and concurrent Todo updates
- **Action:** published `todo_new.json` (attemptedAt 18:10), then `todo_old.json` (attemptedAt 18:05). Then published `conc_todo.json` and `conc_cal.json` in parallel background processes.
- **Evidence:**
  - Newer update: exit 0.
  - Older update: exit 1, `update is older than the stored attemptedAt for todo`.
  - The snapshot hash was `cd7b174aa184` both before and after the older publish.
  - The Calendar card hash was `8da65b3019ff` before and after, and the board showed the newer Todo items with the Calendar's 3 items unchanged.
  - Concurrent publishes: both exited 0, both cards were stored with attemptedAt 18:20, and `python3 -m json.tool` confirmed the file is valid JSON.
  - Screenshots: `03a-newer-todo-calendar-unchanged.png`, `03b-concurrent-both.png`.

### 4. PASS — invalid CLI input
- **Action:** ran `board_cards.py publish` with each bad input and compared the snapshot's SHA-1 before and after.
- **Evidence:** every command exited 1, and the snapshot stayed at `b7ff58b3471c`.

| Input | Error message |
|---|---|
| malformed JSON | `invalid JSON: Expecting value…` |
| `"version": 99` | `unsupported snapshot version` |
| duplicate item ids | `duplicate item id` |
| `attemptedAt: "2026-09-10 18:30"` | `malformed RFC 3339 timestamp` |
| 101 items | `more than 100 items` |
| 303 KB document | `payload exceeds 256 KiB` |
| 300 KB padded document | `payload exceeds 256 KiB` |

  The board kept its previous content. Screenshot: `04-invalid-inputs-board-retained.png`.

### 5. PASS — loading, error, then empty success on one card
- **Action:** published `todo_loading.json`, `todo_error.json` and `todo_empty.json` in turn, reading the stored card and the board after each.
- **Evidence:**

| Update | Stored card | Board |
|---|---|---|
| Loading | status `loading`, previous item and `updatedAt 18:20Z` kept | "Updating…" plus the old item and "Updated … 19:20" |
| Error | status `error`, message `QA synthetic Google failure`, item and `updatedAt` kept | the error text, the old item and "Updated … 19:20" |
| Empty success | `items: []`, `totalCount: 0` | "No open tasks.", "Updated … 19:42" |

  The Calendar card hash stayed `c4e10323064a` throughout. Screenshots: `05-todo-loading.png`, `05-todo-error.png`, `05-todo-empty.png`.

### 6. PASS — server loss, corrupt storage, restart
- **Action:** in order:
  - killed the server
  - restarted it
  - overwrote the snapshot with `{"version": 1, "cards": [ corrupt`
  - restored the saved copy
  - restarted the server and reloaded the page
- **Evidence:**

| Phase | API | Board |
|---|---|---|
| Server stopped (curl got no connection) | — | Both panels showed "Board cards unavailable." and kept their last content and times. Todo's last good state was the empty success, "Updated 19:42"; Calendar kept its item. The page did not reload (marker kept). |
| Server restarted | 200 | recovered: modes `empty`, `ready` |
| Corrupt snapshot | `HTTP/1.0 503`, `Cache-Control: no-store`, `{"error": "board cards storage is invalid"}` | "unavailable", last content kept |
| Snapshot restored | 200 | recovered |
| Server restarted and page reloaded | — | cards returned with their original stored timestamps: todo `18:42:00Z`, calendar `18:20:00Z` |

  Screenshots: `06a-server-stopped.png`, `06b-server-restarted.png`, `06c-corrupt-503.png`, `06d-restored.png`, `06e-reload-restart.png`.

### 7. PASS — London DST fixture and untrusted titles
- **Action:** published `dst_todo.json` and `dst_cal.json`, then inspected the board at 1440x900.
- **Fixture:**
  - an HTML-like title `<img src=x onerror=…><b>QA bold?</b>`
  - a 500-character title
  - a task due `2026-03-29`
  - an all-day event from `2026-03-29` to `2026-03-30`
  - a timed event from `2026-03-29T00:30:00Z` to `02:30:00Z`, with a `<script>` in its title
- **Evidence:**
  - The browser's `Intl.DateTimeFormat().resolvedOptions().timeZone` was `Europe/London`.
  - The timed event rendered exactly `00:30 – 03:30`.
  - The all-day event rendered `All day · 2026-03-29`, and the task showed `2026-03-29`.
  - Both markup titles rendered as literal text. `window.__xss` and `window.__xss2` stayed `null`, and there were 0 `img`, `b` or `script` elements inside `#board-cards`.
  - The long title wraps (`white-space: pre-wrap`, `overflow-wrap: anywhere`), with no horizontal overflow (`scrollWidth` 340 = `clientWidth` 340).
  - Ordering was all-day first, then timed. The range label read `2026-03-29 → 2026-03-30 · Europe/London`.
  - Screenshot: `07-dst-london-untrusted-1440.png`.

### 8. FAIL — layout and keyboard at 390px and 1440px
- **Action:**
  - Published `overflow_todo.json` (7 tasks with 480-character titles).
  - At 1440x900 and at 390x844, measured the geometry and read the accessibility tree.
  - Pressed Tab 5 times from a blurred start.
  - Focused each panel and pressed ArrowDown and Space 10 times.
  - Used browser-harness rather than `/browse`; see the deviations below.
- **Evidence (passing subchecks):**
  - **Tab order:** only the two panels enter it, `card-todo → card-calendar → BODY`, at both widths.
  - **Accessible names:** the two regions are named `TODO` and `CALENDAR`.
  - **Focus indicator:** `outline: solid 2px rgb(61, 220, 132)` plus a 3 px ring.
  - **Keyboard scrolling:** the overflowing Todo panel scrolled 0 → 40 → 80 → 645 = end at 1440, and the region scrolled to 1120 = end at 390. `reachedEnd` was true for both panels, and cinematic mode never triggered.
  - **At 390:** the panels stack (region y 220–764, Calendar below Todo) and don't overlap the HUD.
  - **Wide centre chip:** not covered at 1440.
  - **HUD crowding at 390:** "J.A.R.V.I.S." running into "IDLE" and the bottom labels overlapping each other happen with the cards hidden too, so they come from the HUD, not this feature (`08-390-control-cards-hidden.png`).
- **Expected:** at 1440px, "text does not overlap the HUD" (QA 8).
- **Actual:**
  - At 1440x900, `#card-calendar` spans x 1018–1392, y 108–314. Its container `#board-cards` has `z-index: 12`, which sits above `.hud` at `z-index: 10`.
  - The panel covers the HUD orb `#orb` (x 1347–1384, y 86–123).
  - It also covers all of the live `#usage` text "5H 34% 3h / 7D 61% 3d" (x 1301–1384, y 132–160).
  - The overlap is visible in `08-1440-overview.png` and `02-populated-1440.png`.
  - The wide layout comes from `faces/board/cards.css:10` (`z-index: 12`) and `faces/board/cards.css:16` (`padding: 108px 48px 92px`).
- **Other screenshots:**
  - `08-1440-focus-card-todo.png`, `08-1440-focus-card-calendar.png`
  - `08-1440-scrolled-card-todo.png`, `08-1440-scrolled-card-calendar.png`
  - `08-390-overview.png`
  - `08-390-focus-card-todo.png`, `08-390-focus-card-calendar.png`
  - `08-390-scrolled-card-todo.png`, `08-390-scrolled-card-calendar.png`

### 9. PASS — shortcuts, cinematic mode, voice states, polling
- **Action:**
  - Sent real key events over CDP with focus outside the panels, then with a panel focused.
  - Cycled the voice state by restarting the server with `--mock listening|thinking|speaking|idle`.
  - Installed a temporary `window.fetch` wrapper and a `visibilitychange` log. Watched 6.5 s visible, then about 6.8 s genuinely hidden (a second tab brought to the foreground), then 6.5 s visible again. Removed the wrapper afterwards.
  - Redid the resource-timing cross-check with a cleared, 10,000-entry buffer.
- **Evidence:**
  - **Focus outside the panels:** Space turned cinematic mode on, then off. C did the same. F entered fullscreen, and pressing it again exited.
  - **Panel focused:** Space scrolled the panel (0 → 645). C and F did nothing: no cinematic mode, no fullscreen.
  - **During cinematic mode:** `#board-cards` had `inert=true`, `aria-hidden="true"`, `visibility: hidden`, `opacity: 0`, and panel `tabIndex` of `[-1, -1]`. Three Tab presses stayed on `BODY`.
  - **After cinematic mode:** `inert=false`, `visibility: visible`, `opacity: 1`, `tabIndex [0, 0]`, and the cards were restored.
  - **Animation:** 62 animation frames per second and a changing canvas before, during and after cinematic mode. The four states showed `LISTENING`, `THINKING`, `SPEAKING` and `IDLE`, each at 62 fps with the canvas changing and 5 Todo and 2 Calendar items kept.
  - **Polling while visible:** `/board-cards` requests started at 171739, 173742 and 175746 ms (2004 ms apart), and each finished 2–3 ms after it started, before the next began.
  - **Polling while hidden:** the page went `hidden` at 177283 ms, and `document.visibilityState` read `hidden` twice during the gap. No request started until it became `visible` at 184105.5 ms. A request started at 184105.4 ms, in the same visibility-change handler, and the following ones came 2003–2004 ms apart.
  - **Resource timing:** the first attempt returned no entries because the default 250-entry buffer was already full from `/state` polling, so it was redone. In the redo, 5 of 5 `/board-cards` entries matched the wrapper's log exactly (start and end in ms). `/state` recorded 71 entries over 8.4 s (about 8.5 per second) on its own loop.
  - Screenshots: `09-cine-panels-hidden.png`, `09-cine-exited-cards-restored.png`, `09-state-listening.png`, `09-state-thinking.png`, `09-state-speaking.png`, `09-state-idle.png`.

### 10. BLOCKED — live Sinner handoff
- **Reason:** this step needs `docs/agents/board-info-cards.md` loaded into a Sinner session and real Google tasks and calendar requests. You waived the nested Sinner live QA, and the live Google data needs your authenticated session, which this QA run doesn't have.
- **Not run:** the explicit-date and empty-today live checks and the viewer-timezone prompt. The spec says fixture-only execution cannot pass this step, so no fixture substitute was recorded as a pass.

### 11. BLOCKED — controlled Google failure
- **Reason:** "Sinner publishes a sanitized error…" needs a Sinner session and a live Google failure (waived, and it needs your authenticated session).
- **Supplementary check (not a pass):** a synthetic run of the same publish path, against a *separate* disposable file `$QA/cards11.json`:
  - Seeded Calendar with 5 items, and published a Todo success through `gws_cards.py tasks`.
  - Ran `gws_cards.py error --card calendar --message '<b>Google request failed</b> (HTTP 503)' | board_cards.py publish`. It exited 0.
  - The stored Calendar card became `status error`, message `Google request failed (HTTP 503)` with the tags stripped, and it kept its 5 items and `updatedAt 18:00:05Z`.
  - Todo was stored as `ready`.
  - The file contains no tag markup and no token-like strings (`ya29`, `client_secret`, `access_token`, `refresh_token`).

### 12. PASS — board-only clear, permissions, static root
- **Action:** in order:
  - `board_cards.py --cards-file $QA/cards.json clear --card todo`, then `clear --card all`
  - restarted the server and reloaded the page
  - checked the file's permissions with `stat`
  - sent direct static requests for the snapshot
  - ran `--cards-file faces/board/qa-under-static-root.json` on `board_cards.py publish`, `board_cards.py clear` and `server.py`
- **Evidence:**
  - **Clear Todo:** exit 0. The Calendar hash stayed `13ed4c787093`, the API returned only `calendar ready 2`, and the board showed the Todo invitation with the Calendar items kept.
  - **Clear all:** exit 0. The API returned `[]` and both panels showed the invitation.
  - **After restart and reload:** the API still returned `[]`, and the file held `{"version":1,"cards":[]}`, so nothing reappeared.
  - **Google unchanged:** `board_cards.py` contains no network, subprocess or `gws` code, so a clear only touches the local file.
  - **Permissions:** the snapshot is `-rw-------` (0600).
  - **Static requests:** `/cards.json`, `/board-cards.json`, `/faces/board/../../cards.json`, `/%2e%2e/%2e%2e/cards.json`, `/..%2f..%2fcards.json` and the snapshot's absolute path all returned 404. A control request for `/faces/board/cards.js` returned 200.
  - **Static-root refusal:** all three entry points exited 1 with `… resolves under the static root; refusing to use a path that could be served as a static file`. No file was created, and port 8798 never started listening.
  - Screenshots: `12a-cleared-todo-calendar-kept.png`, `12b-cleared-all-invitation.png`, `12c-after-reload-restart.png`.

## Setup and deviations

- **Browser:** a dedicated headless Chrome started with the command you gave, driven by browser-harness 0.1.10 through `BU_CDP_URL`. Your own Chrome was never used or touched. Steps 8 and 9 name `/browse`, but browser-harness was used as you instructed.
- **Hang and relaunch:** the first step 8 attempt hung. The headless browser process sat at about 113% CPU, its DevTools endpoint didn't answer for 12 s, and a CDP key dispatch timed out. I killed it with `pkill -f 'headless=new.*9333'` and relaunched it with the identical command, discarded that attempt's partial evidence, and re-ran step 8 in full. The cause wasn't found, and the hang didn't recur.
- **CDP address:** the relaunched Chrome listened only on `[::1]:9333`, so `127.0.0.1:9333` didn't answer. `BU_CDP_URL=http://localhost:9333` (the same dedicated instance) was used from then on.
- **Background tabs:** in this headless setup, tabs opened by `new_tab` start `hidden`. The board tab was brought to the foreground with `activate_tab` before checking visible behaviour. The hidden interval in step 9 was a real background tab, checked through `document.visibilityState`, not a synthetic event.
- **Cleanup:** the headless Chrome was killed before this verdict was written (0 processes left on 9333, and the port is closed). The QA server on 8797 was stopped.
- **Files:** only `qa-report.md` and `qa-evidence/` were added. The `.gitignore` change and `code-review.md` were already in the tree before QA began. Fixtures, scripts and the disposable snapshots are in the session scratchpad, not the repo.
