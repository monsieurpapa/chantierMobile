# Architecture Overview

ChantierMobile is a server-rendered Django application (no separate REST/SPA layer) built
around one core idea: a construction firm (**Cabinet**) runs one or more **Sites**
(chantiers), and every other app in the system — finance, personnel, materials, revenue,
pricing, procurement, tasks — hangs business data off a Site or a Cabinet.

## Module map

| App | Owns |
|---|---|
| `accounts` | `User`, `Cabinet`, `UserCabinetRole` (who has which role in which cabinet), `CabinetContextLog` |
| `core` | Shared base models (`BaseModel`, `StatusChangeLog`, `Notification`), RBAC mixins (`CabinetAccessMixin`, `RoleRequiredMixin`), the dashboard aggregator, the pending-approvals inbox, global search, notifications, and the session-idle-timeout middleware |
| `projects` | `Site`, `ProjectPhase`, `PlanningSubmission`, `SiteProgress` + photos/comments |
| `personnel` | `Personnel`, `Skill`, `SiteAssignment`, `Leave`, `Holiday`, `Attendance`, `PersonnelDocument` |
| `finance` | `Budget`, `Expense` (+ `ExpenseCategory`, `ExpenseApproval`), `Caisse` ledger (+ transactions, loans), `PayrollList`/`PayrollListItem` (ouvriers), `SalaryPaymentList`/`SalaryPaymentItem` (ingénieurs/staff), `Avenant` |
| `materials` | `Material`, `MaterialRequest`/`MaterialRequestItem` |
| `revenue` | `Contract`, `Devis`/`DevisLine`, `SituationTravaux`/`SituationLine`, `Invoice`, `Payment` |
| `pricing` | `PriceLibraryItem` (Bibliothèque de Prix), `DQE`/`DQELine` (Détail Quantitatif Estimatif) |
| `procurement` | `Supplier`, `SupplierCredit`/`SupplierCreditPayment`, `StockItem`, `PurchaseOrder`/`PurchaseOrderLine`, `StockMovement` |
| `tasks` | `Task` |

See [the data model](data-model.md) for how these connect, and `docs/modules/<app>.md`
for a detailed walkthrough of each one.

## Multi-tenancy: Cabinet

Every business entity ultimately belongs to a **Cabinet** — an isolated organizational
unit (one construction firm, or one branch of one). A user's access to a Cabinet is
granted by a `UserCabinetRole` row (`user`, `cabinet`, `role`); a user can hold different
roles in different Cabinets, and most views scope every queryset to the Cabinets the
current user has a role in.

Two mixins in `core/mixins.py` carry almost all of this weight:

- **`CabinetAccessMixin`** — filters a class-based view's queryset down to the current
  user's Cabinet(s). Set `cabinet_lookup_field` to the ORM path from the model to its
  owning Cabinet: `'cabinet'` for a direct FK (`Site`, `Personnel`, `Budget`), or an
  indirect path like `'site__cabinet'` (`Expense`, `MaterialRequest`) or
  `'contract__site__cabinet'` (`Invoice`) when the model hangs off a Site instead.
  Also resolves `get_user_cabinet()` — which Cabinet a newly-created object should be
  tagged with — and `get_ambiguous_cabinet_choices()` for the rare case a multi-cabinet
  user needs to disambiguate explicitly on a creation form.
- **`RoleRequiredMixin`** — gates an entire view to specific roles (`allowed_roles = [...]`
  class attribute), scoped by default across all of the user's Cabinets, or to one
  specific Cabinet via `get_role_cabinet()` so a DIRECTOR in Cabinet A can't act on
  Cabinet B.

Function-based views (most approve/reject/send/validate endpoints) use the equivalent
helpers directly: `can_act_for_cabinet(request, cabinet, allowed_roles)` for a
role-gated mutation and the looser `can_view_cabinet(request, cabinet)` for shared,
non-role-gated actions (e.g. commenting on a progress report). **Every state-changing
view must call one of these** — `@login_required` alone only proves the user is signed
in, not that they hold the right role in the right Cabinet.

A **superuser** can additionally "switch into" a specific Cabinet for the session
(`accounts:switch_cabinet`, logged via `CabinetContextLog`) to browse/administer it as
if they were a member — the navbar shows an amber "viewing as" banner while a
Cabinet is active. Without an active selection, a superuser sees everything across
every Cabinet.

## Roles

Defined in `chantiermobile.constants.UserRoles` — the single source of truth for role
names across the whole codebase (never hardcode a role string):

| Role | French label | Typical scope |
|---|---|---|
| `DIRECTOR` | Directeur de Cabinet | Full authority within a single-cabinet setup |
| `DIRECTEUR_TECHNIQUE` | Directeur Technique | Final authorization tier (larger cabinets) |
| `DIRECTEUR_GENERAL` | Directeur Général | Final authorization tier (larger cabinets) |
| `CHIEF_ENGINEER` | Chef des Ingénieurs | Oversight across sites |
| `ENGINEER` | Ingénieur | Own-site planning, budget visibility, crew/leave |
| `FINANCIER` | Financier | Wire transfers, supplier credit |
| `ACCOUNTANT` | Comptable | Expense/payment bookkeeping |
| `CASHIER` | Caissier | Caisse (cash register) operations |
| `MAGASINIER` | Magasinier | Materials/stock validation |
| `WORKER` | Ouvrier | Field worker — minimal access |

`chantiermobile.constants.DIRECTOR_ROLES` groups the three director-tier roles for
anywhere that needs to recognize "a director" generically (budgets, sites, contracts,
invoices, caisse, payroll, dashboard financial widgets). `FINAL_AUTHORIZATION_ROLES` is
the same three, named for its specific use as the second/final approval step on a
material request or avenant. See [`docs/security.md`](../security.md) for the full
permission picture.

## Base models (`core/models.py`)

Every business model inherits `BaseModel`, composed from three abstract mixins:

- **`SoftDeleteModel`** — `delete()` sets `is_deleted=True` and stamps `deleted_at`
  rather than removing the row. `Model.objects` (the default manager) only returns
  non-deleted rows; `Model.all_objects` includes deleted ones. There is deliberately no
  hard-delete path through the application.
- **`AuditableModel`** (extends `TimeStampedModel`) — `created_by`/`updated_by` FKs to
  the user model, plus `created_at`/`updated_at` timestamps.
- A `unique_id` UUID field, for any context that needs a public-safe identifier instead
  of the auto-increment primary key.

`StatusChangeLog` is a separate, generic (ContentTypes-based) audit model for recording
*who changed a status and when* — `StatusChangeLog.log(instance, changed_by=..., old_status=...,
new_status=...)` — currently hooked into site updates and payment creation.

## Status state machines

Every status field in the system is validated in the model's own `clean()` method and
enforced via `full_clean()` on every write path — **not just from the one view that
happens to expose the transition today**. This is the load-bearing invariant for the
whole app's data integrity: a new view, a management command, or a shell session cannot
silently put a record into an invalid state, because the model itself refuses it.

```text
Expense:            PENDING → APPROVED → PAID        (terminal)
                            → REJECTED                (terminal)

MaterialRequest:     PENDING → VALIDATED (magasinier) → APPROVED (director-tier)
                             → ORDERED → DELIVERED     (terminal)
                             → REJECTED (from PENDING or VALIDATED) (terminal)

Invoice:             DRAFT → SENT → PAID              (terminal)
                                  → OVERDUE → PAID     (terminal)
                           → CANCELLED                 (terminal, from any non-terminal)

Site:                PLANNING → ACTIVE ↔ PAUSED → COMPLETED (terminal)
                              ↘ CANCELLED (from any non-terminal) (terminal)

PayrollList /
SalaryPaymentList:    BROUILLON → SOUMISE → PAYEE      (terminal)

Avenant:              PENDING → APPROVED               (terminal)
                              → REJECTED                (terminal)

Devis:                BROUILLON → ENVOYE → ACCEPTE      (terminal)
                                          → REFUSE       (terminal)
                                → EXPIRE                 (terminal)

SituationTravaux:      BROUILLON → VALIDEE → FACTUREE    (terminal)

PurchaseOrder:         BROUILLON → ENVOYEE → RECUE_PARTIELLE → RECUE (terminal)
                                           → RECUE (direct)   (terminal)
                                → ANNULEE                     (terminal)

PlanningSubmission:    BROUILLON → SOUMISE → APPROUVEE        (terminal)
                                            → REJETEE          (terminal)

ProjectPhase:          EN_COURS → CLOTUREE (closed by the site's lead engineer) (terminal)
```

`revenue.tasks.mark_overdue_invoices` (see [Async tasks](#async-tasks)) is the one
transition that happens automatically rather than from a user action: a daily Celery
beat job bulk-updates SENT invoices whose `due_date` has passed to OVERDUE.

Full field-by-field transition rules (who can trigger each one, in which role) live in
each model's `clean()` and the `approve`/`reject`/`submit`/`disburse`/`receive`/`transfer`
methods described in the per-app `docs/modules/*.md` pages.

## Async tasks (Celery)

- **Broker/result backend**: Redis, via `django_celery_results` + `django_celery_beat`
  (database-backed periodic task schedule, editable from the Django admin).
- **`revenue.tasks.mark_overdue_invoices`** — runs daily at 01:00 Africa/Kigali; bulk
  marks SENT invoices whose `due_date` has passed as OVERDUE.
- **Flower** (`:5555` in local dev) gives a live dashboard over the worker/beat queues.

## Cross-cutting features (`core` app)

Added during the Directors/Engineers feature audit (see `CHANGELOG.md`):

- **Pending approvals inbox** (`core/approvals.py`) — aggregates every item a user can
  currently act on (expenses, material requests, avenants, planning submissions, leave
  requests) into one list, mirroring the exact role/status check each action view
  already enforces. Read-only and deliberately duplicated rather than importing each
  app's view logic, so it never shows an item the viewer couldn't actually act on.
- **Dashboard** (`core/dashboard.py`) — cabinet-scoped aggregation (budgets, revenue,
  task counts, recent activity) kept out of the view itself so it can be unit-tested and
  reused independently of `HomeView`.
- **Notifications** (`core/notifications.py`, `core/models.Notification`) —
  `notify_role_holders()` / `notify_user()` helpers fire from approval/decision flows
  across finance, materials, projects, and personnel; surfaced via the navbar bell icon
  and `templates/core/notifications_list.html`.
- **Global search** (`core/search.py`) — a single search box in the navbar querying
  across sites, personnel, contracts, and invoices, permission-scoped the same way as
  every other Cabinet-aware queryset.
- **Session idle timeout** (`core/middleware.SessionIdleTimeoutMiddleware`) — see
  [`docs/security.md`](../security.md) for the full write-up.

## Internationalization

French is the default language, English the alternate; every user-facing string is
wrapped with `gettext_lazy`. See [`CONTRIBUTING.md`](../../CONTRIBUTING.md#translations)
for the translation workflow.

## Where to go next

- [`data-model.md`](data-model.md) for the full entity-relationship diagram
- [`decisions/`](decisions/) for the reasoning behind specific architectural choices
- [`../security.md`](../security.md) for the authorization/session model in detail
- [`../modules/`](../modules/) for an app-by-app deep dive
