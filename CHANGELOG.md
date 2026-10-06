# Changelog

All notable changes to ChantierMobile are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This
project has not followed semantic versioning historically (no tags have been cut — every
change has shipped straight to `main`); entries below are grouped by the date they
landed instead. Going forward, new work should be added under **[Unreleased]** and a
dated heading cut when a deliberate release point is agreed on.

## [Unreleased]

### Fixed
- `/user/profile/update/` 500'd for any logged-in user with at least one
  Site visible in their cabinet(s) — reported directly from production.
  The "Projects (Authorized Cabinets)" section's
  `{% url 'projects:site_detail' pk=site.id %}` link passed `pk`, but
  that URL pattern takes a `unique_id` (UUID) kwarg, so it raised
  `NoReverseMatch` on every render once the `sites` queryset was
  non-empty — invisible in the one existing smoke test, which used a
  bare user with no cabinet data at all, so that section's `{% for %}`
  loop never actually ran. Fixed in `templates/account/user_profile_update.html`
  to pass `unique_id=site.unique_id`, matching every other template's
  `projects:site_detail` link. New regression test
  (`test_profile_update_renders_with_a_visible_site` in
  `tests/test_auth_templates_render.py`) attaches a real cabinet role and
  Site before loading the page, confirmed to reproduce the exact
  `NoReverseMatch` on the pre-fix template and pass after.

### Added
- CASHIER permission-table update, requested for the role's day-to-day
  cabinet work:
  - Hid the "Tâches" sidebar nav item from CASHIER (superusers still see
    it regardless of role).
  - CASHIER can now register and edit Personnel profiles
    (`personnel/views.py`'s `PersonnelCreateView`/`UpdateView`), without
    extending to the rest of `HR_ADMIN_ROLES` territory (Leave/Holiday
    decisions, Skills).
  - Added `Caisse.responsible_cashier` (new field + migration) and
    `CaisseTransactionUpdateView` (no edit path existed before this): only
    a caisse's designated `responsible_cashier`, or whoever recorded a
    given mouvement, may now edit it — bypassable only by `is_superuser`,
    matching the app's existing self-administration pattern. An
    `ACCOUNTANT` can be set as `responsible_cashier` too, for a
    limited-staff cabinet where the accountant also acts as cashier.
    `CaisseTransactionDeleteView`'s existing cabinet-wide
    `CAISSE_MANAGE_ROLES` gating was deliberately left unchanged (not
    requested) — see `docs/modules/finance.md`.
  - Already true before this change, no code needed: CASHIER could already
    disburse a "liste de paie" (`PAYROLL_DISBURSE_ROLES`).

  See `docs/security.md`'s permission matrix and `docs/modules/personnel.md`/
  `docs/modules/finance.md` for the full detail.

## [2026-10-06] — Security fixes from the documentation pass

Five authorization gaps surfaced while writing `docs/` and docstrings across the
codebase (close code-reading tends to find these). Fixed one at a time, each with
its own regression tests; see `docs/security.md` for the current, corrected
behavior.

### Fixed
- `price_items_data_api` required no authentication and applied no cabinet filter,
  leaking every cabinet's price catalog to anonymous requests — now requires login
  and scopes results to the requester's own cabinet(s)
- `Avenant.approve()`/`reject()` had no guard against the requester deciding their
  own budget change order (unlike the equivalent `Expense.approve()`) — now blocks
  self-decision the same way
- `MaterialRequest`'s two-stage état de besoin approval
  (`magasinier_validate`/`authorize`/`reject`) was fully self-administerable by the
  requester for the same reason — same guard added at every stage
- `SiteProgressCreateView` looked up its phase with no cabinet filter and never
  scoped its role check to the phase's own cabinet, letting a user in one cabinet
  file a progress report against another cabinet's phase — now cabinet-scoped like
  its sibling views
- `UserCabinetRole`'s RBAC helpers (`CabinetAccessMixin`, `RoleRequiredMixin`,
  `can_act_for_cabinet`, `can_view_cabinet`, `has_role`, and the many ad-hoc
  `UserCabinetRole` queries duplicated across each app's views) never filtered on
  `status=APPROVED`, so a role grant still awaiting a superadmin's approval already
  granted full access — every one of those checks now requires an APPROVED grant
  (`User.approved_cabinet_roles`)

## [2026-09-24 – 2026-09-25] — Directors/Engineers feature audit

A full pass through what Directors and Engineers need day-to-day, closing 16 identified
gaps.

### Added
- In-app notifications (bell icon, per-role targeting) for approval events
- Global search across sites, personnel, contracts, and invoices
- PDF export for invoices, contracts, and payroll lists
- A unified "Approbations en attente" (pending approvals) inbox aggregating every
  approval-shaped item a user can act on, across apps
- Attendance / pointage tracking (daily sheet + history) for site personnel
- Quick-create shortcuts from the dashboard's "Accès rapide" cards and from the
  "Ajouter un Agent" form
- Engineer self-service: own-site budget visibility, own-site planning submission, crew
  assignment and leave recording for an engineer's own site
- Session idle timeout — an authenticated session is logged out after 15 minutes of
  inactivity, with an explicit "session expired" message (`SessionIdleTimeoutMiddleware`)

### Changed
- "Ingénieurs & Staff" salary payments reworked into a brouillon → soumise → payée
  (draft → submitted → paid) workflow
- Material-request edits locked to the original requester once submitted

### Fixed
- Invoice send/payment dead end — Directeur Technique/Général wiring completed
- Assorted dead-end dropdowns, duplicate toasts, and remaining i18n gaps

### Security
- 15-minute inactivity logout, independent of the existing session cookie age

## [2026-09-21 – 2026-09-23] — Finance depth & multi-cabinet hardening

### Added
- Cashier / Magasinier workflows: expense nature + personnel linkage, free-text
  materials, stock movements with facture (invoice) attachment, caisse-tagged
  purchases with a filterable PDF report, payment-proof upload with automatic director
  notification, devis photo alternative, client balance tracking
- HR roles (Directeur Technique, Directeur Général, Financier) and an Administration
  module for managing them
- Caisse ledger: balance-tracked cash registers, daily cashbook, inter-caisse loans
- Progressive worker payroll ("Liste de paie") and avenants (change orders)
- Wire-transfer purchases and supplier-credit tracking (Phase B3)
- Lead engineer assignment, planning submission review, and phase closure (Phase C)
- Stock transfers, periodic stock reports, and two-stage material-request approval
  (Phase D)
- Dynamic "select or add new" pickers for progressively-grown master data

### Changed
- "Liste de paie" split into separate Main d'œuvre (labor) / Ingénieurs & Staff tabs
- Superadmin given full CRUD on users, roles, and cabinet permissions

### Fixed
- Finance money-flow gaps found in a feature audit (director expense visibility per
  site, expense recipient/approver, empty Catégorie/Étape dropdowns)
- Personnel eligibility enforcement aligned with the caisse report's expense filters
- Caisse fixes and Personnel/Liste de paie overhaul from finance-team demo feedback
- Authentication template consistency and navigation
- CI: `gettext` installed before `compilemessages`; `DEBUG` read as a proper boolean so
  `DATABASE_URL` doesn't force SSL in CI
- Multi-cabinet isolation gaps closed ahead of broader SaaS multi-tenancy

## [2026-09-18 – 2026-09-19] — Pricing, Procurement, Tasks, and RBAC hardening

### Added
- **Pricing module**: `PriceLibraryItem` catalog, DQE (devis quantitatif estimatif) and
  `DQELine` models with an inline formset, DQE views, API, and templates
- **Revenue**: Devis and Situations de travaux (progress billing) models, forms, and views
- **Procurement module**: Achats / Bons de commande (purchase orders) + Stocks
- **Tasks module** (task tracking) and a `personnel_type` field distinguishing
  tâcherons/prestataires from regular staff
- Real-time analytics on the main dashboard
- Forced password-change redirect to a role-gated dashboard

### Changed
- RBAC hardened across action views; navigation, pagination, and confirmation dialogs
  improved

### Security
- A committed `.env` file identified and removed from version control tracking

## [2026-06-04 – 2026-09-11] — QA hardening and deployment options

A sustained QA pass fixing translation, display, and test-suite issues identified across
several review rounds (tracked as `ISSUE-NNN` in commit messages), plus a second
deployment target.

### Added
- Railway deployment configuration (gevent workers, env example) as an alternative to
  Render

### Fixed
- Extensive French translation coverage: hardcoded English strings, fuzzy/incorrect
  `.po` entries, wrong translations across dashboard, personnel, revenue, and admin
  pages (ISSUE-002 through ISSUE-011)
- Invisible status badges (`bg-soft-*` / `badge-subtle-*` contrast issues) across the app
- A 500 error on the personnel detail/edit pages (`Personnel.get_full_name()`)
- Template tags that were split across lines and rendered literally instead of being
  parsed
- Invoice auto-PAID transition, previously only firing from `PaymentCreateView`
  (ISSUE-013)
- `BudgetForm` `end_date` validation error not attached to its field (ISSUE-014)
- An N+1 query in the `has_role` template tag, fixing all `test_performance.py`
  failures (ISSUE-015)
- `seed_sample_data` management command (3 bugs) and 12 pre-existing
  `test_integration.py` failures from fixture/assertion staleness
- All 8 pre-existing `test_e2e_workflows.py` failures

## [2026-04-13 – 2026-04-15] — Security hardening, multi-tenant switcher, production deploy

### Added
- Cabinet context switcher for superadmins, with an `active_cabinet_context` session
  helper and a visible "viewing as" banner
- `StatusChangeLog` audit model (generic, via ContentTypes) hooked into site updates and
  payment creation
- Budget detail view: KPI cards, progress bar, category breakdown, and burn-rate forecast
- Production deployment config for Render + Supabase + Upstash Redis + Cloudflare R2

### Fixed
- `@login_required` added to approval function-based views; RBAC scoped to Cabinet;
  soft-delete cascaded on `Site`
- Inline role strings eliminated in favor of `chantiermobile/constants.py` enums
- A duplicate-query performance issue in `SiteDetailView` and `UserProfileUpdateView`
- Design/accessibility findings: decorative background circles removed from login,
  dead `<script>` tags removed, sign-up button class/icon corrected, capitalization and
  dead `href="#"` links fixed on Materials/Revenue dashboard cards

## [2026-03-31 – 2026-04-01] — Revenue module v1

### Added
- Budget enforcement and an expense-approval state machine
  (Pending → Approved/Rejected → Paid)
- Invoice state machine (Draft → Sent → Paid/Overdue → Cancelled) with a daily Celery
  task auto-marking overdue invoices
- Revenue module UI: payment list, invoice detail, navbar integration
- Full i18n coverage across all apps (French default, English alternate)
- Render.com deployment configuration
- `seed_test_data` management command for QA

### Security
- A security-hardening pass across views for correctness

## [2026-01-23 – 2026-01-27] — Initial platform

### Added
- Initial Django project scaffold: Projects, Personnel, Finance, Materials apps
- Multi-material material requests, message toasts, base navigation
- Multilingual (French/English) foundation and centralized constants
- First test coverage

---

For the detailed, commit-by-commit history behind any entry above, see `git log`. Older
point-in-time implementation write-ups from earlier in the project are preserved under
[`docs/history/`](docs/history/) for reference; the content above supersedes them as the
canonical summary.
