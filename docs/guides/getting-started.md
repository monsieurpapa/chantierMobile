# Getting Started

This expands the root [`README.md`](../../README.md#quick-start) quick-start with more
detail and common troubleshooting. Read the root README first for the five-minute path.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) running
- [`just`](https://github.com/casey/just#installation) installed

Everything else (Python, PostgreSQL, Redis) runs inside containers — there's no local
Python environment to manage for day-to-day development.

## First run

```bash
git clone https://github.com/monsieurpapa/chantierMobile.git
cd chantierMobile
cp .env.example .env   # edit SECRET_KEY / DEBUG / ALLOWED_HOSTS at minimum
just setup              # = dev-up + migrate + createsuperuser
```

`just setup` starts Django (`:8001`), PostgreSQL (`:5432`), Redis (`:6379`), the Celery
worker + beat scheduler, and Flower (`:5555`), applies migrations, then prompts you to
create a superuser.

## After first run, day to day

```bash
just dev-up      # start services
just dev-logs    # tail Django logs
just status      # container status + URLs
just dev-down    # stop services
```

Run `just` with no arguments for the full command list (it's generated from the
`justfile`, so it's always current).

## Creating your first Cabinet

The app has no data until you create at least one `Cabinet` and assign yourself a role:

1. Log in with the superuser account you created
2. Go to the Django admin (`/admin/`) or use `just shell` to create a `Cabinet` and a
   `UserCabinetRole` assigning your user a role (start with `DIRECTOR` to unlock
   everything)
3. Reload the app — the dashboard and navigation unlock based on that role

Alternatively, `just load-sample-data` (or `python manage.py seed_sample_data`) seeds a
representative Cabinet with sites, personnel, and transactions for exploring the UI
without data-entry.

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `just` commands hang or error "connection refused" | Docker Desktop isn't running | Start Docker Desktop, then `just dev-up` |
| Blank/500 page after pulling new code | Pending migrations | `just migrate` |
| New text not translated | `.po` edited but not compiled | `just i18n-compile` (compiled `.mo` files are what the app reads at runtime) |
| Login works but every page redirects to password change | Expected — new accounts force a password change on first login (`ForcePasswordChangeMiddleware`) | Complete the password-change form once |
| Logged out unexpectedly while working | 15-minute idle timeout (see [`docs/security.md`](../security.md)) | Log back in; if it's firing too aggressively in local dev, check `SESSION_IDLE_TIMEOUT_SECONDS` in `.env` |

## Next steps

- [`docs/architecture/overview.md`](../architecture/overview.md) — how the pieces fit together
- [`docs/guides/testing.md`](testing.md) — running and writing tests
- [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — code style, branching, PR checklist
