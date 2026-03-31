# ChantierMobile

**Construction site ERP** — project tracking, personnel management, financial control, material logistics, and revenue handling in one platform.

[![Django](https://img.shields.io/badge/Django-4.2+-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Celery](https://img.shields.io/badge/Celery-Redis-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Development](#development)
- [Testing](#testing)
- [Architecture](#architecture)
- [Contributing](#contributing)

---

## Overview

ChantierMobile is a multi-tenant ERP built for construction firms. Each firm operates under a **Cabinet** — an isolated organizational unit that owns all its sites, budgets, contracts, and personnel data. Role-based access control (Director, Chief Engineer, Engineer, Accountant, Cashier, Worker) is enforced at the view layer.

---

## Features

| Module | What it does |
|--------|-------------|
| **Projects** | Manage construction sites through a lifecycle (Planning → Active → Paused → Completed), broken into phases with progress tracking |
| **Finance** | Per-site budget caps, expense submission with an approval workflow (Pending → Approved → Paid), receipt archiving |
| **Personnel** | Worker profiles, per-site assignments with negotiated daily rates, skill cataloguing |
| **Materials** | Material catalog, request/order workflow (Pending → Approved → Ordered → Delivered) |
| **Revenue** | Client contracts, invoice generation with status tracking (Draft → Sent → Paid/Overdue), payment reconciliation |
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

---

## Configuration

All configuration is driven by environment variables. The defaults in `docker-compose.yml` work for local development out of the box.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure dev key)* | Django secret key — **always override in production** |
| `DEBUG` | `0` | Set to `1` for development |
| `ALLOWED_HOSTS` | `` | Comma-separated list of allowed hostnames |
| `DB_ENGINE` | `django.db.backends.sqlite3` | Switch to `django.db.backends.postgresql` for Postgres |
| `DB_NAME` | `db.sqlite3` | Database name |
| `DB_USER` | `` | Database user |
| `DB_PASSWORD` | `` | Database password |
| `DB_HOST` | `` | Database host |
| `DB_PORT` | `` | Database port |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (used by Celery) |

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

---

## Testing

Tests live in `tests/` and run inside Docker. The suite requires Docker Desktop to be running.

```bash
just test                              # All tests (≥80% coverage enforced)
just test-file tests/test_finance.py   # Single file
just test-app finance                  # Filter by keyword
just test-unit                         # @pytest.mark.unit only
just test-fast                         # Stop on first failure (-x)
just test-debug                        # Drop into pdb on failure
just test-coverage                     # HTML report in htmlcov/
```

**Pytest configuration** (`setup.cfg`):
- `--reuse-db` — test database is preserved between runs; use `--create-db` after schema changes
- `--nomigrations` — uses direct schema creation for speed
- `--cov-fail-under=80` — build fails below 80% coverage

**Test markers**: `unit`, `integration`, `e2e`, `api`, `performance`, `finance`, `materials`, `personnel`, `projects`, `revenue`, `auth`, `i18n`

---

## Architecture

### Multi-tenancy: Cabinet

Every business entity belongs to a **Cabinet**. The two key mixins in `core/mixins.py`:

- `CabinetAccessMixin` — automatically filters querysets to the current user's cabinets
- `RoleRequiredMixin` — gates views to specific roles (set `allowed_roles` on the view class)

### Data relationships

```
Cabinet
  └── Site (projects)
        ├── Budget          (finance)   — OneToOne
        ├── Expense[]       (finance)   — FK
        ├── Assignment[]    (personnel) — FK
        ├── MaterialRequest[] (materials) — FK
        └── Contract        (revenue)  — OneToOne
              ├── Invoice[] — FK
              └── Payment[] — FK (via Invoice)
```

`Site` exposes computed properties (`total_spent`, `total_revenue`, `net_profit`, `budget_usage_percentage`) that aggregate across modules — not stored in the DB.

### Status machines

Transitions are validated in `model.clean()` and enforced via `full_clean()` in all write paths — server-side validation cannot be bypassed.

```
Expense:  PENDING → APPROVED → PAID       (terminal)
                  → REJECTED              (terminal)

Invoice:  DRAFT → SENT → PAID             (terminal)
                       → OVERDUE → PAID   (terminal)
               → CANCELLED               (terminal)

Site: PLANNING → ACTIVE ↔ PAUSED → COMPLETED  (terminal)
             ↘ CANCELLED (from any non-terminal) (terminal)

MaterialRequest: PENDING → APPROVED → ORDERED → DELIVERED (terminal)
                         → REJECTED                        (terminal)
```

### Base models (`core/models.py`)

All business models inherit from `BaseModel`, which provides:

- **Soft delete** — `delete()` sets `is_deleted=True`; use `Model.objects` for active records, `Model.all_objects` to include deleted
- **Audit trail** — `created_by` / `updated_by` FK to `AUTH_USER_MODEL`
- **Timestamps** — `created_at` / `updated_at`
- **UUID** — `unique_id` non-editable UUID field for public-safe identifiers

### Shared constants

`chantiermobile/constants.py` is the single source of truth for all `TextChoices` enums (`UserRoles`, `SiteStatus`, `ExpenseStatus`, `InvoiceStatus`, `PaymentMethod`, etc.). Import from there — never define inline string literals.

### Async tasks

`revenue/tasks.py` — `mark_overdue_invoices` runs daily at **01:00 Africa/Kigali** via Celery beat. It bulk-updates SENT invoices whose `due_date` has passed to OVERDUE.

---

## Contributing

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Run `just quality` before committing
3. Ensure `just test` passes with coverage ≥80%
4. Open a pull request against `main`

See `TODOS.md` for known deferred work and `CLAUDE.md` for guidance on working with this codebase using Claude Code.
