# 0004 — 15-minute session idle timeout via middleware, not cookie age alone

**Status**: Accepted

## Context

Users on this platform (directors, engineers, cashiers) can leave a session open on a
shared or semi-public device (a site office computer, a tablet on a chantier) while
handling financial approvals, payroll, and client invoices. Relying solely on
`SESSION_COOKIE_AGE` (a hard expiry from the cookie's creation time) logs people out even
while they're actively working, which trains users to treat timeouts as an annoyance,
while not logging out an idle-but-still-"valid" session mid-way through its window.

## Decision

Add `core.middleware.SessionIdleTimeoutMiddleware`, which stamps `request.session['last_activity']`
on each authenticated request (throttled — see below) and compares it against
`SESSION_IDLE_TIMEOUT_SECONDS` (15 minutes). If the gap exceeds the timeout, the
middleware logs the user out and redirects to login with an explicit
"your session expired" message, rather than silently dropping into an anonymous state.
`SESSION_COOKIE_AGE` is set to the same 15 minutes as a second, independent backstop
enforced by Django's session framework itself.

The activity stamp is **throttled** to once per `SESSION_IDLE_TOUCH_INTERVAL_SECONDS`
(60 seconds) rather than rewritten on every single request: a session write is a
database round-trip (`BEGIN` / `UPDATE django_session` / `COMMIT`, always wrapped in a
transaction by Django's session backend), and writing it on every request under active
use multiplies the write load for no behavioral benefit — the user is clearly active
either way, whether the stamp is accurate to one second or to sixty.

## Consequences

- An idle user is logged out with a clear reason, not a confusing redirect to login with
  no explanation.
- An active user is never logged out mid-session, because every request within the
  timeout window resets the clock (subject to the 60-second throttle, which only delays
  the *recorded* activity time, never the actual timeout check — a user active every
  10 seconds is still "active" even though the stored timestamp only updates once a
  minute).
- This added a `BEGIN`/`UPDATE`/`COMMIT` triple to a session's first authenticated
  request. It showed up as a measurable (~2.6x) slowdown in the test suite, since each
  of ~600 tests starts a fresh session and pays this cost once; the throttle doesn't
  eliminate it; it was accepted as the real cost of the feature and documented in
  `tests/test_performance.py`'s query-ceiling comments rather than worked around.
- Static/media/i18n paths and the login/logout views themselves are exempted
  (`IDLE_TIMEOUT_EXEMPT_PATH_PREFIXES` / `IDLE_TIMEOUT_EXEMPT_URL_NAMES`) so the timeout
  logic never interferes with the pages needed to log back in.
