# 0002 — Soft delete and audit fields via a shared BaseModel

**Status**: Accepted

## Context

This is a financial and HR system — budgets, payroll, invoices, personnel records.
Losing a row to an accidental (or malicious) hard delete is a materially worse failure
mode here than in most apps: it can hide money, obscure an audit trail, or corrupt a
report that a director or client relies on. At the same time, every app needs the same
handful of fields (timestamps, who created/last touched a row, a stable public
identifier) and re-deriving them per model invites drift.

## Decision

Give every business model a single abstract `BaseModel` (`core/models.py`), composed
from:

- `SoftDeleteModel` — `delete()` sets `is_deleted=True` / `deleted_at=now()` instead of
  removing the row; `Model.objects` (default manager) excludes soft-deleted rows,
  `Model.all_objects` includes them.
- `AuditableModel` (extends `TimeStampedModel`) — `created_by`/`updated_by` FKs and
  `created_at`/`updated_at` timestamps.
- A `unique_id` UUID field for any context needing a non-sequential public identifier.

A separate, generic `StatusChangeLog` model (via Django's ContentTypes framework) layers
on top for recording *status transitions* specifically — who changed a record's status
and when — independent of the general audit fields.

## Consequences

- There is no in-application hard-delete path for business data. Permanently removing a
  record (e.g. for a data-protection request) requires a direct database operation
  outside the app, done deliberately.
- Every query that should exclude deleted rows must go through `Model.objects` (the
  default) — code that bypasses the default manager (raw SQL, `Model.all_objects`
  without an explicit reason) needs a comment explaining why deleted rows are wanted.
- `StatusChangeLog` is opt-in per write path (it's called explicitly, not hooked via a
  signal), so it only covers the call sites that invoke it today (site updates, payment
  creation) — extending audit coverage to another transition means adding the call at
  that transition's write path, not assuming it's automatic.
