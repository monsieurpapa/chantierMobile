# ChantierMobile

**Construction site ERP** — project tracking, personnel management, financial control, material logistics, pricing/estimation, procurement, and revenue handling in one platform.

[![Django](https://img.shields.io/badge/Django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Celery](https://img.shields.io/badge/Celery-Redis-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Development](#development)
- [Testing](#testing)
- [Architecture](#architecture)
- [Security](#security)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

ChantierMobile is a multi-tenant ERP built for construction firms. Each firm operates
under a **Cabinet** — an isolated organizational unit that owns all its sites, budgets,
contracts, and personnel data. Role-based access control (Director, Directeur
Technique/Général, Chief Engineer, Engineer, Financier, Accountant, Cashier,
Magasinier, Worker) is enforced at the view layer, scoped per Cabinet. See
[`docs/architecture/overview.md`](docs/architecture/overview.md) for the full model.

---

## Features

| Module | What it does |
|--------|-------------|
| **Projects** | Manage construction sites through a lifecycle (Planning → Active → Paused → Completed), broken into phases with progress tracking (photos, comments), lead-engineer assignment, and planning submission/review |
| **Finance** | Per-site budget caps, expense approval workflow (Pending → Approved → Paid), a balance-tracked Caisse ledger (cashbook, inter-caisse loans), progressive worker payroll and separate fixed-salary payroll for engineers/staff, avenants (change orders), PDF reports |
| **Personnel** | Worker/staff profiles, per-site assignments with negotiated rates, skill cataloguing, leave requests, daily attendance/pointage tracking |
| **Materials** | Material catalog, two-stage request/approval workflow (Pending → Validated → Approved → Ordered → Delivered) |
| **Revenue** | Devis (quotes) and Situations de travaux (progress billing), client contracts, invoice generation with status tracking (Draft → Sent → Paid/Overdue), payment reconciliation, PDF export |
| **Pricing** | Bibliothèque de Prix (price library) and DQE (Détail Quantitatif Estimatif) for project cost estimation |
| **Procurement** | Suppliers, purchase orders with two-stage approval, stock items and movements (in/out/transfer), supplier credit tracking |
| **Tasks** | Lightweight task tracking per site/phase, with priority and assignment |
| **Dashboard & search** | Real-time cabinet-scoped analytics, a unified pending-approvals inbox, and global search across sites, personnel, contracts, and invoices |
| **Notifications** | In-app, role-targeted notifications on approval events (bell icon) |
| **Security** | 15-minute session idle timeout, forced password change on first login, full RBAC + Cabinet isolation (see [`docs/security.md`](docs/security.md)) |
| **Async tasks** | Celery beat job marks overdue invoices daily; Flower dashboard for task monitoring |
| **i18n** | French (default) and English, switchable via UI; all strings use `gettext_lazy` |

---

## Tech Stack

- **Runtime**: Python 3.12 / Django 4.2+
- **Database**: PostgreSQL 15
- **Cache & broker**: Redis 7
- **Task queue**: Celery + django-celery-beat + django-celery-results
- **Auth**: django-allauth (username or email login)
- **Containerization**: Docker + Docker Compose
- **Task runner**: [just](https://github.com/casey/just)

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) running
- [just](https://github.com/casey/just#installation) installed

### 1. Clone and configure

```bash
git clone https://github.com/monsieurpapa/chantierMobile.git
cd chantierMobile
cp .env.example .env   # then edit with your values
```

Minimum `.env` for local development:

```env
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=1
ALLOWED_HOSTS=127.0.0.1,localhost
```

Database and Redis connection strings are already set for the Docker Compose network — you only need to override them for an external database.

### 2. Start services

```bash
just dev-up
```

This starts Django (`:8001`), PostgreSQL (`:5432`), Redis (`:6379`), Celery worker, Celery beat, and Flower (`:5555`).

### 3. Initialize the database

```bash
just migrate
just createsuperuser
```

### 4. Open the app

| Service | URL |
|---------|-----|
| Application | http://localhost:8001 |
| Celery monitor (Flower) | http://localhost:5555 |

Full walkthrough, including creating your first Cabinet and common first-run issues:
[`docs/guides/getting-started.md`](docs/guides/getting-started.md).

---

## Configuration

All configuration is driven by environment variables; the defaults in
`docker-compose.yml` work for local development out of the box. See
[`docs/guides/deployment.md`](docs/guides/deployment.md#environment-variables-reference)
for the full reference table and `.env.example` for the complete, current list.

---

## Deployment

Supported targets: **Render.com** (free tier), **Railway**, and a **bare Linux server**
(Gunicorn + Nginx + Supervisor + Certbot). Full step-by-step instructions for each,
including the Render free-tier 90-day PostgreSQL migration path, live in
[`docs/guides/deployment.md`](docs/guides/deployment.md).

---

## Development

All commands run inside Docker via `just`. Run `just` with no arguments to list everything.

```bash
# Services
just dev-up          # Start all services
just dev-down        # Stop all services
just dev-logs        # Tail Django logs
just status          # Show container status and URLs

# Django
just migrate         # Apply migrations
just makemigrations  # Create new migrations
just shell           # Django shell
just createsuperuser

# Code quality (runs inside container)
just format          # black
just sort-imports    # isort
just lint            # flake8
just quality         # all three together

# i18n
just i18n-extract    # makemessages (fr + en)
just i18n-compile    # compilemessages

# Database
just db-backup       # Dump to timestamped .sql file
just db-restore <file>
```

### First-time setup shortcut

```bash
just setup   # dev-up + migrate + createsuperuser
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for code style conventions, the branching
model, and the pull-request checklist.

---

## Testing

```bash
just test                              # All tests (≥80% coverage enforced)
just test-file tests/test_finance.py   # Single file
just test-app finance                  # Filter by keyword
just test-unit                         # @pytest.mark.unit only
just test-fast                         # Stop on first failure (-x)
just test-coverage                     # HTML report in htmlcov/
```

Fixture/factory conventions, markers, and how to write a regression test:
[`docs/guides/testing.md`](docs/guides/testing.md).

---

## Architecture

ChantierMobile centers on **Cabinet** (the multi-tenancy boundary) and **Site**
(a construction project), with every other module hanging business data off one or the
other. Every status field is validated in the owning model's `clean()` — not just from
one view — so a transition can't be bypassed from a management command or the admin.

Full write-up, module map, state-machine diagrams, and the entity-relationship diagram:
[`docs/architecture/overview.md`](docs/architecture/overview.md) and
[`docs/architecture/data-model.md`](docs/architecture/data-model.md). The reasoning
behind specific choices (Cabinet as tenancy boundary, soft delete, validating state in
`clean()`, the session idle timeout, separate payroll tracks) is recorded as
[architecture decision records](docs/architecture/decisions/).

---

## Security

Session policy, authentication, the full RBAC permission matrix, tenant isolation, and
audit trail are documented in [`docs/security.md`](docs/security.md). To report a
vulnerability, see [`SECURITY.md`](SECURITY.md).

---

## Documentation

- [`docs/README.md`](docs/README.md) — documentation index
- [`docs/architecture/`](docs/architecture/) — system design, data model, ADRs
- [`docs/guides/`](docs/guides/) — getting started, deployment, testing
- [`docs/security.md`](docs/security.md) — security model
- [`docs/modules/`](docs/modules/) — one reference page per Django app
- [`CHANGELOG.md`](CHANGELOG.md) — notable changes, newest first

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide (branching, commit style,
code style, testing requirements, PR checklist). Short version:

1. Create a branch: `git checkout -b feat/your-feature`
2. Run `just quality` before committing
3. Ensure `just test` passes with coverage ≥80%
4. Open a pull request against `main`

This project also follows a [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License

Proprietary — all rights reserved. See [`LICENSE`](LICENSE).
