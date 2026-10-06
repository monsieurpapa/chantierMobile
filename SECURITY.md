# Security Policy

ChantierMobile handles construction-firm financial data — budgets, payroll, client
contracts, and payments — across multiple tenants (Cabinets). Security issues are taken
seriously and triaged ahead of feature work.

## Reporting a vulnerability

This is a private repository, not a public project, so please **do not** open a public
GitHub issue for a security report. Instead, email:

**dieudonneishara@gmail.com** — subject line starting with `[SECURITY]`

Include:

- A description of the issue and its potential impact
- Steps to reproduce (a minimal repro is ideal)
- Any affected URL(s), role(s), or Cabinet-isolation scenario involved

You should expect an acknowledgment within a few days. Please allow time to investigate
and ship a fix before any public disclosure.

## Supported versions

There is a single deployed line (`main`); fixes are applied there and deployed forward.
There is no older maintained branch to backport security fixes to.

## Security model summary

See [`docs/security.md`](docs/security.md) for the full write-up. In brief:

| Area | Mechanism |
|---|---|
| **Authentication** | django-allauth (username or email + password); forced password change on first login via `ForcePasswordChangeMiddleware` |
| **Session expiry** | 15-minute idle timeout (`core.middleware.SessionIdleTimeoutMiddleware`) — an inactive session is logged out with an explicit message, independent of the 15-minute `SESSION_COOKIE_AGE` hard cap |
| **Authorization** | Role-based access control enforced at the view layer (`RoleRequiredMixin`), never relying on hidden UI alone |
| **Multi-tenancy isolation** | Every tenant-scoped queryset is filtered through `CabinetAccessMixin` — a user can only ever see data from Cabinets they hold a role on (or, for superusers, the session-selected Cabinet) |
| **State-machine integrity** | Status transitions (expense approval, invoice lifecycle, site lifecycle, material requests) are validated in `model.clean()` and enforced via `full_clean()` on every write path, not just from the view that happens to expose them in the UI today |
| **Audit trail** | `BaseModel` stamps `created_by`/`updated_by` on every business record; `StatusChangeLog` records who changed a status and when, via Django's ContentTypes framework |
| **Soft delete** | Business records are never hard-deleted by the application (`BaseModel.delete()` sets `is_deleted=True`); `Model.all_objects` is the only manager that includes deleted rows |
| **Secrets** | `.env` is git-ignored; `SECRET_KEY`, database credentials, and the Redis URL are environment-sourced, never committed (see `git log` — a committed `.env` was identified and scrubbed from tracking) |
| **CSRF / XSS / clickjacking** | Default Django middleware protections are enabled (`CsrfViewMiddleware`, auto-escaping templates, `XFrameOptionsMiddleware`) |

## Known limitations / accepted risk

- `is_superuser` bypasses some application-level checks by design (e.g. self-approval
  prevention on expenses) — superuser accounts should be limited to trusted operators.
- There is no rate-limiting or brute-force lockout on the login form at the application
  layer; this is expected to be handled at the infrastructure/reverse-proxy level in
  production deployments (see `docs/guides/deployment.md`).
- Password reset / account emails depend on the configured email backend being
  production-ready (see `EMAIL_*` settings in `.env.example`) — a misconfigured email
  backend silently breaks account recovery, not an in-app vulnerability but worth
  verifying on every new deployment target.
