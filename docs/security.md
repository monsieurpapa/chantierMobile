# Security Model

This is the detailed companion to [`SECURITY.md`](../SECURITY.md) (which covers
vulnerability reporting). It documents how authentication, authorization, tenant
isolation, and session handling actually work, for anyone reviewing or extending them.

## Authentication

- **django-allauth**, username-or-email + password login.
- New accounts go through a forced password change on first login
  (`ForcePasswordChangeMiddleware`), redirecting to a role-gated dashboard afterward.
- Account email settings (`EMAIL_*` in `.env.example`) must point at a real backend in
  production — password reset/account confirmation silently fail against an
  unconfigured backend, which is an operational risk to check on every new deployment
  target, not an in-app vulnerability.

## Session policy

| Setting | Value | Effect |
|---|---|---|
| `SESSION_COOKIE_AGE` | 900s (15 min) | Hard cap enforced by Django's session framework itself |
| `SESSION_IDLE_TIMEOUT_SECONDS` | 900s (15 min) | Idle window enforced by `SessionIdleTimeoutMiddleware` |
| `SESSION_IDLE_TOUCH_INTERVAL_SECONDS` | 60s | How often the activity timestamp is actually rewritten (throttle, not the timeout itself) |

`core.middleware.SessionIdleTimeoutMiddleware` stamps `last_activity` in the session on
every authenticated request (subject to the 60-second write throttle) and compares the
gap on each subsequent request. Exceeding the timeout logs the user out
(`django.contrib.auth.logout`) and redirects to login with an explicit
"votre session a expiré" message — never a silent drop into an anonymous session that
looks like a bug. See [ADR 0004](architecture/decisions/0004-session-idle-timeout.md)
for the full reasoning, including why the write is throttled.

Exempt from the idle check: static/media/i18n asset paths and the login/logout views
themselves (`IDLE_TIMEOUT_EXEMPT_PATH_PREFIXES` / `IDLE_TIMEOUT_EXEMPT_URL_NAMES` in
`core/middleware.py`) — so the timeout logic can never block the one page you need to
log back in.

## Authorization: roles within a Cabinet

Access is never a single global role — it's `(user, cabinet, role)` via
`UserCabinetRole`. See [`architecture/overview.md`](architecture/overview.md#roles) for
the full role list and [ADR 0001](architecture/decisions/0001-cabinet-multi-tenancy.md)
for why Cabinet is the tenancy boundary.

**A `UserCabinetRole` only grants access once its `status` is `APPROVED`.** A
superadmin can stage an assignment as `PENDING` before it takes effect; every RBAC
helper (`CabinetAccessMixin`, `RoleRequiredMixin`, `can_act_for_cabinet`,
`can_view_cabinet`, `has_role`, and `User.approved_cabinet_roles`, which all of the
above are built on) filters on `status=APPROVED`, so a `PENDING` grant authorizes
nothing yet. This was fixed 2026-10-06 — previously none of these helpers checked
`status` at all, so a freshly-created `PENDING` row already granted full access.
Any new access-control code should go through `User.approved_cabinet_roles` (or an
explicit `status=ApprovalStatus.APPROVED` filter) rather than the bare
`user.cabinet_roles` reverse manager, which still returns every status — that bare
manager remains correct for a purely informational listing (e.g. a profile page
showing a user their own pending assignments).

### Representative permission matrix

Drawn directly from `allowed_roles` declarations across the codebase (not exhaustive —
see each app's `docs/modules/<app>.md` for the complete, current list per view).

| Action | Roles |
|---|---|
| Approve/reject an expense | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `ACCOUNTANT` |
| Validate a material request (1st stage) | `MAGASINIER`, `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL` |
| Final-authorize a material request / avenant (2nd stage) | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL` (`FINAL_AUTHORIZATION_ROLES`) |
| Create/edit a Site, budget reporting | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` |
| Close a project phase | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL` |
| Submit/review own-site planning | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER`, `ENGINEER` (own site only) |
| Contracts / invoices / payments | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `ACCOUNTANT` (some views add `CHIEF_ENGINEER` or `CASHIER`) |
| Purchase orders, stock receiving | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` (financier sign-off adds `ACCOUNTANT`) |
| Pricing library / DQE | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` |
| Personnel / HR administration | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` (some narrowed to director-tier only) |

Two enforcement layers exist, and a new view needs the one matching how it's built:

- **Class-based views** set `allowed_roles = [...]` and mix in `RoleRequiredMixin`
  (optionally overriding `get_role_cabinet()` to scope the check to one Cabinet's
  resource instead of "any Cabinet the user belongs to").
- **Function-based views** (most approve/reject/send/validate endpoints) call
  `can_act_for_cabinet(request, cabinet, allowed_roles)` explicitly before mutating
  anything, or the looser `can_view_cabinet(request, cabinet)` for shared,
  non-role-gated actions like commenting.

**`@login_required` alone is never sufficient** — it proves identity, not role or
Cabinet membership. Every state-changing endpoint needs one of the two checks above.
Reviewers: a PR adding a new mutation without either is a correctness bug, not a style
nitpick.

### A note on duplicated role lists

`core/approvals.py` (the pending-approvals inbox) intentionally hardcodes its own copy
of each action's role list (e.g. `EXPENSE_APPROVAL_ROLES`) rather than importing the
action view to read `allowed_roles` off it. This is a deliberate choice to avoid
pulling every app's view module into one shared aggregator — but it means **the two
copies must be kept in sync by hand**. If you change who can approve an expense, check
`core/approvals.py` for a matching list to update; the module's own docstring flags
this.

## Tenant isolation

`CabinetAccessMixin.get_queryset()` filters every class-based list/detail view to the
current user's Cabinet(s) via `cabinet_lookup_field` (direct or chained FK path). A
regular user with no `UserCabinetRole` anywhere gets an empty queryset, not an error —
fail closed, not open. See [ADR 0001](architecture/decisions/0001-cabinet-multi-tenancy.md).

Self-approval/self-administration is explicitly blocked where it matters, all
following the same shape — `ValidationError` when the acting user is also the
requester, bypassable only by `is_superuser` (accepted as an operator-trust
boundary, not a gap — see `SECURITY.md`'s known limitations):
`Expense.approve()`, `Avenant.approve()`/`reject()`, and `MaterialRequest`'s
two-stage `magasinier_validate()`/`authorize()`/`reject()`.

## State integrity

Every status field is validated in the owning model's `clean()` and enforced via
`full_clean()` on every write path, not only from the view that currently exposes the
transition. See [ADR 0003](architecture/decisions/0003-state-machines-in-model-clean.md)
and the state-machine diagrams in
[`architecture/overview.md`](architecture/overview.md#status-state-machines).

## Audit trail

- `BaseModel` stamps `created_by`/`updated_by` on every business record.
- `StatusChangeLog` (generic, via ContentTypes) records status transitions where it's
  wired in (currently site updates and payment creation) — see
  [ADR 0002](architecture/decisions/0002-soft-delete-base-model.md).
- Soft delete means a record's history is never destroyed by an in-app delete action;
  `Model.all_objects` surfaces it for an investigation if needed.

## Transport and framework defaults

Django's standard protections are enabled and not overridden: CSRF middleware on all
state-changing requests, auto-escaping in Django templates (XSS), `X-Frame-Options`
(clickjacking). `DEBUG` must be `0`/unset in any environment reachable by anyone but a
developer — see `docs/guides/deployment.md`.

## Secrets handling

`.env` is git-ignored. `SECRET_KEY`, database credentials, and `REDIS_URL` are
environment-sourced only. A `.env` file was previously found committed to the
repository and was scrubbed from tracking (see `CHANGELOG.md`, 2026-09-18 entry) — if
you ever suspect a secret was committed, rotate it; removing it from a future commit
does not remove it from git history.

## Reporting a vulnerability

See [`SECURITY.md`](../SECURITY.md).
