# 05 — Code-review fixes (round 2)

Status: resolved
Blocked by: none
Spec: ../spec.md
Review: ../code-review.md

Goal: close every blocking and should finding from code-review round 2. Do not treat nits. Do not spawn Sinner.

- [x] [blocking] `.scratch/board-info-cards/issues/03-sinner-google-handoff.md:18` — Untick the Sinner-session checkbox (or mark it waived by user). Adjust Status/Comments so the ticket does not claim a Sinner-session run. Nested Sinner QA stays waived.
- [x] [should] `gws_cards.py:172` — `calendar_window` keeps unused `today_count`/`fallback_count`. Delete it or make it delegate to `select_calendar_scope`.
- [x] [should] `gws_cards.py:418` — `--auto-scope` copies `normalize_events` without `seen` dedupe; duplicate event ids fail publish. Reuse one collect-and-dedupe helper.
- [x] [should] `faces/board/cards.css:119` — At 390px panels still cover the HUD (`top:96px` vs orb 84–118px). Scroll region must sit below the HUD; QA 8: text does not overlap.
- [x] [should] `gws_cards.py:340` — Sort calendar events by parsed instants, not raw RFC 3339 strings. Fallback `rest[0]` must pick the true next event.
- [x] [should] `gws_cards.py:167` — Fallback range label must match the 30-day window (or honestly describe the single next event), not imply a full day is listed.

Acceptance: `python3 -m unittest discover -s tests` passes. Blocking #13 and should #1, #2, #14–#16 closed by edit. Nits stay open.

## Comments

Closed round-2 blocking #13 and should #1, #2, #14–#16. Nits left open. Nested Sinner QA remains waived; ticket 03's Sinner-session box is unticked and marked waived.
