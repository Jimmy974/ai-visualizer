# 04 — Code-review fixes (round 1)

Status: blocked
Blocked by: none
Spec: ../spec.md
Review: ../code-review.md

Goal: close every blocking and should finding from code-review round 1. Do not treat nits.

- [ ] [blocking] `.scratch/board-info-cards/issues/03-sinner-google-handoff.md:18` — Live Sinner acceptance was ticked without a Sinner session. Explicitly load `docs/agents/board-info-cards.md` into Sinner, run the live skill-to-board check including QA 10 explicit-date and empty-today cases, and record honest evidence (no private contents). Untick/re-tick only if it actually ran in Sinner.
- [x] [blocking] `board_cards.py:297` — `validate_update` never checks `version`. Reject unsupported versions on CLI publish (nonzero exit, snapshot unchanged). Add a unit test. Spec/QA 4.
- [x] [should] `faces/board/cards.js:106` — Hard-coded "Sinner". Use the configured agent `name` (chip/HUD convention in `ai-visualizer.md`). Update invitation copy and any spec QA wording that hard-codes Sinner if needed for consistency.
- [x] [should] `gws_cards.py:18` — Duplicate limits/`_DATE_RE`/title cleanup. Import shared constants/helpers from `board_cards`.
- [x] [should] `gws_cards.py:82` — Duplicate range/timezone clump checks in `calendar_window` and `normalize_events`. One shared validator.
- [x] [should] `gws_cards.py:91` — Default window includes events that already ended today. Default is today's ongoing/upcoming only.
- [x] [should] `gws_cards.py:93` — 30-day fallback must show the single next event and label that range, not every event in 30 days.
- [x] [should] `.scratch/board-info-cards/issues/01-card-storage-and-feed.md:30` — Record in Comments that 01 ran before 03 discovery (historical). No code rewrite of 01 required unless a contract depends on it.
- [x] [should] `faces/board/cards.css:7` — Narrow screens: panels must scroll below the HUD, not overlap it (`z-index`/inset). QA 8: text does not overlap the HUD.

Acceptance: `python3 -m unittest discover -s tests` passes. Blocking findings 11–12 and should findings 1–3, 13–15, 18 are closed by edit (or a Comments note for 15 only). Nits stay open.

## Comments

User/coordinator waived nested Sinner live QA. Do not claim a Sinner-session check.

The gws live check recorded on ticket 03 stands (same grant, disposable `--cards-file`, not a Sinner chat). Blocking finding 11 remains open. Code fixes for version reject, configured agent name, shared constants/range validator, ongoing/upcoming today, single-event 30-day fallback, 01 historical note, and narrow HUD overlap are done.
