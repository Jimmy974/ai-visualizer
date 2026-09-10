# 02 — Display Todo and Calendar on the board

Status: resolved
Blocked by: 01
Spec: ../spec.md

Goal: make published information readable without disrupting the animated face.

Files: modify `faces/board/index.html`; create `faces/board/cards.js` and `faces/board/cards.css` for isolated card polling/rendering.

- [x] Consume `GET /board-cards` independently of `core.js`, with immediate/2-second polling, one in-flight request, hidden-tab pause and resume refresh.
- [x] Render semantic Todo/Calendar panels with the spec's item limits, overflow counts, date rules and successful retrieval timestamp. Consume calendar `range.start`, exclusive `range.end` and `timezone`; retain displayed scope during loading/error and show none before a first success. Timed display uses browser-local, zero-padded 24-hour `HH:mm`.
- [x] Implement invitation, loading, empty, provider error and connection error states; retain previous content where specified and render all external strings as text.
- [x] Integrate desktop chip clearance, narrow-screen scrolling and cinematic hiding/restoration. Only the two labelled panel regions are focusable (`tabindex="0"`, `role="region"`, heading-based accessible name), with visible focus and normal cursor. Guard `e.target` for panel regions/descendants and future controls before global Space/C/F handling; allow native Space/arrow scrolling. Hidden panels leave the tab order.
- [x] Smoke-check with the fixtures from 01 at 390px and 1440px via `/browse`; full sweep is spec QA Plan steps 7–9. Record evidence in this ticket's Comments.

Acceptance: published changes appear within one successful polling interval; mobile content is reachable; no fake results appear on errors; retained snapshots are visibly dated. Record QA evidence in this ticket.

## Comments

Round 3: panels are read-only; the earlier task-completion proposal is superseded.

Spec review round 1: clarified schema consumption, focus/keyboard behavior and 24-hour time formatting (1, 3, 11); consolidated QA into the spec sweep (9, 10). Retained the user's approved status (6).

Smoke via `/browse` against `python3 server.py --no-open --cards-file <disposable>` with 01-shaped fixtures (7 tasks / 5 events including HTML title, 500-char title, all-day 2026-03-29 exclusive 2026-03-30, timed 2026-03-29T00:30:00Z–02:30:00Z). Browser `Intl` timezone was `Europe/London`. No console errors.

- 390x844: `#board-cards` is `flex`/`column` with `overflow-y: auto` (scrollHeight 927 > clientHeight 844). Todo then Calendar stacked below the HUD. 5 tasks + 3 events, `+2 more` on both. Title `<b>html title</b>` is text. All-day meta `All day · 2026-03-29`. Timed Call `00:30 – 03:30`. Range `2026-03-29 → 2026-03-30 · Europe/London`. Updated `29 Mar 2026, 13:00`. Only `#card-todo` and `#card-calendar` have `tabindex=0` / `role=region`. Cursor `default`.
- 1440x900: grid columns; Todo right edge 422, Calendar left 1018, mid 720 clear of both (center chip visible). Same item limits and tab order.
- Cinematic `body.cine`: panels `inert`, `tabIndex -1`, `aria-hidden=true`. Space on a focused panel does not start cine; Space with focus outside does. Focus outline is 2px green. Poller one-in-flight / 2s / hidden-pause / resume covered in `tests/test_board_card_display.py` (QA 9 genuine-hidden page not driven live in this smoke).
