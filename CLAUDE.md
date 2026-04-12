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
