# 01 — Persist and serve board cards

Status: resolved
Blocked by: none
Spec: ../spec.md

Goal: provide the durable, validated boundary between Sinner and the board.

Files: create `board_cards.py` and `tests/test_board_cards.py`; modify `server.py` (including `DEFAULTS`), `ai-visualizer.json.example`, and configuration/CLI documentation in `README.md`.

Before implementation, consume ticket 03's early discovery evidence. That checkbox runs without waiting for this ticket; stop and record an actual skill-access blocker before building against assumed upstream shapes.

Portability: use an `O_CREAT|O_EXCL` lock file, 5-second contention timeout and finally-based release; no `fcntl`. Owner-only permissions apply on POSIX and are best-effort elsewhere. Parse RFC 3339 `Z`/offset timestamps with a small validated stdlib parser rather than adding a Python 3.11 floor. Document stale-lock recovery and test Windows-compatible behavior.

- [x] Implement the spec's version-1 card schema and limits, including calendar-ready `range: {start, end}` with real `YYYY-MM-DD` dates and exclusive end greater than start, plus trimmed non-empty `timezone`. Retain successful range/timezone during loading/error; omit them before first success.
- [x] Implement shared path precedence: `--cards-file` on both entry points, then `board_cards_file` config, then default; expand home paths and resolve relative paths against the repo root. Refuse resolved/symlinked paths under the static root with nonzero exit and a clear message before startup or writes. All tests use the override with disposable paths.
- [x] Implement stdin `publish` and explicit `clear` commands, portable locked merge and atomic persistence. Reject older attempt timestamps; accept equal timestamps with last serialized writer winning.
- [x] Add read-only `GET /board-cards`, including empty storage and controlled corrupt-storage responses; preserve `/state`, `/config`, and `/mic` behavior.
- [x] Add standard-library unit tests for invalid input preserving bytes, per-card merging, overlapping writers, lock timeout/release, older rejection and equal-timestamp acceptance, loading/error retention, successful empty results, clearing and reload from disk. Cover required ready range/timezone, missing/invalid dates and blank timezone, exclusive-end ordering, retained range/timezone, first-fetch failure without invented scope, `Z`/offset parsing, override precedence on both entry points and static-root/symlink rejection.
- [x] Exercise the endpoint for missing, valid and corrupt snapshots and verify no-store headers. Run `python3 -m unittest discover -s tests`.

Acceptance: snapshots survive a new process; invalid or older updates cannot overwrite good data; neither credentials nor data files are served through static paths. The exact JSON and CLI contracts are those in the spec and must be available to tickets 02/03.

## Comments

Round 3: durable local publication follows the repo's file-backed bus convention; no browser writes are introduced.

Spec review round 1: addressed findings 1, 2, 4, 5 and 12; consume early discovery from 03 (finding 7). Status remains user-approved `ready-for-agent`; see spec Review Log finding 6.

Ticket 03's discovery checkbox is still open and this worktree has no Google skill identity, invocation, or redacted output samples. 01 implements the spec's version-1 card schema rather than assumed upstream Google shapes.
