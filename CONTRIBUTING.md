# Contributing to ChantierMobile

This is a private, proprietary codebase (see [LICENSE](LICENSE)). This guide is for
people who have been given access to contribute — collaborators, contracted
developers, or future hires — not a public open-source contribution guide.

## Table of Contents

- [Before you start](#before-you-start)
- [Local setup](#local-setup)
- [Branching model](#branching-model)
- [Commit messages](#commit-messages)
- [Code style](#code-style)
- [Testing requirements](#testing-requirements)
- [Pull request checklist](#pull-request-checklist)
- [Adding a new Django app](#adding-a-new-django-app)
- [Database migrations](#database-migrations)
- [Translations](#translations)

## Before you start

Read these first, in order:

1. [`README.md`](README.md) — what the product is, tech stack, quick start
2. [`docs/architecture/overview.md`](docs/architecture/overview.md) — multi-tenancy (Cabinet),
   role-based access control, base models, status state machines
3. [`docs/security.md`](docs/security.md) — the security model: this is a construction-finance
   system handling budgets, payroll, and client payments, so changes to permissions,
   approval flows, or session handling get extra scrutiny
4. The relevant `docs/modules/<app>.md` page for the app you're changing

## Local setup

Everything runs in Docker via [`just`](https://github.com/casey/just):

```bash
cp .env.example .env   # edit with your values
just setup             # dev-up + migrate + createsuperuser
```

See [`docs/guides/getting-started.md`](docs/guides/getting-started.md) for the full walkthrough
and troubleshooting.

## Branching model

- `main` is always deployable. Direct commits to `main` are reserved for trivial,
  already-tested fixes (docs, config); everything else goes through a branch + PR.
- Branch names follow `<type>/<short-description>`, matching the commit convention below,
  e.g. `feat/attendance-tracking`, `fix/invoice-overdue-task`.
- Rebase on `main` before opening a PR; merge commits from `main` into a long-lived
  feature branch are fine if a rebase would be painful.

## Commit messages

This repo does not enforce Conventional Commits mechanically, but recent history follows
it loosely and new commits should too:

```
<type>(<scope>): <short summary, imperative mood>

<optional body — the "why", not a restatement of the diff>
```

Common `<type>` values used in this repo: `feat`, `fix`, `docs`, `test`, `chore`, `style`,
`perf`, `security`. `<scope>` is usually the app name (`finance`, `revenue`, `qa`, `deploy`,
`i18n`) or omitted for repo-wide changes. See `git log` for real examples — e.g.
`fix(qa): ISSUE-015 — N+1 in has_role template tag`, `feat(i18n): complete internationalization
across all apps`.

For a change requested by a specific finding, ticket, or audit item, reference it in the
subject (`ISSUE-013`, `item 12`) so it's traceable in `git log` without a separate tracker.

## Code style

```bash
just format        # black — auto-formats
just sort-imports   # isort — auto-sorts imports
just lint           # flake8 — reports issues, does not auto-fix
just quality         # all three together; run this before every commit
```

Beyond the automated formatters:

- **Docstrings**: every module, model, and non-trivial view/function should have a
  docstring that explains *why*, not just *what* — assume the reader can read the code
  but not the four other call sites that explain the constraint. See `core/approvals.py`
  or `core/dashboard.py` for the house style.
- **No inline role/status string literals.** Role names, status values, and similar
  enums live in `chantiermobile/constants.py` as `TextChoices`. Import from there —
  grep for `UserRoles.DIRECTOR` style usage before typing `'DIRECTOR'` by hand.
- **State transitions are validated in `model.clean()`**, not just in the view. If you add
  a new status field or transition, add the guard to `clean()` so it can't be bypassed by
  a future view, shell session, or management command. See `docs/architecture/overview.md`
  for the existing state machines.
- **Every business model inherits `core.models.BaseModel`** (soft delete, `created_by`/
  `updated_by`, timestamps, `unique_id`). Don't hand-roll these fields on a new model.
- **Queryset scoping**: any view touching tenant data uses `CabinetAccessMixin` (or
  explicitly scopes by `site__cabinet` / `cabinet` with the same rules) — never trust a
  URL-supplied primary key without a cabinet check. This is the single most
  security-relevant convention in the codebase; see `docs/security.md`.

## Testing requirements

```bash
just test            # full suite — coverage must stay ≥80% (enforced by pytest.ini)
just test-app finance # filter by keyword
just test-unit        # @pytest.mark.unit only
just test-fast        # stop on first failure
```

- New business logic needs tests in `tests/` — unit tests for model/state-machine
  behavior, integration tests for the full view flow, and an e2e test if it's a new
  user-facing workflow spanning several pages.
- A bug fix should add a regression test reproducing the original bug, named so the
  connection is obvious (see the `ISSUE-NNN` pattern already used throughout `tests/`).
- Run the full suite locally before opening a PR — `pytest.ini` enforces
  `--cov-fail-under=80`, and CI will reject a PR that drops below it.

## Pull request checklist

- [ ] `just quality` passes (black, isort, flake8)
- [ ] `just test` passes with coverage ≥80%
- [ ] New/changed models and non-trivial functions have docstrings
- [ ] Any new status/role string goes through `chantiermobile/constants.py`
- [ ] Any new tenant-scoped view uses `CabinetAccessMixin` / `RoleRequiredMixin`
- [ ] User-facing strings are wrapped for translation (`gettext_lazy`) — see
  [Translations](#translations)
- [ ] `docs/modules/<app>.md` updated if the change affects that app's models, views, or
  workflow in a way future readers would need to know
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`

## Adding a new Django app

1. `docker-compose exec chantiermobile-service python manage.py startapp <name>`
2. Add it to `INSTALLED_APPS` in `chantiermobile/settings.py`
3. Add its models' status/role enums to `chantiermobile/constants.py` rather than the
   app's own `models.py`, if they're referenced from other apps (most are)
4. Inherit `core.models.BaseModel` for anything that needs soft delete/audit/timestamps
5. Register its URLs in `chantiermobile/urls.py` with an app namespace
6. Add a `docs/modules/<name>.md` page (see existing ones for the expected structure)
7. Add it to the relevant test markers in `pytest.ini` if it warrants its own marker

## Database migrations

- Run `just makemigrations` after model changes, and commit the generated migration
  file — don't hand-edit migrations unless you know exactly why.
- Data migrations (not just schema) should be a separate migration file with a clear
  name, and should be reversible where practical.
- `pytest.ini` runs tests with `--nomigrations` for speed, so a broken migration won't
  surface in CI test runs — always run `just migrate` locally against a fresh database
  before merging a schema change.

## Translations

The app supports French (default) and English. Every user-facing string must be wrapped:

```python
from django.utils.translation import gettext_lazy as _
label = _("Submit for approval")
```

After adding strings:

```bash
just i18n-extract   # regenerates locale/*/LC_MESSAGES/django.po
# translate the new msgid entries in locale/fr/... and locale/en/...
just i18n-compile    # compiles .po → .mo
```

Commit both the `.po` and compiled `.mo` files — the app reads compiled translations at
runtime, so a `.po`-only change has no visible effect until compiled.
