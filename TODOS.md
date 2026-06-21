# TODOS — ChantierMobile

Deferred work tracked here. Items added by `/plan-ceo-review` on 2026-03-31.

---

~~## P2 — Self-Approval Prevention~~ *(Implemented — `Expense.approve()` raises `ValidationError` when `requester == approver`; bypassable by `is_superuser`.)*

~~## P2 — Status Change Audit Log~~ *(Implemented — generic `StatusChangeLog` model in `core/models.py` using ContentTypes; migration `core/0001_status_change_log.py` applied; hooked into `SiteUpdateView.form_valid()` and `PaymentCreateView.form_valid()`.)*

~~## P3 — Budget Period Reporting~~ *(Implemented — `BudgetDetailView` with KPI cards, progress bar, category breakdown, burn-rate forecast, and recent expenses table. URL: `finance:budget_detail <pk>`. Budget list links to it.)*

~~## P3 — SiteDetailView Double Query~~ *(Fixed in commit 031deb1 — perf: eliminate duplicate site/expenses queries)*

~~## P2 — Fix `IsSuperAdminMixin` Duplicate Definition~~ *(Fixed — second definition removed from `accounts/views.py`)*

~~## P2 — Fix `cabinet_lookup_field` Pattern in `CabinetAccessMixin`~~ *(Fixed — `cabinet_lookup_field` class attribute added, `ExpenseListView` uses `site__cabinet`)*

~~## P1 — Cabinet Switcher for Superadmins~~ *(Implemented — `SwitchCabinetView`, `CabinetContextLog`, `active_cabinet_context`, navbar dropdown, falcon_base amber banner, queryset scoping across all apps)*

~~## P2 — Expense Approval Race Condition~~ *(Implemented — `Expense.approve()` and `reject()` wrapped in `transaction.atomic()`; `select_for_update()` on budget row in `approve()` to serialize concurrent approvals.)*

~~## P2 — Cross-Tenant Approval in Function-Based Action Views~~ *(Implemented — `approve_expense`, `mark_expense_paid`, `approve_material_request` now check `get_session_cabinet()` after `get_object_or_404` and block cross-cabinet mutations when a cabinet scope is active.)*

~~## P3 — CabinetDeleteView Cascade Warning~~ *(Implemented — `CabinetDeleteView.get_context_data()` now adds `site_count`, `expense_count`, `invoice_count`; template shows a red danger card listing all data that will be destroyed.)*

~~## P2 — Cabinet Scoping on `SiteAssignmentCreateView`~~ *(Implemented — `get_form()` override filters site and personnel FK dropdowns to user's cabinet; `cabinet_lookup_field = 'site__cabinet'` set for `CabinetAccessMixin`. Regression test added in `TestSiteAssignmentCabinetScoping`.)*

## P3 — Superadmin Banner on Assignment Form When No Cabinet Selected

When a superadmin opens `/personnel/assignments/add/` without an active cabinet selected, `get_session_cabinet()` returns `None` and the form shows all sites globally. Add a dismissible amber banner: "No cabinet selected — showing all sites. Use the cabinet switcher to scope to a specific firm." Priority: pre-demo polish, not a security issue (superadmins are trusted).

## P3 — `PersonnelListView` Missing `select_related`

`PersonnelListView.get_queryset()` has no `.select_related('cabinet')`. Fine at current data volume. Add before the list grows past 50 rows to avoid N+1.

## P3 — `BudgetListView` Manual Cabinet Filtering (DRY violation)

`BudgetListView.get_queryset()` manually filters `site__cabinet__id__in=user_cabinet_ids` instead of using `CabinetAccessMixin`. Pre-existing pattern, no active harm. Should be unified when touching `finance/views.py` next.

## P3 — `approve_material_request` Lacks `transaction.atomic()`

Unlike `Expense.approve()`, `approve_material_request` does a bare `mat_request.save()` without wrapping in `transaction.atomic()`. At current complexity (no child records modified atomically) this is fine. Add if the function is extended to also create an Expense or log entry.

## P3 — `StatusChangeLog` Not Wired to Invoice/Payment Status Changes

`StatusChangeLog.log()` is only called from `SiteUpdateView.form_valid()`. Invoice (DRAFT→SENT→PAID→OVERDUE) and Payment status transitions are not logged. Add when audit trail becomes a customer requirement.

---

*Items below added by `/plan-eng-review` on 2026-05-15 (frontend re-engineering review):*

## P3 — Cache Director List in `check_budget_warning` Signal

`check_budget_warning` queries `UserCabinetRole.objects.filter(cabinet=..., role=DIRECTOR)` on every expense approval. At current scale this is fine. When approval volume grows past ~50/day per cabinet, add `cache.get_or_set(f'cabinet_directors_{site.cabinet_id}', lambda: list(query), 60)` in `finance/signals.py`. **Requires:** add `cache.delete(f'cabinet_directors_{cabinet_id}')` call in `UserCabinetRole.save()` and `UserCabinetRole.delete()` to invalidate when directors change. Do not add the cache without also adding the invalidation.

## P3 — Bundle `BudgetListView` DRY Violation Fix in Phase 3

`BudgetListView.get_queryset()` manually filters `site__cabinet__id__in=user_cabinet_ids` instead of using `CabinetAccessMixin`. When Phase 3 (HTMX expense flow) touches `finance/views.py`, add `cabinet_lookup_field = 'site__cabinet'` to `BudgetListView` and remove the manual filter. Zero risk, one-liner fix.

## P3 — `approve_material_request` Lacks `transaction.atomic()`

When Phase 4 (materials HTMX) extends `approve_material_request` to create an Expense or log entry, wrap in `transaction.atomic()` at that point. Currently the bare `mat_request.save()` is fine. See `Expense.approve()` for the reference pattern.

## P3 — `StatusChangeLog` Wiring for Invoice/Payment

Bundle with Phase 4 (revenue HTMX). Wire `StatusChangeLog.log()` into `InvoiceUpdateView.form_valid()` and `PaymentCreateView.form_valid()` (the latter is already done per TODOS; verify Invoice is covered).

---

*Items below added by `/plan-ceo-review` on 2026-06-05 (Frontend Re-Engineering Railway edition):*

## P2 — PWA manifest + service worker

After first 10 paying directors are using Phase 2 for 30+ days, add `manifest.json` and a service worker with cache-first strategy for key views (Dashboard, Site Detail). This turns ChantierMobile into an installable app on Android — directors tap "Add to Home Screen" and it opens fullscreen like WhatsApp.

**Why:** Mobile-first audience in Goma; app store friction is high; PWA install creates daily-use habit.
**Depends on:** Phase 2 shipped and 10 paying directors acquired.
**Effort:** S (human: ~1 day / CC: ~20min)

## P2 — Railway WebSocket validation sprint

Before Phase 3 planning begins, deploy a minimal Django Channels consumer to Railway staging to validate WebSocket support end-to-end with Supabase PgBouncer (CONN_MAX_AGE=0) and Daphne. Open Question 4 from the design doc is deferred — not resolved.

**Why:** Phase 3 requires Channels/Daphne on Railway. Railway supports WebSockets natively but the Supabase PgBouncer + Daphne combination has known gotchas (CONN_MAX_AGE=0 required).
**Depends on:** Launch gate met (5 paying directors × 30 days on Phase 2).
**Effort:** S (human: ~2h / CC: ~15min)

~~## P1 — Update railway.toml to gevent workers before Phase 2 deploy~~ *(Done — `railway.toml` now uses `--worker-class gevent --workers 4 --worker-connections 200 --timeout 300`; `gevent` added to `requirements.txt`.)*

---

*Items below added by `/qa` on 2026-06-21 (full-app browser QA pass — see `.gstack/qa-reports/qa-report-localhost-2026-06-21.md` for fix details on the 12 issues resolved in the same session):*

## P3 — `tests/test_api.py` imports `djangorestframework`, which isn't installed

No API views, serializers, or `rest_framework` entry in `INSTALLED_APPS`/`requirements.txt` exist anywhere else in the codebase. This test file (449 lines, added in commit `f464529` "testing") was written for an API layer that was never built. Blocks `pytest` collection entirely unless run with `--ignore=tests/test_api.py`. Decide: build the API layer, or delete the test file.

## P3 — Browser tab `<title>` tags hardcoded in English

`site_detail.html` ("Site Details"), `personnel_detail.html` ("Personnel Details"), `budget_list.html` ("Budgets"), and others interpolate raw English into `{% block title %}`. Low visibility (browser tab only) — deprioritized during the i18n pass in favor of in-page content. Sweep all `{% block title %}` blocks for `{% trans %}` coverage when next touching i18n.

## P3 — Currency displayed as `$` throughout

Budgets, expenses, and invoices all render amounts as `${{ amount }}`. Plausibly intentional (USD is commonly used for large transactions in DRC), but never confirmed with product — flag before assuming it's correct.

## P3 — Seed data uses Senegal/Dakar addresses, not DRC/Goma

`accounts/management/commands/seed_sample_data.py` generates `+221` Senegal phone numbers and Dakar addresses, despite the target market being DRC/Great Lakes per the workspace's root `CLAUDE.md`. Cosmetic for demos, but worth aligning if sample data is ever shown to a DRC-based prospect.

## P2 — SSE keepalive comment (proxy 60s timeout)

Railway's reverse proxy closes idle SSE connections after ~60 seconds of no data. Add a keepalive comment event inside the `notification_stream` generator:

```python
# Inside the while True loop, before time.sleep(2):
yield ": keepalive\n\n"
```

**Effort:** XS (5 lines of code)
