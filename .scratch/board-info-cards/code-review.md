VERDICT: APPROVED

# Code review: board-info-cards (round 3)

- Fixed point: `75a7f84a7a96dea7666f3f142b64607da39ed913` (diff `git diff 75a7f84...HEAD`, three-dot)
- Commits: `b5c8455` meta: record spec fixed-point · `57eee97` 01: persist and serve board cards · `c8b01f5` 02: display Todo and Calendar on the board · `3c8f935` 03: connect Sinner Google results to board cards · `d9bf73f` 04: code-review fixes except nested Sinner QA · `cc82624` 05: close round-2 blocking and should review findings
- Spec: `.scratch/board-info-cards/spec.md`, checked against its text at the fixed point. Tickets: `.scratch/board-info-cards/issues/01..05`.
- Standards sources: `CONTRIBUTING.md` (only asks for work "in the style of the rest of the codebase"), `ai-visualizer.md`, the code as it stood before this diff, and the Fowler smell baseline.
- Round-2 fixes: `issues/05-review-fixes-r2.md`. The user explicitly waived the nested Sinner live QA, so the missing Sinner-session run is not a finding. No artifact claims it happened any more.
- Tests: `python3 -m unittest discover -s tests` passes (43 tests). The layout was measured in a headless browser at 390x844, 900, 1440x900 and 1920 wide, against a throwaway snapshot file.

The two axes were reviewed separately and are not reranked against each other.

## Standards

No finding is a hard violation of a documented standard. Everything below is a judgement-call nit.

**New in this round**

1. [nit] `gws_cards.py:113` — **Possible Duplicated Code (judgement call).** The new `_event_start_instant` (`gws_cards.py:113-114`) builds a local-midnight datetime the same way `_overlaps_today_upcoming` does (`gws_cards.py:130-134`). The sort lambda `lambda item: _item_sort_key(item, timezone)` also appears three times (`gws_cards.py:157,163,323`).
2. [nit] `faces/board/cards.js:66` — **Possible Duplicated Code (judgement call).** `sortCalendarItems` sorts by local day, then all-day first. The Python side (`gws_cards.py:118`) now sorts by instant. The two rules agree today but have nothing tying them together, so they can drift apart.
3. [nit] `gws_cards.py:336` — **Possible Mysterious Name (judgement call).** The public `collect_event_items` sits next to the private `_collect_events` (`gws_cards.py:266`), and nothing in the names says which one dedupes. The 30-day window is a bare literal at `gws_cards.py:166`.
4. [nit] `tests/test_board_card_display.py:293` — **Style drift (judgement call).** An inline `__import__("re").search(...)` breaks the codebase's habit of importing at the top of the file. `CONTRIBUTING.md` asks for work in "the style of the rest of the codebase".

**Carried from round 2 (nits, left open on purpose by tickets 04/05)**

5. [nit] `faces/board/cards.css:123` — **Magic numbers and z-index coupling (judgement call; r2 #6, changed).** Narrow screens now use `top: 220px` (`faces/board/cards.css:119`) with `z-index: 9`. This works only because `.hud` is at 10 and `#vig` at 8 (`faces/board/index.html:39,79`). The same kind of hard-coded offset appears at `faces/board/cards.css:16,31`. See #15.
6. [nit] `faces/board/cards.js:368` — **Possible Duplicated Code (judgement call; r2 #3).** The invitation text is built again outside `panelView` (`faces/board/cards.js:107`). The `"JARVIS"` fallback repeats at `faces/board/cards.js:23,106,313`.
7. [nit] `gws_cards.py:20` — **Possible Middle Man (judgement call; r2 #4).** The file re-exports aliases from `board_cards` (`gws_cards.py:20-23`), including the private `_DATE_RE`. `validate_range_and_timezone` (`gws_cards.py:76`) still mostly delegates onward. The today-range call now appears twice (`gws_cards.py:158,169`).
8. [nit] `gws_cards.py:103` — **Possible Repeated Switches (judgement call; r2 #5).** The `allDay` branch also appears at `gws_cards.py:112,119,127` and `faces/board/cards.js:60,71,84`.
9. [nit] `board_cards.py:279` — **Possible Repeated Switches / Primitive Obsession on card ids (judgement call; r2 #7).** Also at `board_cards.py:320,356,538`, `gws_cards.py:370,373` and `faces/board/cards.js:82,102,113,126,132,363`.
10. [nit] `board_cards.py:332` — **Possible Duplicated Code (judgement call; r2 #8).** `_validate_stored_card` repeats the checks in `validate_update` (`board_cards.py:297`).
11. [nit] `board_cards.py:121` — **`%` formatting drifts from the repo's f-string style (r2 #9).** It also appears at `board_cards.py:130,135,138,148,163,168,417,503,592`.
12. [nit] `tests/test_board_cards.py:1` — **No copyright/SPDX header (r2 #10).** The same applies to `tests/test_board_card_display.py:1` and `tests/test_gws_cards.py:1`.
13. [nit] `server.py:120` — **Possible Duplicated Code (judgement call; r2 #11).** `_flag_value` sits beside the inline argv parsing at `server.py:109-117`.
14. [nit] `board_cards.py:476` — **Possible Mysterious Name (judgement call; r2 #12).** This `_dump` returns bytes, while `gws_cards.py:360` `_dump` returns a string. `kick` (`faces/board/cards.js:214`) would read better as `pollNow`.

**Round-2 Standards findings resolved**

- **#1:** `calendar_window` is deleted, and a test asserts it is gone (`tests/test_gws_cards.py:253`).
- **#2:** `--auto-scope` now uses the shared, deduping `collect_event_items` (`gws_cards.py:400`), covered by a duplicate-id CLI test.

## Spec

**(a) Missing or partial**

15. [should] `faces/board/cards.css:16` — **On wide screens the Calendar panel covers the top-right HUD (new; round 2 only measured the narrow layout).** The wide grid uses `padding: 108px 48px 92px` at `z-index: 12`, above `.hud`'s 10. At 1440x900 the Calendar panel spans y 108–350px and x 1018–1392px. That covers the orb (y 86–123px) and all of the live `#usage` text (y 132–174px, x 1301–1384px). The same happens at 900 and 1920 wide. Ticket 02 still records "1440x900 … clear" (`.scratch/board-info-cards/issues/02-board-card-display.md:28`), which isn't accurate. Spec QA 8: "the wide center chip stays visible and text does not overlap the HUD."
16. [nit] `faces/board/cards.css:120` — **On narrow screens the transcript line (`#echo`) overlaps the bottom of the cards region (new).** The region ends at `bottom: 80px`, and `#echo` sits at 76px and wraps upward. At 390x844 it spans y 746–768px against a region bottom of 764px, and it prints over the Calendar footer. Spec QA 8: "text does not overlap the HUD."
17. [nit] `.scratch/board-info-cards/issues/03-sinner-google-handoff.md:62` — **QA 10's explicit-date and empty-today checks have no live record (carried from r2 #13, residual).** The live `gws` check covered only today's range. Both cases have unit tests (`tests/test_gws_cards.py:191,402`), and both could run through `gws` without a Sinner session. Spec: "Verify an explicit date request and an empty-today fixture."

**(b) Scope creep**

None.

**(c) Implemented but looks wrong**

18. [nit] `docs/agents/board-info-cards.md:137` — **The doc's `totalCount` wording contradicts the fallback (new).** The doc says "`totalCount` describes the fetched window", but the fallback publishes `totalCount` 1 under a 30-day range label (`gws_cards.py:168`). The board then shows the 30-day range with one event and no "+N more", which can read as "the only event in 30 days". The labelling itself follows the spec ("fetch the next event within the next 30 days and label that range"); only the wording is inconsistent.
19. [nit] `gws_cards.py:164` — **The fallback never checks that the chosen event falls inside today to today+30 (new).** If the payload covers a wider window, the published event can sit outside its own range label.
20. [nit] `gws_cards.py:89` — **An unknown timezone still falls back to UTC for "today" (carried from r2 #17).** Spec: "If Sinner cannot determine the viewer timezone, it asks within the task conversation before a timezone-dependent Google query."
21. [nit] `board_cards.py:300` — **`"version": true` is still accepted (carried from r2 #18).** Python treats `True == 1`, and `publish` exits 0. Spec: "reject invalid types … unsupported versions".
22. [nit] `faces/board/cards.js:85` — **A multi-day all-day event still shows only its start date (carried from r2 #19).** Spec: "preserve all-day dates and label them 'All day.'"
23. [nit] `server.py:123` — **A `--cards-file` flag with no value is still silently ignored (carried from r2 #20).** `board_cards.py` exits with an error in the same case.

**Round-2 Spec findings resolved**

- **#13:** ticket 03's live box (`03-sinner-google-handoff.md:18`) is unticked and marked "Waived by user". Lines 28 and 59 state no Sinner session was run, and no ticket, README or handoff doc claims one.
- **#14:** at 390x844 the region now starts at 220px, below the orb (y 84–118px) and a three-line `#usage` (y 127–165px). There is no overlap at the top.
- **#15:** events are sorted by parsed instants in the viewer's timezone (`gws_cards.py:118`). All-day events count as local midnight and win ties. Mixed offsets are covered by the test at `tests/test_gws_cards.py:255`.
- **#16:** the fallback range is today to today+30 (`gws_cards.py:165-167`). The doc (`docs/agents/board-info-cards.md:97`) and the board label (`faces/board/cards.js:134`) match it.
- **Dedupe:** `normalize_events` and `--auto-scope` now share `collect_event_items` (`gws_cards.py:336,356,400`), covered by the test at `tests/test_gws_cards.py:442`.

## Summary

- **Standards:** 14 findings (0 blocking, 0 should, 14 nit). The worst are #2, the Python and JS calendar sort rules that can drift apart, and #5, the narrow-layout `z-index: 9` coupling to the HUD.
- **Spec:** 9 findings (0 blocking, 1 should, 8 nit). The worst is #15: on the default wide layout the Calendar panel covers the orb and live usage text, failing QA 8's "text does not overlap the HUD".
