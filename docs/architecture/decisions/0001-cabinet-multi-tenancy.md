# 0001 — Cabinet as the multi-tenancy boundary

**Status**: Accepted

## Context

ChantierMobile serves multiple construction firms (and potentially multiple branches of
one firm). Their data — sites, budgets, personnel, contracts — must never be visible or
writable across firms, while still running as one shared application and database
rather than one deployment per customer.

## Decision

Introduce a `Cabinet` model as the single tenancy boundary. Every business model either
has a direct FK to `Cabinet`, or reaches it indirectly through a chain of FKs (e.g.
`Expense.site.cabinet`, `Invoice.contract.site.cabinet`). Access is granted per-user via
`UserCabinetRole(user, cabinet, role)` rather than a single global role — the same user
can be a `DIRECTOR` in one Cabinet and have no access at all to another.

Two reusable building blocks enforce this everywhere instead of once per view:
`CabinetAccessMixin` (queryset scoping) and `RoleRequiredMixin` / `can_act_for_cabinet`
(role scoping within a Cabinet). See `docs/architecture/overview.md`.

A superuser can "switch into" a specific Cabinet for a session (logged via
`CabinetContextLog`) to administer it without needing a `UserCabinetRole` row of their
own.

## Consequences

- Any new model that holds tenant data must declare its path to `Cabinet` and use
  `CabinetAccessMixin` — there is no automatic enforcement if a view author forgets to
  set `cabinet_lookup_field` or mix the class in at all. This is the single most
  important thing to check in code review for a new view (see `CONTRIBUTING.md`).
- A function-based view must call `can_act_for_cabinet`/`can_view_cabinet` explicitly;
  there is no middleware-level enforcement (this was deliberate — scoping lives at the
  exact point data is read/written, not as a blanket request filter, since the same
  request can legitimately touch more than one Cabinet's read-only context, e.g. a
  superuser's cross-cabinet dashboard).
- Shared constants/reference data (e.g. `chantiermobile.constants`) intentionally live
  outside the Cabinet boundary — they're process-wide vocabulary (role names, status
  choices), not tenant data.
