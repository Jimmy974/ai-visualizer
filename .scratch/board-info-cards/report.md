# Report: board-info-cards

Pipeline: herdr-orchestrate v2 (architect gpt-6-astra, executor grok-4.6, reviewer claude-fable-5-1, auditor claude-opus-5). Presence: telegram. Original kickstart had no `--pr`; user later asked for a PR after this report. QA gate did not pass.

## 1. Spec

- Architect grill (telegram): 3 question rounds, then ticket-list approve.
  - R1: first cards, data source, todo/calendar content, actions, layout, empty/error, timezone.
  - User: Sinner fetches Google tasks/calendar; board only displays.
  - R2: skill can/cannot, panels over circuit, read-only, refresh-on-ask, persist across reload.
  - User: `ok` (all recommends).
- Tickets approved; statuses set to `ready-for-agent`; `## QA Plan` and `## Review Log` added after finalize.
- Reviewer rounds: 2.
  - R1 `CHANGES_REQUESTED`: 2 blocking (calendar `range`/`timezone` schema; `--cards-file` override), 8 should, 3 nit.
  - Architect revised; rebuttals on ticket status (user-approved `ready-for-agent`) and enum-widening wording — both accepted.
  - R2 `VERDICT: APPROVED` with leftover shoulds (prose cycle, TZ launch, Windows wording) folded later in implementation.

## 2. Implementation

| Ticket | Commit | When (BST) |
|---|---|---|
| spec + tracker | `75a7f84` spec: board-info-cards | 16:56 |
| meta fixed-point | `b5c8455` | 16:56 |
| 01 persist/serve | `57eee97` | 17:13 |
| 02 board display | `c8b01f5` | 17:50 |
| 03 Sinner/gws handoff | `3c8f935` | 18:07 |
| 04 review fixes (code-only) | `d9bf73f` | 18:34 |
| 05 review fixes r2 | `cc82624` | 18:44 |

- 01: `board_cards.py`, `GET /board-cards`, stdin publish/clear, tests.
- 02: `faces/board/cards.js` + `cards.css`, polling, invitation/loading/error/empty.
- 03: `gws_cards.py` + `docs/agents/board-info-cards.md`; live `gws` (not nested Sinner) recorded on the ticket.
- 04: Status `blocked` — nested Sinner QA waived by user; other review checkboxes ticked.
- 05: Status `resolved`.

## 3. Code review

- Rounds: 3 (cap). Final `VERDICT: APPROVED` in `code-review.md`.
- R1 `CHANGES_REQUESTED`: missing CLI version reject; Sinner-session claim; calendar window/fallback; HUD; name hard-code.
- R2 `CHANGES_REQUESTED`: ticket 03 still claimed Sinner QA; remaining HUD; sort/label/dedupe.
- R3 `APPROVED`, 0 blocking. One **should** left open (wide Calendar covers HUD) — user chose `qa` instead of ticket 06.

Summary line from final review: Standards 0 blocking / 0 should / 14 nit; Spec 0 blocking / 1 should / 8 nit. Worst remaining: wide layout Calendar panel covers orb and `#usage`.

## 4. QA

- Rounds: 1. `VERDICT: FAIL`.
- 9 PASS (steps 1–7, 9, 12), 1 FAIL (step 8), 2 BLOCKED (steps 10–11, nested Sinner / live Google waived).
- FAIL: at 1440px `#card-calendar` (`z-index: 12`) covers `#orb` and live `#usage`. Evidence: `.scratch/board-info-cards/qa-evidence/08-1440-overview.png`.
- Headless Chrome + browser-harness; user browser unused. Server `--port 8797 --cards-file` disposable.

## 5. Nits left open

From `code-review.md` round 3, verbatim:

1. [nit] `gws_cards.py:113` — `_event_start_instant` duplicates `_overlaps_today_upcoming` local-midnight datetime; sort lambda appears three times.
2. [nit] `faces/board/cards.js:66` — JS sorts by local day then all-day first; Python sorts by instant; nothing ties the rules.
3. [nit] `gws_cards.py:336` — `collect_event_items` vs `_collect_events`; 30-day window is a bare literal.
4. [nit] `tests/test_board_card_display.py:293` — inline `__import__("re").search(...)`.
5. [nit] `faces/board/cards.css:123` — magic `top: 220px` / `z-index: 9` coupled to HUD.
6. [nit] `faces/board/cards.js:368` — invitation text rebuilt outside `panelView`; `"JARVIS"` fallback repeats.
7. [nit] `gws_cards.py:20` — re-exports including private `_DATE_RE`.
8. [nit] `gws_cards.py:103` — repeated `allDay` branches.
9. [nit] `board_cards.py:279` — card-id if-chains.
10. [nit] `board_cards.py:332` — `_validate_stored_card` repeats `validate_update`.
11. [nit] `board_cards.py:121` — `%` formatting vs repo f-strings.
12. [nit] `tests/test_board_cards.py:1` — no copyright/SPDX (also other new tests).
13. [nit] `server.py:120` — `_flag_value` beside inline argv parsing.
14. [nit] `board_cards.py:476` — two different `_dump`s; `kick` vs `pollNow`.
15. [nit] `faces/board/cards.css:120` — narrow `#echo` overlaps card region bottom.
16. [nit] `issues/03-sinner-google-handoff.md:62` — QA 10 explicit-date / empty-today have no live record.
17. [nit] `docs/agents/board-info-cards.md:137` — `totalCount` wording vs fallback.
18. [nit] `gws_cards.py:164` — fallback does not assert event is inside today+30.
19. [nit] `gws_cards.py:89` — unknown timezone falls back to UTC.
20. [nit] `board_cards.py:300` — `"version": true` accepted (`True == 1`).
21. [nit] `faces/board/cards.js:85` — multi-day all-day shows start date only.
22. [nit] `server.py:123` — `--cards-file` with no value silently ignored.

## 6. Open items

- QA step 8 FAIL / review should #15: wide Calendar covers HUD orb and usage text.
- Nested Sinner live QA waived (ticket 04 blocked on that checkbox; 03 box unticked and marked waived).
- QA steps 10–11 BLOCKED (Sinner session + live Google failure).
- Ticket 04 remains `Status: blocked`.
- User skipped ticket 06 (wide HUD) then requested report + PR anyway.

Recommendation: fix wide `z-index`/padding so Calendar does not cover `.hud`, re-run QA step 8, then load `docs/agents/board-info-cards.md` in Sinner for the live handoff.

## 7. Git

- Branch: `feat/board-info-cards`
- Worktree: `/Users/jimmywong/.herdr/worktrees/ai-visualizer/feat-board-info-cards`
- Repo: `/Users/jimmywong/source/jarvis-agent-home/ai-visualizer`
- Base: `main` (`24dbcc5`)
- Fixed point: `75a7f84`
- Range: `75a7f84..HEAD` (implementation `57eee97..cc82624`)
- PR URL: https://github.com/Jimmy974/ai-visualizer/pull/1

Finish without a PR:

```
git -C /Users/jimmywong/source/jarvis-agent-home/ai-visualizer merge feat/board-info-cards
```

Clean up:

```
herdr worktree remove --workspace wH
```

QA screenshots were not committed (47MB). They remain at `.scratch/board-info-cards/qa-evidence/` in the worktree.

## 8. Try it yourself

All commands run from the worktree and use a disposable snapshot file, so your real `ai-visualizer.json` and the server on 8790 are untouched.

```bash
cd /Users/jimmywong/.herdr/worktrees/ai-visualizer/feat-board-info-cards
export CARDS=/tmp/board-cards-demo.json

# 1. Start the server on a spare port
python3 server.py --no-open --port 8797 --cards-file $CARDS
```

2. Open **http://127.0.0.1:8797/faces/board/index.html** — the board shows an invitation ("Ask Sinner for your tasks/calendar") and two empty cards.

3. Publish your real Google data (second terminal, same `$CARDS`):

```bash
python3 gws_cards.py tasks | python3 board_cards.py --cards-file $CARDS publish
python3 gws_cards.py events --timezone Europe/London --auto-scope | python3 board_cards.py --cards-file $CARDS publish
```

Within a few seconds, without reloading, the Todo card lists your open tasks (8 at QA time) and the Calendar card shows today's remaining events, or the next one within 30 days with its date labelled.

4. Error state — the card shows the error but keeps its previous items:

```bash
python3 gws_cards.py error --card calendar --message "Google down" | python3 board_cards.py --cards-file $CARDS publish
```

5. Reset to the invitation state:

```bash
python3 board_cards.py --cards-file $CARDS clear --card all
```

Stop the server with Ctrl-C. Full publish/clear/scope reference: `docs/agents/board-info-cards.md`.

**Not demonstrable yet:** at 1440px and wider the Calendar card covers the top-right HUD (open item, `cards.css:10,16`). Triggering the publish from Sinner itself (rather than piping by hand) needs `docs/agents/board-info-cards.md` loaded into a Sinner session first; that path was not exercised in QA.

## 9. Panes

Workspace `wH` (board-info-cards), left open:

- architect — Codex gpt-6-astra — `wH:p1`
- reviewer — Claude claude-fable-5-1 — `wH:p2`
- executor — Grok grok-4.6 — `wH:p3`
- auditor — Claude claude-opus-5 — `wH:p4`
