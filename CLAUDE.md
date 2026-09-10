# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run inside Docker. Use `just` as a task runner (or run the docker-compose equivalents directly).

```bash
# Start / stop services
just dev-up          # Start all services (Django on :8001, Redis on :6379, PostgreSQL on :5432)
just dev-down

# Django management
just migrate         # Apply migrations
just makemigrations  # Create new migrations
just shell           # Django shell

# Tests
just test                        # Run all tests
just test-file tests/test_unit.py  # Single file
just test-app finance            # Filter by app keyword
just test-unit                   # Only @pytest.mark.unit
just test-integration            # Only @pytest.mark.integration
just test-e2e                    # Only @pytest.mark.e2e
just test-fast                   # Stop on first failure (-x)
just test-debug                  # With pdb on failure
just test-coverage               # With HTML coverage report

# Code quality
just lint            # flake8
just format          # black
just sort-imports    # isort
just quality         # all three together

# Data management
just load-sample-data          # loaddata sample_data.json
# Or use management commands directly:
# python manage.py seed_sample_data
# python manage.py clear_sample_data
# python manage.py populate_materials

# i18n
just i18n-extract    # makemessages (fr + en)
just i18n-compile    # compilemessages
```

Pytest is configured in `pytest.ini`: uses `--reuse-db`, `--nomigrations`, enforces 80% coverage, and looks for tests in `tests/`.

## Architecture

### Multi-tenant: Cabinet

The central organizational unit is `Cabinet` (`accounts/models.py`). Every business entity (Site, Budget, Contract, etc.) belongs to a Cabinet. Access control is enforced in views via two mixins in `core/mixins.py`:

- **`CabinetAccessMixin`** — filters querysets to the current user's cabinets.
- **`RoleRequiredMixin`** — gates views to specific `UserRoles` (DIRECTOR, CHIEF_ENGINEER, ENGINEER, ACCOUNTANT, CASHIER, WORKER), all defined in `chantiermobile/constants.py`.

### Base models (`core/models.py`)

All business models inherit from `BaseModel`, which stacks:

1. **`SoftDeleteModel`** — `delete()` sets `is_deleted=True` instead of hard-deleting. Use `Model.objects` for active records, `Model.all_objects` to include deleted.
2. **`AuditableModel`** — `created_by` / `updated_by` FK to `AUTH_USER_MODEL`.
3. **`TimeStampedModel`** — `created_at` / `updated_at`.
4. A `unique_id` UUID field (non-editable).

### App structure

| App | Responsibility |
|-----|---------------|
| `accounts` | Custom `User` (extends `AbstractUser`), `Cabinet`, `UserCabinetRole` |
| `projects` | `Site` (construction site), `Phase` — core entity everything else links to |
| `finance` | `Budget` (OneToOne with Site), `ExpenseCategory`, `Expense` with approval workflow |
| `personnel` | Worker profiles, site assignments with daily rates |
| `materials` | Material definitions, request/order workflow |
| `revenue` | `Contract` (OneToOne with Site), `Invoice`, `Payment` |
| `core` | Abstract base models, `CabinetAccessMixin`, `RoleRequiredMixin`, `PageHeaderMixin`, context processors |

### Data flow / key relationships

```
Cabinet
  └── Site (projects)
        ├── Budget (finance) — OneToOne
        ├── Expense[] (finance) — FK
        ├── Assignment[] (personnel) — FK
        ├── MaterialRequest[] (materials) — FK
        └── Contract (revenue) — OneToOne
              ├── Invoice[] — FK
              └── Payment[] — FK (via Invoice)
```

`Site` has computed properties (`total_spent`, `total_revenue`, `net_profit`, `budget_usage_percentage`) that aggregate across the related apps — these are not stored in the DB.

### Status machines

All status transitions are validated in model `clean()` methods, not just in views:

- **Site**: PLANNING → ACTIVE/CANCELLED; ACTIVE → PAUSED/COMPLETED/CANCELLED; PAUSED → ACTIVE/COMPLETED/CANCELLED. COMPLETED and CANCELLED are terminal.
- **Expense**: PENDING → APPROVED/REJECTED; APPROVED → PAID/REJECTED. REJECTED and PAID are terminal.
- **MaterialRequest**: PENDING → APPROVED/REJECTED → ORDERED → DELIVERED.
- **Invoice**: DRAFT → SENT → PAID/OVERDUE.

### Internationalization

Default language is French (`fr`). English (`en`) is also supported. Translation files live in `locale/`. The `LocaleMiddleware` is active. All user-facing strings must use `gettext_lazy as _`. After editing `.po` files, run `just i18n-compile`. The `compile_translations.py` script in the root is a helper for this.

### Shared constants

`chantiermobile/constants.py` is the single source of truth for all `TextChoices` enums (`UserRoles`, `SiteStatus`, `ExpenseStatus`, `InvoiceStatus`, `PaymentMethod`, etc.). Always import from there rather than defining inline string literals.

### View composition

All views follow this mixin stack (order matters for MRO):

```python
class MyView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, RoleRequiredMixin, ListView):
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = "..."
    header_subtitle = "..."
    back_url = reverse_lazy('app:list')
```

- `CabinetAccessMixin` — filters `get_queryset()` to the user's cabinets; use `get_user_cabinet()` on create views.
- `RoleRequiredMixin` — add `allowed_roles` class attribute; omit if any authenticated user should have access.
- `PageHeaderMixin` — injects `header_title`, `header_subtitle`, `breadcrumb_items`, `back_url`, `header_actions` into context.

For template-level role checks, use the `has_role` filter from `core/templatetags/rbac_tags.py`:

```html
{% load rbac_tags %}
{% if request.user|has_role:'DIRECTOR,CHIEF_ENGINEER' %}...{% endif %}
```

### Celery

Celery is configured in `chantiermobile/celery.py`. Workers and the beat scheduler run as separate Docker services.

- `django_celery_beat` — stores periodic task schedules in the DB (manageable via Django admin).
- `django_celery_results` — persists task results to the DB.
- `revenue/tasks.py` — `mark_overdue_invoices` runs daily at 01:00 Africa/Kigali to transition SENT → OVERDUE invoices.

New tasks go in `<app>/tasks.py` and use `@shared_task`. Periodic schedules are registered in Django admin under **Periodic Tasks**.

### Testing

- Tests live in `tests/` (flat, not per-app).
- `tests/conftest.py` provides shared pytest fixtures (users, cabinet, roles).
- `tests/factories.py` contains Factory Boy factories.
- Markers: `unit`, `integration`, `e2e`, `api`, `performance`, plus per-app markers (`finance`, `materials`, etc.).
- The `--reuse-db` flag means the test DB is preserved between runs; run with `--create-db` if schema changes are not picked up.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Growth/customer acquisition, GTM, launch strategy, marketing → invoke growth-playbook
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

## Deploy Configuration (configured by /setup-deploy)
- Platform: Railway
- Production URL: https://{your-service}.railway.app (set after first deploy)
- Deploy workflow: auto-deploy on push to main
- Deploy status command: HTTP health check
- Merge method: squash
- Project type: web app (Django + Celery)
- Post-deploy health check: https://{your-service}.railway.app/

### Custom deploy hooks
- Pre-merge: none
- Deploy trigger: automatic on push to main (Railway watches the connected branch)
- Deploy status: poll production URL
- Health check: https://{your-service}.railway.app/

### Railway services required (create in Railway dashboard)
1. **Web** — Dockerfile build, start command from `railway.toml`
2. **Celery worker** — same repo, start command: `celery -A chantiermobile worker --beat --loglevel=info --concurrency=1`

### Required env vars (set in Railway dashboard)
| Variable | Value |
|---|---|
| `SECRET_KEY` | generate a strong random string |
| `DEBUG` | `False` |
| `DATABASE_URL` | PostgreSQL connection string (Railway PostgreSQL plugin or Supabase) |
| `REDIS_URL` | Redis URL (Railway Redis plugin or Upstash) |
| `ALLOWED_HOSTS` | comma-separated hostnames (Railway sets `RAILWAY_PUBLIC_DOMAIN` automatically) |
| `CLOUDFARE_R2_TOKEN_NAME` | R2 Access Key ID (for media uploads) |
| `CLOUDFARE_API_TOKEN` | R2 Secret Access Key |
| `CLOUDFARE_R2_BUCKET_NAME` | R2 bucket name |
| `CLOUDFARE_R2_BUCKET_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `EMAIL_HOST_USER` | SMTP user (optional) |
| `EMAIL_HOST_PASSWORD` | SMTP password (optional) |

## Secondary Deploy Target: Google Cloud

Added alongside Railway (Railway stays primary/auto-deploy; GCP is deployed manually via the script below). Scripts live in `deploy/gcp/`.

- **Platform:** Cloud Run (web) + Compute Engine e2-micro VM (Celery worker + beat)
- **Database:** Cloud SQL for PostgreSQL (`db-f1-micro`), connected via the built-in Cloud Run ↔ Cloud SQL unix-socket integration (no VPC connector needed)
- **Redis broker:** Upstash (external, free tier) — chosen over Memorystore because Memorystore requires a Serverless VPC Access connector (~$8-10/mo extra) just to reach it from Cloud Run/Compute Engine, which isn't worth it for a Celery broker at this scale
- **Media storage:** same Cloudflare R2 bucket/credentials as Railway (reuse, don't duplicate)
- **Static files:** Whitenoise, baked into the container at `collectstatic` time — no GCS bucket needed

### Deploying

```bash
export PROJECT_ID=your-gcp-project-id
export SQL_DB_PASSWORD=...        # new strong password for the Cloud SQL user
export SECRET_KEY=...             # generate a strong random string (different from Railway's)
export REDIS_URL=rediss://...     # Upstash connection string
export CLOUDFARE_R2_TOKEN_NAME=...
export CLOUDFARE_API_TOKEN=...
export CLOUDFARE_R2_BUCKET_NAME=...
export CLOUDFARE_R2_BUCKET_URL=...

bash deploy/gcp/deploy.sh
```

The script is idempotent for the Cloud SQL instance (skips creation if it already exists) and re-runs `gcloud run deploy`/updates the worker VM's metadata + restarts it on subsequent runs — safe to re-run for redeploys.

### One-time prerequisites (a human must do these)

1. Create a GCP project and enable billing (console.cloud.google.com)
2. `gcloud auth login` (interactive — run it yourself, Claude can't complete an OAuth flow)
3. Create a free Upstash Redis database at upstash.com, copy its `rediss://` URL
4. Reuse the existing Cloudflare R2 bucket/token from the Railway deploy, or create a new one

### Known limitations of this setup

- `min-instances`/`max-instances` are pinned to 1 on the Cloud Run service. The Dockerfile runs `migrate` on every container boot (matches the Railway/Render pattern); running that against more than one concurrent instance risks racing migrations. Raise `max-instances` only after moving `migrate` out of the boot command (e.g. a separate `gcloud run jobs execute` step in CI).
- The Celery worker VM is a single e2-micro instance with no redundancy — acceptable for the current low-volume stage (matches the WebSocket/PWA TODOS.md items gated on "5-10 paying directors"), revisit if that changes.
