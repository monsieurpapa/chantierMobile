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

~~## P3 — Superadmin Banner on Assignment Form When No Cabinet Selected~~ *(Fixed by /qa on main, 2026-09-10 — dismissible amber banner added to `assignment_form.html`, gated on `no_cabinet_selected` context flag from `SiteAssignmentCreateView.get_context_data()`.)*

~~## P3 — `PersonnelListView` Missing `select_related`~~ *(Fixed by /qa on main, 2026-09-10 — added `.select_related('cabinet')` to `get_queryset()`.)*

~~## P3 — `BudgetListView` Manual Cabinet Filtering (DRY violation)~~ *(Fixed by /qa on main, 2026-09-10 — now uses `CabinetAccessMixin` with `cabinet_lookup_field = 'site__cabinet'`, manual filter removed.)*

## P3 — `approve_material_request` Lacks `transaction.atomic()`

Unlike `Expense.approve()`, `approve_material_request` does a bare `mat_request.save()` without wrapping in `transaction.atomic()`. At current complexity (no child records modified atomically) this is fine. Add if the function is extended to also create an Expense or log entry.

~~## P3 — `StatusChangeLog` Not Wired to Invoice/Payment Status Changes~~ *(Partially resolved by /qa on main, 2026-09-11 — the SENT/OVERDUE→PAID auto-transition now always logs via `Invoice.check_and_mark_paid()`, called from `Payment.save()`, so it's covered regardless of entry point (was previously only logged from `PaymentCreateView`). Still not logged: DRAFT→SENT and any→CANCELLED — there is no `InvoiceUpdateView` in the codebase at all, so those transitions currently have no UI path either; add logging when that view gets built.)*

---

*Items below added by `/plan-eng-review` on 2026-05-15 (frontend re-engineering review):*

## P3 — Cache Director List in `check_budget_warning` Signal

`check_budget_warning` queries `UserCabinetRole.objects.filter(cabinet=..., role=DIRECTOR)` on every expense approval. At current scale this is fine. When approval volume grows past ~50/day per cabinet, add `cache.get_or_set(f'cabinet_directors_{site.cabinet_id}', lambda: list(query), 60)` in `finance/signals.py`. **Requires:** add `cache.delete(f'cabinet_directors_{cabinet_id}')` call in `UserCabinetRole.save()` and `UserCabinetRole.delete()` to invalidate when directors change. Do not add the cache without also adding the invalidation.

~~## P3 — Bundle `BudgetListView` DRY Violation Fix in Phase 3~~ *(Fixed by /qa on main, 2026-09-10 — see above.)*

## P3 — `approve_material_request` Lacks `transaction.atomic()`

When Phase 4 (materials HTMX) extends `approve_material_request` to create an Expense or log entry, wrap in `transaction.atomic()` at that point. Currently the bare `mat_request.save()` is fine. See `Expense.approve()` for the reference pattern.

~~## P3 — `StatusChangeLog` Wiring for Invoice/Payment~~ *(Payment side resolved by /qa on main, 2026-09-11 — see the P3 item above. Invoice DRAFT→SENT/CANCELLED logging still waits on `InvoiceUpdateView` existing at all; bundle with Phase 4 when that view is built.)*

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

~~## P3 — `tests/test_api.py` imports `djangorestframework`, which isn't installed~~ *(Resolved by /qa on main, 2026-09-10 — deleted; no API layer exists anywhere else in the codebase.)*

~~## P3 — Browser tab `<title>` tags hardcoded in English~~ *(Fixed by /qa on main, 2026-09-10 — `{% trans %}`/`{% blocktrans %}` added to all `{% block title %}` blocks across `projects/` and `personnel/` templates and `500.html`.)*

## P3 — Currency displayed as `$` throughout

Budgets, expenses, and invoices all render amounts as `${{ amount }}`. Plausibly intentional (USD is commonly used for large transactions in DRC), but never confirmed with product — flag before assuming it's correct.

~~## P3 — Seed data uses Senegal/Dakar addresses, not DRC/Goma~~ *(Fixed by /qa on main, 2026-09-10 — `seed_sample_data.py` now uses DRC (+243) phone numbers, Congolese names, and Goma neighborhoods (Himbi, Katindo, Majengo).)*

~~## P2 — SSE keepalive comment (proxy 60s timeout)~~ *(Stale — no `notification_stream` generator or SSE endpoint exists anywhere in the codebase as of 2026-09-10. Feature described here was apparently never built. Nothing to fix; removing this item.)*

---

*Items below added by `/qa` on 2026-09-10 (finish-up pass ahead of first GCP deploy):*

## Boilerplate contamination from the wrong starter template (mostly fixed)

This project was bootstrapped from an unrelated "DevBoks"/"CMC"/"TicTacFlow Solutions" recruitment-portal boilerplate and the rebrand to ChantierMobile was incomplete. Found and fixed:

- **Critical (was breaking production):** `templates/account/email/email_confirmation_message.html/.txt` and `password_reset_key_message.html` extended `templates/email/base.html`/`base.txt`, which never existed. Every signup email-confirmation and password-reset in production would 500. Created `templates/email/base.html` and `base.txt` with ChantierMobile branding; removed leftover "CMC Team" signature.
- **Critical (dead but confusing):** `templates/account/profile.html` and `templates/includes/breadcrumb.html` referenced a nonexistent `recruitment` app/namespace. Confirmed both are unreachable (no view renders them) and deleted them, along with two unreferenced `activation_email.html/.txt` templates using a non-allauth template naming convention.
- **Cosmetic (live, user-visible):** every page's navbar/footer/login-page logo pointed at `TicTacFlow_logo*.png` static assets and linked to `TicTacFlowSolutions.com`; the login page welcome text read "Assistance Technique en Genie Civil's Self Service Portal". Replaced with a ChantierMobile wordmark/mark (new SVGs at `static/app/img/chantiermobile-*.svg`) and correct copy.
- **Not fixed — needs a designer:** the actual favicon files at `static/assets/img/favicons/cmc/*.ico`/`*.png` are still the old boilerplate's raster icons (browser tab icon). Fixing the `manifest.json` name was a one-line change and is done; regenerating the icon binaries themselves needs real image tooling this session didn't have.
- Also removed two orphaned, unreferenced templates (`templates/landing.html`, `templates/dashboard.html`) that were a completely different unrelated recruitment-portal landing page with the wrong branding — dead code, never wired to any URL.

Also worth a look next time someone's in `docker-compose.yml`: the postgres service is still named `tictacflow-postgres-service` — purely internal, not user-facing, left alone this pass.

## Timezone bug: `timezone.now().date()` used instead of `timezone.localdate()`

`TIME_ZONE = 'Africa/Kigali'` (UTC+2) with `USE_TZ = True`, but `Budget.is_budget_period_active()` (`finance/models.py`), `BudgetDetailView`'s burn-rate forecast (`finance/views.py`), `Site.active_assignments` (`projects/models.py`), and the daily `mark_overdue_invoices` Celery task (`revenue/tasks.py`) all computed "today" via `timezone.now().date()`, which returns the **UTC** calendar date, not the local Kigali date. Any time between 22:00–23:59 UTC (i.e. after midnight in Kigali), this silently disagreed with `date.today()` used everywhere else in the codebase (forms, seed data, tests) — causing spurious "Budget period is not active" rejections and one-day-late overdue-invoice transitions right at the daily boundary. Fixed by switching all four call sites to `timezone.localdate()`. This is what was actually causing 7 of the failures in `tests/test_critical_business_logic.py` (all now pass, 50/50).

~~## Pre-existing test debt: 38 failing tests outside critical-business-logic scope~~ *(Resolved by /qa on main, 2026-09-11 — triaged and fixed all 37/38 across `test_integration.py` (12), `test_e2e_workflows.py` (8), `test_unit.py` (3), and `test_performance.py` (14). Nearly all were test-file bugs (stale `pk`-vs-`unique_id` reverse() calls, `Expense.expense_date` missing from POSTs/factories, `UserFactory` pinned to Django's builtin `auth.User` instead of the swapped `AUTH_USER_MODEL`, thread-unsafe factory Sequence usernames, `Client.request` misread as the last request object, wall-clock perf thresholds that don't hold in this dev environment). Two real app bugs surfaced along the way and got fixed too: `Invoice` only auto-transitioned to PAID from `PaymentCreateView`, never from a direct `Payment` create (now on `Invoice.check_and_mark_paid()`, called from `Payment.save()`); and the `has_role` template tag re-queried on every call with no caching, causing a 206-query N+1 on the site list page for 100 sites (now cached per-request on the user instance, 206 → 8 queries). Also deleted `TestSearchIntegration`/`TestAPIIntegration`/`TestAPIPerformance`/the search half of `TestSearchPerformance` — no `search` URL or `/api/` endpoints exist anywhere, same class of issue as the already-deleted `tests/test_api.py`. 127/127 passing full-suite.)*
