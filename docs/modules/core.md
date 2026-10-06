# `core`

`core` is the shared-infrastructure app: it owns no business data of its own (no Site,
no Expense, no Invoice) and instead provides the base model classes every other app
builds on, the RBAC primitives that enforce Cabinet multi-tenancy, and the
cross-cutting features added during the Directors/Engineers audit — the dashboard, the
pending-approvals inbox, in-app notifications, global search, and the session/password
middleware. If a behavior needs to be consistent across finance, materials, projects,
personnel, revenue, pricing, procurement and tasks, it almost certainly lives here.

## Models

### `BaseModel` (abstract — `core/models.py`)

Composed from three abstract mixins; nearly every business model across every app
inherits it:

| Mixin | Fields | Notes |
|---|---|---|
| `SoftDeleteModel` | `is_deleted`, `deleted_at` | `delete()` flips the flag instead of issuing SQL DELETE. `Model.objects` (default manager) excludes deleted rows; `Model.all_objects` includes them. **There is no hard-delete path through the application.** |
| `AuditableModel` (extends `TimeStampedModel`) | `created_by`, `updated_by` (FK to `accounts.User`), `created_at`, `updated_at` | Who/when touched this record, maintained by convention at each write site (not automatically — see Gotchas). |
| — | `unique_id` (UUID) | A public-safe identifier for URLs that shouldn't leak the auto-increment PK (e.g. `projects:site_detail`). |

### `StatusChangeLog` (`core/models.py`)

A generic (ContentTypes-based) audit model recording *who changed a status field and
when*, independent of which model owns that status. Not automatic — a view opts in by
calling `StatusChangeLog.log(instance, changed_by=request.user, old_status=..., new_status=...)`.
Currently wired into site status updates and payment creation only; most status
transitions (Expense, MaterialRequest, Invoice, Avenant, ...) are *not* logged here —
their history is only implicit in `updated_at`/`updated_by`.

### `Notification` (`core/models.py`)

```
recipient (FK User) · message · url · is_read · created_at
```

Deliberately plain: no generic FK back to the triggering object, just a ready-to-follow
`url` string. This keeps it a thin, read-only fan-out layer — like `core/approvals.py`
— rather than something every app's models have to import and wire into. Created
exclusively through the two helpers in `core/notifications.py`:

- `notify_role_holders(cabinet, roles, message, url, exclude_user=None)` — "something
  needs your decision", fanned out to every `UserCabinetRole` holder of `roles` in that
  `cabinet`.
- `notify_user(user, message, url)` — "your request was decided", sent back to the
  original submitter.

Both are silent no-ops on bad input (`cabinet=None`, no matching users, `user=None`)
rather than raising — a notification is a side effect that should never block the
request that triggered it.

## RBAC primitives (`core/mixins.py`)

Not a model, but the piece every other app's views depend on for Cabinet isolation —
see [`docs/security.md`](../security.md) for the full write-up. Four building blocks:

| Name | Shape | Used by |
|---|---|---|
| `CabinetAccessMixin` | class-based view mixin | Filters `get_queryset()` to the user's Cabinet(s) via `cabinet_lookup_field` (direct `'cabinet'` or chained, e.g. `'site__cabinet'`, `'contract__site__cabinet'`). Also resolves `get_user_cabinet()` (which Cabinet to tag a new record with) and `get_ambiguous_cabinet_choices()` (for a multi-cabinet user who hasn't picked one). |
| `RoleRequiredMixin` | class-based view mixin | Gates a whole view to `allowed_roles`, optionally scoped to one Cabinet via `get_role_cabinet()`. |
| `can_act_for_cabinet(request, cabinet, allowed_roles)` | function | The function-based-view equivalent of `RoleRequiredMixin`, for a single mutating action (approve/reject/send/...). |
| `can_view_cabinet(request, cabinet)` | function | Looser sibling: true for *any* role in that Cabinet (or superuser) — for shared, non-role-gated actions like commenting. |

`get_session_cabinet(request)` underlies all four: resolves the session's
`active_cabinet_id` (set by `accounts:switch_cabinet`) into a `Cabinet`, re-validating a
non-superuser's selection against their own `UserCabinetRole` rows every time (a stale
or revoked selection is dropped silently rather than trusted).

A superuser passes every one of these checks unless they've switched their session into
a *specific* Cabinet — then they're held to that one Cabinet only, same as a regular
user, so a superuser "viewing as" Cabinet A can't silently act on Cabinet B.

`PageHeaderMixin` (also in `core/mixins.py`) is unrelated to RBAC — just a
`get_context_data()` convenience for the page-header component (title, breadcrumbs,
back link, header actions) used across most admin/management views.

`add_ambiguous_cabinet_field(view, form)` is a small form helper for a `CreateView`
using `CabinetAccessMixin`: when `get_ambiguous_cabinet_choices()` returns something, it
injects an explicit `cabinet` choice field scoped to the user's own cabinets.

## Dashboard aggregation (`core/dashboard.py`)

`build_dashboard_context(request)` builds the entire "Tableau de Bord" context in one
function, kept out of `core/views.py`'s `HomeView` so it stays unit-testable and reusable
(e.g. from a future API endpoint). Everything is scoped via `scoped_cabinet_ids(request)`
— `None` means "no restriction" (superuser, no active cabinet switched in), otherwise a
concrete list of cabinet ids, possibly empty for a user with no role anywhere.

Produces:

- **Hero KPIs** — revenue/expense this month vs. last (with `%` trend), net margin,
  site counts by status.
- **Secondary chips** — devis pipeline value/count, win-rate, overdue invoices,
  overdue tasks, low-stock count, pending-expense count/amount.
- **6-month cashflow trend**, **devis/task/personnel-type donut charts** (colors pulled
  from `chantiermobile.constants.StatusBadgeClasses`, mapped to the Falcon theme's hex
  palette via `COLOR_HEX`/`_badge_hex` so chart colors match badge colors elsewhere).
- **Budget usage by active site** (top 6) and **total expenses per site** (top 8, all
  sites, not just budgeted ones).
- **A merged recent-activity feed** across devis, invoices, purchase orders, tasks and
  expenses, interleaved and sorted by `updated_at`.

`can_view_financials(request)` is the RBAC gate for the money widgets: `FINANCIAL_ROLES`
(`DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `ACCOUNTANT`, `CASHIER`) plus
superusers see them; `CHIEF_ENGINEER`, `ENGINEER` and `WORKER` get the same operational
widgets (sites, tasks, stock, personnel) without financial figures. Kept as its own
testable function rather than a template-only check, so the rule can be asserted
without rendering HTML.

## Pending-approvals inbox (`core/approvals.py`)

`get_pending_approvals(request)` aggregates every item the current user can currently
act on — Expense, MaterialRequest, Avenant, PlanningSubmission, Leave — into one
oldest-first list, instead of a director checking five separate list pages by hand.

**Deliberately duplicated role lists.** This module hardcodes its own copy of each
action's role list (`EXPENSE_APPROVAL_ROLES`, `MATERIAL_REQUEST_VALIDATE_ROLES`,
`PLANNING_REVIEW_ROLES`, `LEAVE_DECIDE_ROLES`, plus the shared
`FINAL_AUTHORIZATION_ROLES` from `chantiermobile.constants`) rather than importing each
app's view module to read its `allowed_roles` off it. This is intentional — pulling
every app's views into one shared aggregator would create a web of cross-app imports —
but it means **the two copies must be kept in sync by hand**: if an app's action view
changes who can approve something, `core/approvals.py` needs a matching update, or the
inbox will show (or hide) an item the viewer can't (or can) actually act on. Each list
carries a comment pointing at the view it mirrors.

Being read-only, it must never show an item the viewer couldn't actually act on if they
clicked through — that's the one invariant that matters more than completeness here.

## Global search (`core/search.py`)

`global_search(request, query)` — the navbar's search box, querying Sites, Personnel,
Contracts and Invoices by name/number. Cabinet-scoped the same way as every other
queryset; mirrors each entity's own list view's permission model (cabinet membership
only, no role restriction), so results never show more than the matching list page
already would. Returns `[]` for a query shorter than `MIN_QUERY_LENGTH` (2 chars) rather
than scanning the whole table.

## Middleware (`core/middleware.py`)

| Middleware | Purpose |
|---|---|
| `SessionIdleTimeoutMiddleware` | Logs an authenticated user out after `SESSION_IDLE_TIMEOUT_SECONDS` (15 min) of inactivity, with an explicit "votre session a expiré" message, rather than a silent drop into an anonymous session. Stamps `last_activity` in the session, throttled to one write per `SESSION_IDLE_TOUCH_INTERVAL_SECONDS` (60s) to avoid a session-table write on every request. See [`docs/security.md`](../security.md) and [ADR 0004](../architecture/decisions/0004-session-idle-timeout.md). |
| `ForcePasswordChangeMiddleware` | Redirects a user with `must_change_password=True` to the change-password page on every request until they change it — used for accounts created with a shared temporary password (`accounts.management.commands.bootstrap_admin_and_roles`, and the superadmin user-create/reset-password views). |

Both exempt static/media/i18n paths and the login/logout (or change-password) views
themselves, so the very page the user needs to reach is never the thing that gets
blocked.

## Views & permissions (`core/views.py`)

| View | URL name | Access |
|---|---|---|
| `HomeView` | `home` | Any authenticated user — `LoginRequiredMixin` only; financial content is hidden by `can_view_financials`, not by blocking the view. |
| `PendingApprovalsView` | `pending_approvals` | Any authenticated user — the list itself is already filtered to what they can act on by `get_pending_approvals`. |
| `GlobalSearchView` | `global_search` | Any authenticated user — results pre-filtered to their Cabinet(s). |
| `NotificationListView` | `notifications_list` | Any authenticated user, their own notifications only. |
| `notification_open` | `notification_open` | Any authenticated user; marks read and redirects to the notification's `url`, scoped to `request.user.notifications`. |
| `notifications_mark_all_read` | `notifications_mark_all_read` | Any authenticated user, POST-only, bulk-updates their own unread notifications. |

None of these use `allowed_roles` / `can_act_for_cabinet` — they're read-only or
self-scoped (a user can only mark their own notifications read), so `@login_required` /
`LoginRequiredMixin` is sufficient; the Cabinet- and role-scoping happens inside the
aggregator functions they call, not at the view layer.

## Business rules & gotchas

- **No hard delete, anywhere, by convention.** `SoftDeleteModel.delete()` always sets
  `is_deleted=True`; nothing in the app issues a real SQL DELETE on a `BaseModel`
  subclass. A query that forgets this (e.g. a raw `Model.all_objects.filter(...).delete()`)
  would be the one way to actually destroy data — avoid it.
- **`created_by`/`updated_by` are not automatic.** `AuditableModel` only declares the
  fields; nothing in `BaseModel.save()` populates them from the current request. Each
  view that creates/updates a record is responsible for setting them (typically in
  `form_valid()`). A silently-`None` audit field usually means a call site forgot this.
- **`StatusChangeLog` is opt-in and sparse.** Only site updates and payment creation
  call `StatusChangeLog.log()` today. Don't assume every status transition in the system
  is logged here — check the owning app's view/model before relying on it for an audit
  trail.
- **The pending-approvals role lists are a second source of truth.** See the
  "Deliberately duplicated role lists" note above — this is the single most likely
  place for a silent permission drift bug after a role-list change elsewhere.
- **`can_act_for_cabinet`/`can_view_cabinet` do not check `UserCabinetRole.status`.**
  Both query `UserCabinetRole.objects.filter(user=..., cabinet=..., role__in=...)`
  without filtering on `status`, so a `PENDING` (not yet approved) role assignment
  already grants access. See `docs/modules/accounts.md` for why this matters.
- **Dashboard financial figures are computed unconditionally.** `build_dashboard_context`
  always calculates revenue/expense/margin; `can_view_financials` only controls whether
  the *template* renders them. A new consumer of this context (an API endpoint, a PDF
  export) must re-check `can_view_financials` itself rather than assuming the data was
  withheld.
- **`active_cabinet_context` (a context processor, not in this doc's Views section but
  worth knowing) is superuser-only on purpose** — extending it to also resolve a regular
  multi-cabinet user's cabinets on every page load was tried and reverted for query-count
  cost; that disambiguation instead happens locally on the specific creation forms that
  need it (`get_ambiguous_cabinet_choices`).
