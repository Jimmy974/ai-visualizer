## Report
At 1440px and wider the Calendar card (#board-cards, z-index 12) sits over the top-right HUD: the orb (#orb) and the live usage text (#usage) are hidden under it.

## Context
- Feature: board-info-cards (PR #1, merged 9389120)
- Found by: qa-agent (step 8) and code-review round 3 finding #15
- Path hint: faces/board/cards.css:10,16 (z-index / wide-layout padding)

## Expected / Actual
Expected: at 1440x900 the HUD orb and usage text stay visible; cards sit below or beside them.
Actual: #card-calendar spans y 108-314 and covers #orb (y 86-123) and #usage (y 132-160). Evidence: qa-evidence/08-1440-overview.png from the run.
