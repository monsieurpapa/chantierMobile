# `pricing`

The `pricing` app owns the Bibliothèque de Prix (a cabinet's reusable catalog
of unit prices — labor, materials, equipment, services, and composite work
items) and the DQE (Détail Quantitatif Estimatif) built from it to estimate a
project's total cost before it becomes a `revenue.Devis`. It lets a cabinet
price a new project from its own known rates instead of re-pricing every job
from scratch, and keeps each estimate's line prices as its own snapshot so a
later catalog price change never silently reprices work already quoted.

## Models

### `PriceLibraryItem`
A reusable unit price, scoped to one cabinet.

| Field | Notes |
|---|---|
| `cabinet` | direct FK, cascade |
| `code` | short identifier, e.g. `MO-001`, `MAT-012`; `unique_together = ('cabinet', 'code')` |
| `item_type` | `PriceItemType`: `LABOR` / `MATERIAL` / `EQUIPMENT` / `SERVICE` / `WORK_ITEM` (composite ouvrage) |
| `work_category` | **(added 2026-10-07)** `WorkCategory`: `BETON` / `ACIER` / `COFFRAGE` / `MACONNERIE` / `AUTRE` — required when `item_type == WORK_ITEM`, forbidden otherwise; tells `DQELine.exploded_requirements()` which `MaterialConsumptionRatio` rows to explode this item's quantity through |
| `material` | **(added 2026-10-07)** FK to `materials.Material`, nullable, `SET_NULL` — only meaningful when `item_type == MATERIAL`; lets a direct-material catalog line be compared against état-de-besoin requests without any ratio lookup |
| `unit`, `unit_price` | |
| `is_active` | inactive items are excluded from the DQE line picker (`DQELineForm.__init__`) and from `price_items_data_api` |

`clean()` — `unit_price` must not be negative (zero is fine, e.g. a "fourni
par le client" line); `work_category` required iff `item_type == WORK_ITEM`.
`material` closes what used to be a deliberate gap: this catalog is still
otherwise decoupled from `materials.Material` (a separate, cabinet-scoped
price list vs. that app's shared, cabinet-agnostic material catalog) — the
new FK is the one deliberate bridge, used only for the comparison engine
below.

### `DQE`
A bill of quantities for a project (or phase of one), built from
`PriceLibraryItem`-referencing lines.

| Field | Notes |
|---|---|
| `cabinet` | direct FK, cascade |
| `site` | nullable, `SET_NULL` — a DQE doesn't have to be tied to a site yet |
| `reference` | e.g. `DQE-2025-001`; `unique_together = ('cabinet', 'reference')` |
| `status` | `DQEStatus`: `DRAFT` / `VALIDATED` / `ARCHIVED` — **not state-machine-enforced** (see gotchas) |

`total_amount` (property) — sums `line.line_total` in Python, since
`line_total` is itself a property (not a stored/annotatable column), not a
DB aggregate. `total_lines` (property) — `self.lines.count()`.

### `DQELine`
A single quantified line, priced from a `PriceLibraryItem`.

| Field | Notes |
|---|---|
| `dqe` | cascade |
| `price_item` | `PROTECT` — a catalog item can't be deleted while referenced |
| `phase` | **(added 2026-10-07)** FK to `projects.ProjectPhase`, nullable, `SET_NULL` — ties this line's quantity to a specific étape (or sous-étape) of the site's chantier; `clean()` requires `phase.site_id == dqe.site_id` when both are set. A line with no phase still counts toward the DQE's total but is invisible to the per-étape comparison engine below. |
| `designation` | optional override of the catalog item's designation |
| `quantity`, `unit_price` | `unit_price` is **copied from the catalog at the time the line is added**, then independently editable per estimate |
| `order` | manual sort position |

`clean()` — positive quantity, non-negative `unit_price`; `phase` (if set)
must belong to the same `site` as the DQE. `display_designation` — this
line's override, falling back to the catalog item's. `unit` — always the
catalog item's unit (no per-line override, unlike `designation`/
`unit_price`). `line_total` — `quantity × unit_price`.

`exploded_requirements()` **(added 2026-10-07)** — turns this line's
catalog-level quantity into elementary material quantities, returning
`{material_id: Decimal quantity}`:
- `item_type == MATERIAL` with `price_item.material` set → the line's own
  quantity, keyed directly by that material (no ratio lookup; this is the
  direct-material-line path allowed alongside ouvrage-level lines — see
  gotchas).
- `item_type == WORK_ITEM` with `price_item.work_category` set → looks up
  every `MaterialConsumptionRatio` row matching that `work_category`, scoped
  to this DQE's `cabinet_id` **or** global (`cabinet__isnull=True`), prefers
  the cabinet-specific ratio over the global default when both exist for the
  same material, and multiplies `quantity × ratio.ratio` per material. This
  is the "explosion": e.g. 12 m³ of `BETON` work becomes N sacs de ciment, M
  m³ sable, etc., per the cabinet's (or the global default's) consumption
  ratios.
- Anything else (no `material`/`work_category` set, or any other
  `item_type`) → `{}` — the line simply doesn't participate in material
  comparison.

### `MaterialConsumptionRatio` **(added 2026-10-07)**
How much of an elementary material one unit of a work category consumes —
the ratio catalog that powers `DQELine.exploded_requirements()`.

| Field | Notes |
|---|---|
| `cabinet` | nullable FK — `null` means a **global default** ratio, usable by every cabinet; a non-null value is that cabinet's own override |
| `work_category` | `WorkCategory` — must match a `PriceLibraryItem.work_category` to apply |
| `material` | FK to `materials.Material` |
| `ratio` | `DecimalField(12, 4)` — quantity of `material` per 1 unit of the work item (e.g. "7 sacs de ciment par m³ de béton") |
| `ratio_unit` | free-text unit label for the ratio's numerator (display only) |
| `notes` | optional free text |

`Meta.unique_together = ('cabinet', 'work_category', 'material')` — at most
one ratio per (cabinet-or-global, category, material) combination; see the
global-vs-override precedence gotcha below. `clean()` — `ratio` must be
positive. Seeded with 8 global-default rows (`cabinet=None`) by
`pricing/migrations/0004_seed_material_consumption_ratios.py` covering
`BETON`, `ACIER`, `COFFRAGE`, `MACONNERIE`; a cabinet only needs its own row
when it wants to override one of those defaults (see
`MaterialConsumptionRatioListView`/`CreateView`/`UpdateView` below).

## Comparison engine (`pricing/services.py`) **(added 2026-10-07)**

Compares what a site has actually requested for a material, at a given étape,
against what the accepted devis budgeted for it — the heart of the
"Devis & États de besoin" feature.

- `baseline_quantity(site, phase, material)` — finds the site's accepted
  `Devis` (`status=ACCEPTE`) with a `source_dqe` set, explodes every line of
  that DQE scoped to `phase` and its sous-étapes (see rollup below), and sums
  the requested material's exploded quantity. Returns `Decimal('0')` if there
  is no accepted devis, or none with a `source_dqe`.
- `cumulative_requested_quantity(site, phase, material)` — sums
  `MaterialRequestItem.quantity` for that site/phase-and-descendants/material,
  excluding `REJECTED` items (an optional `exclude_request_item` lets a
  request's own in-progress item be excluded from its own comparison, and
  `additional_quantity` lets the live-badge endpoint simulate "what if this
  row's quantity were X" before the item is even saved).
- `compare_material_usage(site, phase, material, ...)` → `{baseline,
  cumulative_requested, variance_pct, status}`. `status` is a
  `MaterialVarianceStatus`: `NOT_BUDGETED` (nothing budgeted but something
  requested), `GREEN` (nothing requested, or `variance_pct` under the
  cabinet's orange threshold), `ORANGE` (at or above
  `cabinet.material_variance_orange_threshold_pct`), `RED` (at or above
  `cabinet.material_variance_red_threshold_pct`) — thresholds are read live
  off the site's cabinet, not hardcoded (see `accounts.Cabinet` gotcha
  below).
- `material_request_variance_report(material_request)` — one
  `{item, comparison}` row per `MaterialRequestItem` that has **both** a
  `material` and a `phase` set (items missing either are skipped — they have
  nothing to compare against). Drives both the live per-row badge on the
  request form and the static table on the request detail page.
- `has_red_variance(material_request)` — `True` if any row in that report is
  `RED`; gates the mandatory `overage_justification` in
  `MaterialRequest.authorize()` (see `docs/modules/materials.md`).

**Sub-étape rollup**: a top-level étape's comparison automatically includes
its sous-étapes' figures (`_phase_and_descendants()`), since nesting is
capped at exactly one level (`ProjectPhase.clean()`, see
`docs/modules/projects.md`) — there is no need (or ability) to roll up more
than one level. A sous-étape's own comparison, by contrast, is scoped to
itself only — it never looks at its siblings or its parent.

### `structural_quantity_estimate(site)` **(added 2026-10-08)**
Thin wrapper over `Site.total_concrete_volume_m3`/`total_wall_area_m2`/
`estimated_rebar_kg` (see `docs/modules/projects.md`'s `SiteLevel` section) —
returns `{'concrete_m3', 'wall_area_m2', 'rebar_kg'}`, all `Decimal`, 0 when
the site has no `SiteLevel` rows yet. **Advisory only**: it never creates a
`DQELine` by itself. Surfaced by the `pricing:site_structural_estimate` JSON
endpoint and `dqe_form.html`'s "Suggestions structurelles" panel, refetched
whenever the DQE form's `site` picker changes (same AJAX pattern as
`site_dqes_data_api`) — each of its three "+ Ligne" buttons adds a new DQE
line (the same client-side `addNewLine()` the "Ajouter une ligne" button
uses) with the quantity pre-filled; the user still picks the matching
`PriceLibraryItem` (by `work_category` — BETON/MACONNERIE/ACIER) and `phase`
themselves, since neither can be safely inferred from the estimate alone.

## State machines / workflows

```text
DQE.status (DQEStatus): DRAFT -> VALIDATED -> ARCHIVED   (as documented intent)
```

There is **no `clean()` or method enforcing this** anywhere in
`pricing/models.py` — `status` is a plain field on `DQEForm`, editable by
anyone who can reach `DQEUpdateView` (`DIRECTOR`, `DIRECTEUR_TECHNIQUE`,
`DIRECTEUR_GENERAL`, `CHIEF_ENGINEER`), to any value, in any order, with no
check against the current value. Contrast `materials.MaterialRequest` and
`procurement.PurchaseOrder`, which both validate their status transitions in
`clean()`. See the gotcha below.

Who can do what, with no state-machine step in between:
- **Create a DQE** (`DQECreateView`): `DIRECTOR`, `DIRECTEUR_TECHNIQUE`,
  `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` (`allowed_roles`).
- **Edit a DQE and its lines, including flipping `status`**
  (`DQEUpdateView`): same role list, no restriction based on current status.

## Views & permissions

| View / endpoint | Who | Notes |
|---|---|---|
| `PriceLibraryItemListView` / `PriceLibraryItemDetailView` | any member of the cabinet | `CabinetAccessMixin`, default `cabinet_lookup_field = 'cabinet'` (direct FK) |
| `PriceLibraryItemCreateView` / `UpdateView` | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` | `allowed_roles`; create resolves the cabinet via `get_user_cabinet()` or an explicit picker for an ambiguous multi-cabinet user |
| `DQEListView` / `DQEDetailView` | any member of the cabinet | `CabinetAccessMixin` |
| `DQECreateView` / `UpdateView` | same director-tier/`CHIEF_ENGINEER` set | `site` scoped to the user's own cabinet(s) via `_scope_site_queryset` |
| `price_items_data_api` | any authenticated member of the cabinet | fixed 2026-10-06 — see gotcha below |
| `MaterialConsumptionRatioListView` **(added 2026-10-07)** | any member of the cabinet | shows the global-default ratio catalog plus the cabinet's own overrides side by side |
| `MaterialConsumptionRatioCreateView` / `UpdateView` **(added 2026-10-07)** | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` | `PRICING_ADMIN_ROLES`; `CabinetAccessMixin`-gated — a cabinet can only create/edit its **own** override rows (`cabinet` is forced to the acting user's cabinet), never the global-default (`cabinet=None`) rows |
| `CabinetMaterialThresholdSettingsView` **(added 2026-10-07)** | `PRICING_ADMIN_ROLES` | `UpdateView` on `accounts.Cabinet` with a custom `get_object()` resolving the acting user's own cabinet — no `pk` in the URL, so there's no way to reach another cabinet's settings by editing the URL |
| `DevisComplianceReportView` **(added 2026-10-07)** | any member of the cabinet | `DetailView` on `projects.Site`; `CabinetAccessMixin`; shows every (étape, matériau) comparison row for the site's accepted devis plus the list of requests carrying an `overage_justification` |
| `material_usage_comparison_api` **(added 2026-10-07)** | any authenticated member of the cabinet | GET `site`/`phase`/`material`/`quantity`/`exclude_item`; powers the debounced live badge on the material-request form; returns `{ok:False, reason}` rather than an HTTP error for "nothing to compare yet" states (no phase picked, no material picked, etc.) |
| `site_dqes_data_api` **(added 2026-10-07)** | any authenticated member of the cabinet | mirrors `finance`'s site-scoped `*_data` API pattern; feeds `revenue.DevisForm`'s `source_dqe` picker |
| `site_structural_estimate_api` **(added 2026-10-08)** | any authenticated member of the cabinet | GET `site`; same cabinet-scoping as `site_dqes_data_api`; returns `structural_quantity_estimate(site)` as JSON, or zeros for an unknown/foreign site — feeds `dqe_form.html`'s "Suggestions structurelles" panel |

## Business rules & gotchas

- **`price_items_data_api` is now authenticated and cabinet-scoped (fixed
  2026-10-06).** It previously had no `@login_required` decorator and no
  cabinet filter at all, exposing every active item's code, designation,
  unit, and unit price — across every cabinet in the system — to a fully
  anonymous request. It now mirrors `materials.views.materials_data_api`:
  `@login_required`, plus cabinet-scoping (a superuser sees their
  session-active cabinet or everything; a regular user sees only their own
  cabinet(s), via `request.user.approved_cabinet_roles`).
  See `tests/test_pricing_security.py` for the regression coverage.
- **A DQE's `status` has no enforced lifecycle.** Nothing stops setting it
  straight to `ARCHIVED` on creation, flipping an `ARCHIVED` DQE back to
  `DRAFT`, or editing its lines after it's `VALIDATED` — there is no
  equivalent of `MaterialRequest.clean()`'s transition table or
  `PurchaseOrder.clean()`'s `valid_transitions` for `DQEStatus`. If
  downstream code (or a future `revenue.Devis` integration) ever assumes a
  `VALIDATED`/`ARCHIVED` DQE is frozen, that assumption isn't backed by
  anything here today.
- **A `DQELine.unit_price` is a one-time snapshot, not a live reference.**
  Changing a `PriceLibraryItem.unit_price` later does not touch any
  `DQELine` that already copied the old price — this is intentional (so a
  catalog price change doesn't silently reprice a submitted estimate), but
  it also means there is no built-in way to see which DQEs would be affected
  by a catalog repricing, or to bulk-refresh them, short of writing a
  one-off script.
- `price_item` on `DQELine` is `on_delete=PROTECT` — a `PriceLibraryItem`
  referenced by any DQE line can't be deleted outright; deactivating it
  (`is_active=False`) is the only way to retire it from new estimates while
  leaving existing ones intact.
- **Global-default vs. cabinet-override `MaterialConsumptionRatio`
  precedence.** `exploded_requirements()` resolves at most one ratio per
  material: a cabinet-specific row (`cabinet=<this cabinet>`) always wins
  over a global-default row (`cabinet=None`) for the same
  `(work_category, material)` pair; the global row is only used when the
  cabinet hasn't defined its own. There is no per-DQE or per-line override —
  a cabinet-level override changes every DQE's explosion for that cabinet at
  once, retroactively (it is read live at comparison time, not snapshotted
  per line the way `DQELine.unit_price` is).
- **Both ouvrage-level and material-level DQE lines are allowed in the same
  DQE and roll up together.** A DQE mixing a `WORK_ITEM` line ("12 m³ béton",
  exploded via ratios) and a `MATERIAL` line ("50 sacs de ciment
  supplémentaires", counted directly) both contribute to the same material's
  `baseline_quantity` for a given étape — this is deliberate (the simplest
  real-world DQEs mix both styles) but means double-exploding is possible if
  a cabinet accidentally prices the same cement both inside a `BETON` ouvrage
  line and as a separate direct material line for the same étape; nothing in
  `clean()` detects or prevents that overlap today.
- **Cabinet-wide, not per-site or per-project, variance thresholds.**
  `Cabinet.material_variance_orange_threshold_pct` /
  `material_variance_red_threshold_pct` apply to every site and every
  material under that cabinet uniformly; there is no per-material or
  per-chantier override. `Cabinet.clean()` only enforces
  `orange_threshold <= red_threshold` — nothing stops both being set to an
  unreasonably low or high value (e.g. `0`, which would flag every nonzero
  request as `RED`).
  Changing them is retroactive in the same sense as the ratio catalog: it's
  read live by `compare_material_usage()`, so editing a cabinet's thresholds
  immediately changes the color of every existing comparison, past and
  present — there is no history of what a request's status was *at the time*
  it was authorized.
- **One-level sous-étape nesting only, enforced in `ProjectPhase.clean()`,
  not here.** The comparison engine's `_phase_and_descendants()` assumes this
  invariant (it only ever looks one level down via `sub_phases`, never
  recurses) — see `docs/modules/projects.md` for where that cap is actually
  enforced.
- **`DQELine.exploded_requirements()` and the comparison functions in
  `pricing/services.py` are plain Python loops, not DB aggregates.** For a
  DQE or site with many lines/requests this means N+1-shaped queries
  (`select_related`/`prefetch_related` are used where straightforward, but
  the ratio resolution and summation happen in Python); fine at current
  per-chantier data volumes, worth revisiting with `annotate()`/`Sum()` if a
  cabinet's DQEs grow very large.
