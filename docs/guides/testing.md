# Testing

Tests live in `tests/` (not inside each app) and run inside Docker via `pytest`, wrapped
by `just`. The suite requires Docker Desktop to be running.

## Running tests

```bash
just test                              # All tests (≥80% coverage enforced)
just test-file tests/test_finance.py   # Single file
just test-app finance                  # Filter by keyword (pytest -k)
just test-unit                         # @pytest.mark.unit only
just test-integration                  # @pytest.mark.integration only
just test-e2e                          # @pytest.mark.e2e only
just test-fast                         # Stop on first failure (-x)
just test-debug                        # Drop into pdb on failure
just test-coverage                     # HTML report in htmlcov/
just test-parallel                     # pytest -n auto
```

## Configuration (`pytest.ini`)

- `--reuse-db` — the test database is preserved between runs; pass `--create-db` (or run
  `just test-coverage`/equivalent with it) after a schema change, since `--nomigrations`
  means schema is created directly from current models, not replayed through migrations.
- `--nomigrations` — faster test startup; this also means a broken migration file will
  **not** be caught by the test suite — always run `just migrate` against a real,
  from-scratch database before merging a schema change (see `CONTRIBUTING.md`).
- `--cov-fail-under=80` — the build fails below 80% coverage. This is enforced on every
  `just test` run, not just in CI.

## Markers

Declared in `pytest.ini`: `unit`, `integration`, `e2e`, `slow`, `auth`, `finance`,
`materials`, `personnel`, `projects`, `revenue`, `i18n`, `api`, `critical`. Use
`@pytest.mark.<name>` on a test class or function, and `just test-marker <name>` (or
`pytest -m <name>` directly) to run just that subset.

As a rule of thumb when writing a new test:

- **`unit`** — one model method or function, no HTTP request involved
- **`integration`** — a full view round-trip (request → response), still isolated to one
  feature
- **`e2e`** — a multi-step user workflow spanning several views/pages
- An app-specific marker (`finance`, `revenue`, ...) alongside whichever of the above
  applies, so `just test-app <name>` finds it

## Fixtures (`tests/conftest.py`)

Shared fixtures so individual tests don't each hand-roll users, cabinets, and roles:

| Fixture | Gives you |
|---|---|
| `client` | A plain Django test client |
| `user`, `superuser` | A regular / superuser account |
| `cabinet` | A `Cabinet` |
| `user_cabinet_role` | A `UserCabinetRole` tying `user` to `cabinet` (default role) |
| `director_user`, `engineer_user`, `accountant_user` | A user with that role already granted on `cabinet` |
| `director_client`, `engineer_client`, `accountant_client` | A logged-in test client for the corresponding role |
| `admin_client` | A logged-in test client for `superuser` |
| `site_factory` / `site` / `active_site` | A `Site` (or a factory to make more), scoped to `cabinet` |
| `phase_factory` / `phase` | A `ProjectPhase` on `site` |
| `expense_category_factory` / `expense_category` | An `ExpenseCategory` |
| `sample_date`, `future_date`, `past_date`, `sample_amount` | Common literal test values |
| `sample_image_file`, `mock_file_upload` | File-upload test doubles |
| `mock_email_backend` | Captures outgoing emails instead of sending |
| `freeze_time` | Time-freezing helper for date-sensitive logic (state-of-need deadlines, overdue invoices) |

Prefer composing from an existing `*_client` fixture (e.g. `director_client`) over
manually logging in a user in a new test — it keeps role setup consistent with every
other test and with the `RoleRequiredMixin`/`can_act_for_cabinet` checks being exercised.

## Factories (`tests/factories.py`)

`factory_boy`-based factories for generating model instances with sensible defaults:
`UserFactory`, `SuperUserFactory`, `CabinetFactory`, `UserCabinetRoleFactory`,
`SiteFactory`, `ProjectPhaseFactory`, `SiteProgressFactory`, `ExpenseCategoryFactory`,
`ExpenseFactory`, `BudgetFactory`, `MaterialFactory`, `MaterialRequestFactory`,
`MaterialRequestItemFactory`, `PersonnelFactory`, `SiteAssignmentFactory`,
`SkillFactory`, `ContractFactory`, `InvoiceFactory`, `PaymentFactory`. Two composite
helpers build a larger, realistic graph in one call: `CompleteProjectFactory` and
`TestDataGenerator`.

Use a factory over a fixture when a test needs several instances, specific field
overrides, or a relationship fixtures don't already model — `SiteFactory(cabinet=cabinet,
status=SiteStatus.ACTIVE)` rather than hand-building the object.

## Writing a regression test for a bug fix

The established convention in this codebase (see `git log` and `tests/`) is to name the
test after the issue it closes, e.g. `test_issue_015_no_n_plus_one_on_has_role`, so the
connection between bug and test is traceable without a separate tracker. Reproduce the
original failure first (the test should fail against the pre-fix code), then fix it.

## What CI enforces

The same `pytest.ini` configuration runs in CI as locally — there's no separate CI-only
test config to keep in sync. A green `just test` locally should mean a green CI run,
modulo environment differences (`DATABASE_URL`/`REDIS_URL` wiring — see
`.github/` workflow files for the exact CI environment).
