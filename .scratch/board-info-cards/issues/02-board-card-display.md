# 02 — Display Todo and Calendar on the board

Status: ready-for-agent
Blocked by: 01
Spec: ../spec.md

Goal: make published information readable without disrupting the animated face.

Files: modify `faces/board/index.html`; create `faces/board/cards.js` and `faces/board/cards.css` for isolated card polling/rendering.

- [ ] Consume `GET /board-cards` independently of `core.js`, with immediate/2-second polling, one in-flight request, hidden-tab pause and resume refresh.
- [ ] Render semantic Todo/Calendar panels with the spec's item limits, overflow counts, date rules and successful retrieval timestamp. Consume calendar `range.start`, exclusive `range.end` and `timezone`; retain displayed scope during loading/error and show none before a first success. Timed display uses browser-local, zero-padded 24-hour `HH:mm`.
- [ ] Implement invitation, loading, empty, provider error and connection error states; retain previous content where specified and render all external strings as text.
- [ ] Integrate desktop chip clearance, narrow-screen scrolling and cinematic hiding/restoration. Only the two labelled panel regions are focusable (`tabindex="0"`, `role="region"`, heading-based accessible name), with visible focus and normal cursor. Guard `e.target` for panel regions/descendants and future controls before global Space/C/F handling; allow native Space/arrow scrolling. Hidden panels leave the tab order.
- [ ] Smoke-check with the fixtures from 01 at 390px and 1440px via `/browse`; full sweep is spec QA Plan steps 7–9. Record evidence in this ticket's Comments.

Acceptance: published changes appear within one successful polling interval; mobile content is reachable; no fake results appear on errors; retained snapshots are visibly dated. Record QA evidence in this ticket.

## Comments

Round 3: panels are read-only; the earlier task-completion proposal is superseded.

Spec review round 1: clarified schema consumption, focus/keyboard behavior and 24-hour time formatting (1, 3, 11); consolidated QA into the spec sweep (9, 10). Retained the user's approved status (6).
