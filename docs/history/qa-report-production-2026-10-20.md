# QA report — production, 2026-10-20

**Scope:** read-only pass over the live app
(`chantiermobile-168453882291.us-central1.run.app`), signed in as superadmin,
"Tous les cabinets". Every menu page (40) was loaded and timed; detail pages,
forms, global search and the asset bundle were inspected. Nothing was
submitted. Phone-width (390 px) and JavaScript-error checks were then run on
a local copy in production mode (`DEBUG=False`, gunicorn, Django 6.0.9 — the
version production installs), since the production browser window could
not be resized.

**Production data seen:** one cabinet ("ATGC Congo"), 2 chantiers
(Marguerite, Chemin de perfection), 10 personnel, 3 caisses, 6 listes de
paie, 1 budget, no DQE, no Bibliothèque de Prix entries, no devis.

Fixes are on branch `fix/qa-2026-10-20`, one commit per finding, with
regression tests in `tests/test_qa_production_2026_10_20.py`.

| # | Severity | Area | Finding | Status |
|---|----------|------|---------|--------|
| 1 | Critical | Pricing / deploy | The CCLK "synthèse par étape" DQE migration (`pricing/0010`, merged in #13) only targets a "Cabinet Principal" cabinet; production's only cabinet is "ATGC Congo", so it skips and creates nothing. | Fixed |
| 2 | Critical | Security | Every page loads `https://polyfill.io/v3/polyfill.min.js`. That domain was taken over in 2024 and served malicious code to sites using it. | Fixed |
| 3 | Critical | Settings / performance | (a) Production runs Django 6, which ignores the removed `DEFAULT_FILE_STORAGE` / `STATICFILES_STORAGE` settings: **uploads go to the Cloud Run container's ephemeral disk instead of Cloudflare R2** (lost on every redeploy/restart), and static files are neither hashed nor compressed (`Cache-Control: max-age=60`). (b) Every page loads 39 JS/CSS files, including assets no page uses: Leaflet + 2 plugins, `world.js` (216 KB), both RTL stylesheets (776 KB, downloaded even while disabled), a duplicate lodash. | Fixed |
| 4 | Medium | Personnel | "Tarif par défaut" shows **`$None`** for every worker without a default daily rate (list and detail). | Fixed |
| 5 | Medium | Projects | "Filter" and "Export" buttons on the chantiers list do nothing (no link, no script), and are in English. | Fixed |
| 6 | Medium | Finance | Amounts without thousands separators (Budgets "$30000,00", Vue DG "$4400,00", chantier detail "$30000" — 88 places in 27 templates); negative caisse balances read "$-200,00". | Fixed |
| 7 | Low | i18n | Browser-tab titles in English: "Expenses", "Material Catalog", "Material Requests", "Contracts", "Payments", "Role Assignments". | Fixed |
| 8 | Low | Layout | 404/500 pages scroll sideways and throw a JS error (logo script assumes the sidebar exists); the footer's negative gutters push pages 8 px past a phone screen. | Fixed |
| 9 | Low | Layout | Chantier detail: the four buttons next to "Phases et avancement du projet" are squeezed into the title row (labels on 3 lines) and push the page to 573 px on a phone. | Fixed |
| 10 | Low | Payroll | "Préparée par" shows the login name ("dieudonneishara"). The template already prefers the full name; the account simply has no first/last name. | No code change — fill in the name under "Paramètres du profil" |
| 11 | Low | Search | Global search (`/recherche/`) covers chantiers, personnel, contracts, invoices — not materials, suppliers, DQE or devis ("ciment" finds nothing). | Open |
| 12 | Low | Layout | The fixed top bar (search, role badges, e-mail) is ~115 px tall and semi-transparent; content scrolls visibly underneath. The sidebar logo block is ~120 px. "Modules"/"Administration" labels sit flush-left. | Open |
| 13 | Low | Security | jQuery 3.2.1 (2017, cdnjs) has known XSS fixes in 3.5+. Upgrading needs a pass over the custom scripts (3.5 changed `htmlPrefilter`). | Open |
| 14 | Info | Data | Two caisses are negative ("Bétonnière" −$200,00, "Caisse principale" −$10,00). Check whether overdraft is intended. | Open |
| 15 | Info | Infra | Server time is small (~70 ms for a list page, ~380 ms for the dashboard); most latency is the ~370 ms round trip from DRC to `us-central1` — a static file takes as long as a page. Cloud Run and Cloud SQL are available in `africa-south1` (Johannesburg); moving both would cut every request for users in Goma. With finding 3 fixed, static files are downloaded once and cached, so the round-trip cost applies to pages only. | Open |
| 16 | Info | Dev | `tests/conftest.py` overrides `django_db_setup` with a no-op, so tests run against the configured database, and transactional tests flush it — running `just test` locally empties the dev database. | Open |

## Notes per finding

1. New migration `pricing/0011` re-runs the 0010 seed with a wider rule: the
   existing "Appartements CCLK" chantier, else "Cabinet Principal", else the
   only cabinet when there is exactly one. No-op on empty databases, on
   databases with several cabinets and none of those, and when the DQE
   already exists — safe whether 0010 ran or skipped. Verified on a
   production-like database (only "ATGC Congo", 0010 applied): creates
   DQE-CCLK-SYN-001, 91 lines, $51,900.10.
2. Script tag removed; nothing relied on it.
3. (a) Storages now declared in `STORAGES`: `MediaStorage` (R2) for uploads
   and `StaticStorage` (WhiteNoise `CompressedManifestStaticFilesStorage`)
   for static files in production; plain storages in DEBUG. `StaticStorage`
   keeps references to files that don't exist in vendored theme CSS (e.g.
   `leaflet.css` → `images/layers.png`) instead of aborting `collectstatic`,
   which the container runs on boot. Verified: 1,099 files hashed and
   gzip'd; `theme.min.css` served at ~93 KB instead of ~770 KB with
   `Cache-Control: max-age=315360000, public, immutable`.
   (b) 39 → 21 JS/CSS files per page. Kept: echarts (dashboard), Chart.js
   (used by `theme.js`), DataTables, select2. No JavaScript errors on 27
   signed-in pages checked in production mode.
4. Shows "—" when there is no rate; the rate is grouped when set.
5. Removed; the global search remains.
6. `floatformat:"2g"`/`"0g"` everywhere an amount follows the currency
   symbol (no input values or JavaScript touched). New `money` filter
   (`core/templatetags/money.py`) for caisse balances: "-$200,00".
8. 404/500 pages and every page footer now fit 390 px.
9. Header and the Phases / Personnel / Matériaux button rows wrap.

All 27 pages checked fit a 390 px screen after the fixes.
