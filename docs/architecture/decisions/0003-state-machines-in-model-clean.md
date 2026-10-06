# 0003 — Status transitions validated in `model.clean()`, not just in views

**Status**: Accepted

## Context

Nearly every business object in this system has a status lifecycle (expense approval,
invoice lifecycle, material-request approval, site lifecycle, payroll disbursement, and
more — see `docs/architecture/overview.md` for the full list). Early in the project,
some of these transitions were only checked in the view that exposed the corresponding
button, which meant the same guarantee had to be re-implemented (or was silently
missing) anywhere else that could write to the model — a management command, the Django
admin, a shell session, or a future view nobody thought to cross-check.

## Decision

Validate every status transition inside the model's own `clean()` method, and call
`full_clean()` on every write path (not only `ModelForm.is_valid()`, which already calls
it, but also direct `.save()` calls in business-logic methods like `approve()`/
`reject()`/`disburse()`). The model is the single place a transition can be declared
legal or illegal; views, forms, and management commands all go through it.

## Consequences

- Adding a new status or transition means updating the model's `clean()`, not just
  wiring a new button — this is called out explicitly in `CONTRIBUTING.md`.
- Business-logic methods (`Expense.approve()`, `PurchaseOrder.receive()`,
  `PayrollList.disburse()`, etc.) still exist as the ergonomic, intention-revealing API
  views call — but they're a convenience layer over the validated `.save()`, not a
  replacement for the `clean()` guard.
- A bug where an invalid transition slips through is treated as a `clean()` gap, not
  "the view forgot to check" — the fix belongs on the model.
- This does cost an extra `full_clean()` (and its queries, where validation needs to
  look up related data) on every write; so far this hasn't shown up as a measurable
  problem, and correctness has been prioritized over shaving it off.
