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
- [Deployment](#deployment)
  - [Render.com (free)](#rendercom-free)
  - [Bare Linux Server](#bare-linux-server)
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

## Deployment

### Render.com (free)

Render hosts the full stack for free using the included `render.yaml` blueprint. Free tier limitations: the web service sleeps after 15 minutes of inactivity (~30 s cold start), and the PostgreSQL instance expires after 90 days (migrate to Supabase before then — see note below).

#### Prerequisites

- A free [Render account](https://render.com)
- A free [Upstash account](https://upstash.com) for Redis (10 K commands/day, no expiry)

#### 1. Create a free Redis database on Upstash

1. Log in to Upstash → **Create Database**
2. Choose the region closest to your users
3. Copy the **Redis URL** — it starts with `rediss://`

#### 2. Deploy via Blueprint

1. In the Render dashboard click **New → Blueprint**
2. Connect your GitHub repo (`monsieurpapa/chantierMobile`)
3. Render reads `render.yaml` and proposes three resources:
   - `chantiermobile-web` — Django web service
   - `chantiermobile-celery` — Celery worker + beat scheduler
   - `chantiermobile-db` — managed PostgreSQL (free, 90 days)
4. Before clicking **Apply**, set the `REDIS_URL` environment variable on **both services** to the Upstash URL copied above
5. Click **Apply** — Render runs `build.sh` (install → collectstatic → migrate) and starts the services

#### 3. Create a superuser

Once the deploy is green, open the **Shell** tab on `chantiermobile-web` and run:

```bash
python manage.py createsuperuser
```

#### 4. Access the app

Your live URL will be: `https://chantiermobile-web.onrender.com`

Log in, create a Cabinet, and assign yourself a role to unlock the full interface.

#### PostgreSQL expiry (90-day migration to Supabase)

Render's free PostgreSQL is deleted after 90 days. Before that deadline:

1. Dump from Render: in the Render shell run `pg_dump $DATABASE_URL > backup.sql`
2. Create a free project on [Supabase](https://supabase.com) — permanent free tier, 500 MB
3. Copy the Supabase connection string (PostgreSQL format, not Supabase JS)
4. Restore: `psql <supabase-connection-string> < backup.sql`
5. In the Render dashboard update `DATABASE_URL` on both services to the Supabase URL
6. Redeploy — zero downtime

---

### Bare Linux Server

For full control on a VPS (Ubuntu 22.04 LTS recommended — available free on [Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) or from ~$4/month on Hetzner/DigitalOcean).

The stack uses **Gunicorn** behind **Nginx**, **Supervisor** to keep Celery running, and **Certbot** for HTTPS.

#### 1. Provision the server

```bash
# On your local machine
ssh root@YOUR_SERVER_IP
```

```bash
# On the server — install system dependencies
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv python3-pip \
               postgresql postgresql-contrib \
               redis-server nginx supervisor certbot python3-certbot-nginx \
               git
```

#### 2. Create a database and user

```bash
sudo -u postgres psql <<SQL
CREATE DATABASE chantiermobile;
CREATE USER chantiermobile WITH PASSWORD 'choose-a-strong-password';
ALTER ROLE chantiermobile SET client_encoding TO 'utf8';
ALTER ROLE chantiermobile SET default_transaction_isolation TO 'read committed';
ALTER ROLE chantiermobile SET timezone TO 'Africa/Kigali';
GRANT ALL PRIVILEGES ON DATABASE chantiermobile TO chantiermobile;
SQL
```

#### 3. Clone the repo and install dependencies

```bash
git clone https://github.com/monsieurpapa/chantierMobile.git /srv/chantiermobile
cd /srv/chantiermobile

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 4. Configure environment variables

```bash
cp .env /srv/chantiermobile/.env.prod
nano /srv/chantiermobile/.env.prod
```

Minimum production `.env.prod`:

```env
SECRET_KEY=replace-with-a-long-random-string
DEBUG=0
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://chantiermobile:choose-a-strong-password@localhost:5432/chantiermobile
REDIS_URL=redis://localhost:6379/0
```

#### 5. Build the app

```bash
cd /srv/chantiermobile
source venv/bin/activate
export $(cat .env.prod | xargs)

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createsuperuser
```

#### 6. Configure Gunicorn via Supervisor

Create `/etc/supervisor/conf.d/chantiermobile.conf`:

```ini
[program:chantiermobile-web]
command=/srv/chantiermobile/venv/bin/gunicorn chantiermobile.wsgi:application
        --bind unix:/run/chantiermobile.sock
        --workers 3
        --timeout 120
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s",
            ALLOWED_HOSTS="%(ENV_ALLOWED_HOSTS)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/web.err.log
stdout_logfile=/var/log/chantiermobile/web.out.log

[program:chantiermobile-celery-worker]
command=/srv/chantiermobile/venv/bin/celery -A chantiermobile worker --loglevel=info
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/celery-worker.err.log
stdout_logfile=/var/log/chantiermobile/celery-worker.out.log

[program:chantiermobile-celery-beat]
command=/srv/chantiermobile/venv/bin/celery -A chantiermobile beat --loglevel=info
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/celery-beat.err.log
stdout_logfile=/var/log/chantiermobile/celery-beat.out.log
```

```bash
mkdir -p /var/log/chantiermobile
chown www-data:www-data /var/log/chantiermobile
# Load env vars for supervisor (add to /etc/supervisor/supervisord.conf or use a wrapper)
supervisorctl reread && supervisorctl update
supervisorctl start all
```

#### 7. Configure Nginx

Create `/etc/nginx/sites-available/chantiermobile`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /srv/chantiermobile/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://unix:/run/chantiermobile.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/chantiermobile /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

#### 8. Enable HTTPS with Certbot

```bash
certbot --nginx -d yourdomain.com -d www.yourdomain.com
# Certbot edits the Nginx config and sets up auto-renewal
```

#### 9. Deploying updates

```bash
cd /srv/chantiermobile
git pull origin main
source venv/bin/activate
export $(cat .env.prod | xargs)
pip install -r requirements.txt
python manage.py migrate --no-input
python manage.py collectstatic --no-input
supervisorctl restart chantiermobile-web chantiermobile-celery-worker chantiermobile-celery-beat
```

#### Supervisor quick-reference

```bash
supervisorctl status                        # Show all process states
supervisorctl restart chantiermobile-web    # Restart web only
supervisorctl tail -f chantiermobile-web    # Live logs
```

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
