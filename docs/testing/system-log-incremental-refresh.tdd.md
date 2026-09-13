# System log incremental refresh TDD evidence

## Source and user journeys

No plan file was provided. The guarantees were derived from the requested behavior:

- As an administrator, I want repeated log refreshes to parse only newly appended bytes so historical log volume does not make every refresh slow.
- As an administrator, I want automatic system-log refreshes every 30 seconds so the page produces fewer overlapping requests.

## RED and GREEN evidence

| Guarantee | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| Appending a log line does not reparse the existing file | `tests/test_file_log_collector.py:test_appended_log_content_is_parsed_without_reparsing_existing_file` | `python -m unittest discover -s tests -p test_file_log_collector.py` failed because `_parse_file` was called 2 times instead of 1 | The same command passed 12/12 tests |
| Truncated log files fall back to a full safe reparse | `tests/test_file_log_collector.py:test_truncated_log_file_falls_back_to_full_reparse` | Covered during the review loop after identifying the rotation/truncation fallback as mandatory acceptance evidence | The same command passed 12/12 tests |
| Logs appended while a full parse is running are not skipped by the stored offset | `tests/test_file_log_collector.py:test_append_during_full_parse_is_not_marked_as_already_consumed` | Covered during the review loop after finding the parser could advance the offset past bytes it had not parsed | The same command passed 12/12 tests |
| Monitor-buffered traceback continuations are not duplicated by disk refresh | `tests/test_file_log_collector.py:test_monitor_and_disk_increment_do_not_duplicate_traceback_continuation` | Covered during the review loop after finding shared dicts between the live buffer and disk cache | The same command passed 12/12 tests |
| The system-log refresh interval and user-facing text are 30 seconds | `tests/test_system_logs_frontend_contract.py` | The contract test failed because the 30-second constant was absent | The same command passed 2/2 tests |
| Automatic refreshes do not overlap while a log request is already in flight | `tests/test_system_logs_frontend_contract.py:test_system_logs_refresh_uses_ref_guard_against_overlapping_requests` | Covered during the review loop after identifying stale React timer closures as a loading regression risk | The same command passed 2/2 tests |

## Full verification

- `python scripts/run_tests.py --quality --database temp`: 563 tests passed.
- Coverage: 28.8%, above the repository's configured 20% gate.
- The E2E runner built and served the current frontend; 13 browser E2E tests passed.
- TypeScript type check, detached Vite production build, three Compose configuration checks, and `git diff --check` passed.
- Rebuilt runtime smoke test: Docker reported `healthy`; `/health` and `/` returned HTTP 200.
- After the final rebuild, the runtime collector returned the newest 1,000 of 1,685 entries in 56.9 ms on initial parsing and 38.1 ms from cached offsets.

## Known gaps and merge evidence

- The original 66 MB historical log set had already been cleared, so the live smoke test used the current 3,241-entry dataset. The unit test verifies the no-reparse behavior directly.
- No checkpoint commits were created because the working tree already contained overlapping uncommitted changes; RED and GREEN evidence is preserved here instead.
