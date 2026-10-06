# ChantierMobile Documentation

Start at the root [`README.md`](../README.md) for the quick-start. This directory holds
the deeper reference material.

## Architecture

- [Overview](architecture/overview.md) — multi-tenancy, RBAC, base models, status state
  machines, module map, async tasks
- [Data model](architecture/data-model.md) — entity-relationship diagram and
  cross-app relationships
- [Decisions](architecture/decisions/) — architecture decision records (ADRs) for the
  choices that aren't obvious from reading the code alone

## Guides

- [Getting started](guides/getting-started.md) — local development setup
- [Deployment](guides/deployment.md) — Render.com, bare Linux server, Railway
- [Testing](guides/testing.md) — running and writing tests

## Security

- [Security model](security.md) — authentication, authorization, session policy,
  tenant isolation, audit trail

## Module reference

One page per Django app, covering its models, state machines, and key business rules:

- [`accounts`](modules/accounts.md) — users, Cabinets, roles
- [`core`](modules/core.md) — shared base models, RBAC mixins, dashboard, notifications,
  search, approvals inbox, session middleware
- [`projects`](modules/projects.md) — sites, phases, planning, progress reports
- [`personnel`](modules/personnel.md) — workers/staff, assignments, leave, attendance
- [`finance`](modules/finance.md) — budgets, expenses, caisse ledger, payroll, avenants
- [`materials`](modules/materials.md) — material catalog and request workflow
- [`revenue`](modules/revenue.md) — contracts, devis, situations, invoices, payments
- [`pricing`](modules/pricing.md) — price library, DQE (devis quantitatif estimatif)
- [`procurement`](modules/procurement.md) — suppliers, purchase orders, stock
- [`tasks`](modules/tasks.md) — task tracking

## Design proposals

[`docs/designs/`](designs/) holds forward-looking design docs for features not yet (or
only partly) implemented — e.g. [phase-scoped budget & stock alerts](designs/phase-budget-stock-alerts.md).
Unlike `docs/modules/`, these describe a proposed future state, not the current one.

## Historical documents

[`docs/history/`](history/) preserves point-in-time implementation write-ups from
earlier in the project, superseded by the documents above and by
[`CHANGELOG.md`](../CHANGELOG.md), but kept for reference.
