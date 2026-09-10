# 03 — Connect Sinner's Google results to card publication

Status: ready-for-agent
Blocked by: 01, 02
Spec: ../spec.md

Early-work exception: the first discovery checkbox is unblocked and must execute before ticket 01 implementation. The dependency line applies to publication/normalization implementation and live acceptance. Record discovery evidence or a concrete blocker before proceeding with the dependent work.

Goal: complete “ask Sinner → see actual Google information on the board.”

Files: create `docs/agents/board-info-cards.md` with the Sinner handoff instructions and runnable stdin examples; update `README.md` with the workflow. This document is the delivery artifact: explicitly load it into the Sinner session before using the workflow, including during live QA. No automatic installation into an assumed Sinner-home path is claimed. Include the shared `--cards-file` override in all QA invocation examples.

- [ ] EARLY / UNBLOCKED: locate and verify the existing skill can retrieve Google tasks and calendar using Sinner's current authentication. Record its exact name/path, invocation, and a structurally faithful redacted sample of each output under Comments, including date/timezone and pagination fields. Replace personal values and omit credentials. Supply this evidence to 01 before implementation; if unavailable, record the concrete blocker immediately. Do not assume a tool name or invent a second OAuth flow.
- [ ] Wire the agent workflow to publish per-card loading, normalized success or sanitized error updates through `python3 board_cards.py publish`. Preserve the other card on single-source requests.
- [ ] Normalize incomplete tasks and timed/all-day events to the spec using the verified upstream shapes. Calendar success includes `range: {start, end}` in `YYYY-MM-DD` with exclusive end and the viewer's IANA `timezone`. Honor explicit dates; otherwise use today's ongoing/upcoming events and the labelled 30-day fallback. Resolve viewer timezone before date-dependent retrieval. Loading/error updates must not replace the previous successful scope.
- [ ] Document and exercise explicit board-only clear commands. Keep Google writes outside this workflow.
- [ ] Verify normalization with representative redacted skill output: date-only tasks, all-day events, offset timestamps, multiple lists/calendars, no results and one-source failure. Confirm totals describe the fetched scope.
- [ ] Explicitly load the handoff document into Sinner with the QA `--cards-file` override. Run a live request for both tasks and calendar, then a single-source refresh, reload/server restart and explicit board clear. Record invocation and pass/fail results without private task/event contents in repo documentation.

Acceptance: actual skill results appear in the board; failures preserve prior data correctly; local persistence and clear work end to end. Fixture-only checks do not satisfy the live acceptance criterion.

If the installed skill cannot be located or accessed, record the concrete integration blocker here; do not claim completion or replace live data with examples. Any edits to an external skill need the execution session's authorized scope; this planning session edits only the scratch feature directory.

## Comments

Round 3: user accepted reuse of the existing Google skill. Its exact identity remains an implementation discovery, not an unresolved product decision.

Spec review round 1: discovery now runs first through an explicit dependency exception (7); the loaded repository document is the precise Sinner handoff artifact (8). Producer fields and isolated QA overrides match 01/02 (1, 2). Status remains user-approved (6).
