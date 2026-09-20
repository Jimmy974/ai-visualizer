# 01: Keep Calendar clear of the board HUD

Status: resolved
Blocked by: None (can start immediately)
Files: faces/board/cards.css

**What to build:** Reserve enough space in the desktop card layout for the top-right status block so the orb and populated live usage text remain fully visible, with Calendar below them. The reported 1440×900 layout places Calendar at y=108–314, overlapping the orb and usage. Adjust desktop spacing and the affected card height allowance together so scrolling still keeps content above the bottom HUD.

## Repository evidence

- `faces/board/cards.css:7`: fixed three-column card grid uses z-index 12 and 108px top padding; Calendar occupies the right column at line 43.
- `faces/board/cards.css:27`: cards scroll within a viewport-relative maximum height, which needs to remain compatible with the new top clearance.
- `faces/board/index.html:39`: the HUD has z-index 10; its status block is anchored at top 34px/right 56px at line 55. Orb size and usage typography scale with viewport width at lines 60 and 63.
- `faces/board/index.html:97`: the status block contains mode, clock, orb, and usage in that order; usage is initially empty and populated by `syncUsage` at line 198.
- `faces/board/cards.css:117`: widths up to 899px use a separate vertically scrolling stack starting at 220px. Cinematic hiding is defined at line 21.
- `tests/test_board_card_display.py:284`: existing CSS checks cover focus, cinematic mode, overflow, and narrow stacking; these are source checks, not rendered overlap checks.

## Acceptance criteria

- [x] At 1440×900, 1920×1080, and 2560×1440 with populated Calendar and live usage rows, Calendar's rectangle does not intersect the orb (including its outer ring) or usage text; both HUD elements and all Calendar text remain readable.
- [x] Clearance comes from layout spacing rather than only changing stacking order, hiding HUD content, or reducing its text size.
- [x] With overflowing card content at 1440×900, both cards remain keyboard focusable and scrollable, and their lower edges stay above the bottom HUD text.
- [x] At 899×900 the narrow stacked layout still scrolls, and at 900×900 the desktop layout keeps Calendar clear of the populated status block. Cinematic mode still hides the cards and restoring normal mode restores them.
- [x] `python3 -m unittest discover -s tests -p 'test_board_card_display.py'` passes with Node available; confirm the rendered acceptance criteria in a browser because this suite does not measure layout.

## Assumptions

- A CSS-only spacing correction is sufficient; use the existing desktop layout rather than introducing a new breakpoint or JavaScript positioning.
- Moving both desktop cards down together is acceptable to retain their shared top alignment. Preserve the existing narrow-layout rules and allow for the larger clamped HUD sizes on wider screens.
- Browser verification may use synthetic populated usage and card content. If running the publisher/server, use a disposable `--cards-file` path per `docs/agents/board-info-cards.md`; no Google access is needed.
- One unblocked ticket covers this change. Per the requested quick pipeline, no spec, interview, separate QA plan, or new test infrastructure is required.
