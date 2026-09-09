# Permanent localhost login session: TDD evidence

> Historical record: this behavior was superseded by conditional session expiry. Manual-login sessions now use a TTL, while only environment-backed auto-login sessions remain non-expiring.

## Source and user journey

- Source: the user request in this task; no external plan document was used.
- User journey: As a localhost admin user, I want my login credential to remain valid regardless of elapsed time so that I do not need to sign in again every 24 hours.

## Execution record

### Login credentials no longer expire with time

- Implementation: removed the 24-hour expiry check from `verify_token`; explicit logout can still revoke the credential.
- RED: `python -m unittest discover -s tests -p "test_auth_session.py" -v`
- RED result: `Ran 1 test`, failed; a known credential with timestamp `0` returned `None`.
- GREEN: reran the same command.
- GREEN result: `Ran 1 test in 0.001s`, `OK`.
- Full regression: `python -m unittest discover -s tests -p "test_*.py"`.
- Full regression result: `Ran 385 tests in 56.991s`, `OK`.

## Test specification

| # | Guarantee | Test | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | An existing login credential remains valid regardless of how long ago it was issued | `tests/test_auth_session.py:AuthSessionTests.test_session_does_not_expire_with_time` | Unit | PASS | Target test went RED, then GREEN |
| 2 | The change does not break existing Python behavior | `python -m unittest discover -s tests -p "test_*.py"` | Regression | PASS | 385 tests, OK |

## Coverage and known boundaries

- Coverage command: `python -m coverage run --branch --source=app -m unittest discover -s tests -p "test_*.py"`, followed by `python -m coverage report -m`.
- Result: the repository-wide `app` package coverage is 37%; the existing suite does not meet the 80% global target. The permanent-session branch added by this change is exercised directly by the focused test.
- Login credentials are still held in server-process memory, so restarting the server process revokes existing credentials. This task only removes the previous 24-hour time-based expiry rule.

## Merge evidence

- RED commit: `233a606 test: 添加登录态永久有效回归测试`
- GREEN commit: `c3342b7 fix: 取消后台登录态时间限制`
