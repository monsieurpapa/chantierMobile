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
| `unit`, `unit_price` | |
| `is_active` | inactive items are excluded from the DQE line picker (`DQELineForm.__init__`) and from `price_items_data_api` |

`clean()` — `unit_price` must not be negative (zero is fine, e.g. a "fourni
par le client" line). No relationship to `materials.Material` — this is a
separate, cabinet-scoped price catalog, distinct from `materials`' shared,
cabinet-agnostic material catalog.

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
| `designation` | optional override of the catalog item's designation |
| `quantity`, `unit_price` | `unit_price` is **copied from the catalog at the time the line is added**, then independently editable per estimate |
| `order` | manual sort position |

`clean()` — positive quantity, non-negative `unit_price`. `display_designation`
— this line's override, falling back to the catalog item's. `unit` — always
the catalog item's unit (no per-line override, unlike `designation`/
`unit_price`). `line_total` — `quantity × unit_price`.

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
| `price_items_data_api` | **anyone, including anonymous requests** | see gotcha below — this is the one outlier in the app |

## Business rules & gotchas

- **`price_items_data_api` leaks every cabinet's price catalog to anyone,
  logged in or not.** Unlike `materials.views.materials_data_api` (which it
  otherwise mirrors), this view has **no `@login_required`** decorator, and
  there's no project-wide login-required middleware to fall back on
  (`chantiermobile/settings.py`'s `MIDDLEWARE` has none). It also queries
  `PriceLibraryItem.objects.filter(is_active=True)` with **no cabinet
  filter at all**, unlike every other view in this app (all of which go
  through `CabinetAccessMixin` or an explicit `cabinet_roles` filter).
  `PriceLibraryItem` is cabinet-scoped, commercially sensitive data — a
  cabinet's own negotiated unit rates — so this single JSON endpoint exposes
  every active item's code, designation, unit, and unit price, across every
  cabinet in the system, to a fully anonymous request. This is both an
  authentication gap and a tenant-isolation gap, and it's the kind of thing
  worth fixing before this app is used by more than one cabinet in the same
  deployment.
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
