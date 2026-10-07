# `materials`

The `materials` app owns the shared Material catalog and the "état de besoin"
(material request) workflow: a Site requests a list of materials, a magasinier
checks it against actual need, a director-tier user gives final authorization,
and — if the request carries a positive estimated cost — that authorization
automatically books a matching `finance.Expense`, already approved, so the
promised spend is never just a number sitting on the request. It is the
primary feed into `procurement`'s stock/purchasing side: a request's items
reference the same `Material` catalog that `procurement.StockItem` optionally
links to, but `materials` itself does not touch stock quantities — that only
happens once a purchase order is raised and received (see
[`procurement.md`](procurement.md)).

## Models

### `Material`
A shared, cabinet-agnostic catalog entry — **no `cabinet` FK on purpose**,
matching how `procurement.StockItem` and the quick-create pickers already
treat it as one system-wide list rather than a per-tenant one.

| Field | Notes |
|---|---|
| `name`, `unit` | e.g. "Ciment", "kg" |
| `estimated_cost_per_unit` | nullable — a catalog entry can exist with no price yet |

No notable methods beyond `__str__`.

### `MaterialRequest`
An état de besoin raised against a `projects.Site`.

| Field | Notes |
|---|---|
| `site` | FK to `projects.Site`, cascade |
| `requested_by` | FK to the user, `SET_NULL` — always set to the creating user by the view |
| `status` | `MaterialRequestStatus` (see state machine below) |
| `expense` | nullable `OneToOneField` to `finance.Expense` — populated only on `authorize()`, and only when there's a positive estimated cost |
| `overage_justification` | **(added 2026-10-07)** `TextField`, blank by default — a dedicated field, **not** a reuse of the generic `notes` param passed to `StatusChangeLog`; see `authorize()` below |

Notable methods:
- `magasinier_validate(user, notes='')` — stage 1: `PENDING → VALIDATED`.
- `authorize(user, notes='', overage_justification='')` **(signature changed
  2026-10-07)** — stage 2: `VALIDATED → APPROVED`; also creates and links
  the `finance.Expense` via `_create_linked_expense()` when there's a
  positive `total_estimated_cost`. **New in this pass**: before approving,
  checks `pricing.services.has_red_variance(self)` — if any item on this
  request compares `RED` against its étape's devis baseline (see
  [`pricing.md`](pricing.md#comparison-engine-pricingservicespy-added-2026-10-07)),
  a blank `overage_justification` raises `ValidationError` and the request
  is **not** approved. This mirrors the existing Chef de Corps /
  `ConventionAvenant` / `PayrollListItem.overage_note` "soft-overage"
  pattern already used elsewhere in the codebase: the system doesn't block
  the overage outright, it forces the approver to write down why before it
  goes through. On success, `overage_justification` (stripped) is saved
  alongside `status`/`updated_at` in the same `save(update_fields=...)`
  call — but only when the request actually `is_overage`; a non-red
  approval never touches the field, even if a stray value was POSTed.
- `reject(user, notes='')` — from `PENDING` or `VALIDATED` → `REJECTED`.
  **Never requires `overage_justification`**, red variance or not — only
  `authorize()` (final approval) is gated, since a request can simply be
  rejected instead of justified.
- `total_items` / `total_estimated_cost` — properties, computed from `items`.
- `clean()` — requires at least one item, but only once the request already
  has a `pk` (a brand-new request is always saved before its items exist).

### `MaterialRequestItem`
A line on a request. `material` (catalog FK, nullable) and `material_name`
(free text) are **mutually exclusive — exactly one must be set** (enforced in
`clean()`): a request is not limited to catalog items, so a one-off or
not-yet-registered material can be typed in directly. `unique_together =
('request', 'material')` blocks adding the same catalog material twice to one
request, but never blocks two free-text rows (`material IS NULL` is never
equal to itself in SQL).

| Field | Notes |
|---|---|
| `material` | nullable FK to `Material`, `PROTECT` |
| `material_name` | free text, used when `material` is empty |
| `phase` | **(added 2026-10-07)** FK to `projects.ProjectPhase`, nullable, `SET_NULL` — which étape (or sous-étape) this item's quantity is being requested for; `clean()` requires `phase.site_id == request.site_id` once `request` is set (checked only when both `phase_id` and `request_id` are present, so a brand-new unsaved item is exempt, same shape as other same-site invariants in this codebase). An item with no `phase` set is invisible to the comparison engine — it shows up on the request as normal but is skipped by `material_request_variance_report()` (requires both `material` **and** `phase`). |
| `quantity` | `DecimalField`, must be positive |

Notable methods/properties:
- `display_name` — `material.name` if linked, else `material_name`.
- `estimated_cost` — `0` for a free-text item (no catalog price to multiply).
- `clean()` — enforces the catalog-or-free-text XOR, a positive quantity, and
  (added 2026-10-07) the `phase`-same-site-as-`request` check above.

**Devis & États de besoin comparison** — each item with both a `material`
and a `phase` is checked live against that étape's devis baseline via
`pricing.services.compare_material_usage()`: a debounced badge on the
request form (`request_form.html`) and a static column on the request
detail page (`request_detail.html`, via
`MaterialRequestDetailView.get_context_data()` annotating each prefetched
item with `.variance_comparison`) show GREEN/ORANGE/RED/NOT_BUDGETED. See
[`pricing.md`](pricing.md#comparison-engine-pricingservicespy-added-2026-10-07)
for the full engine, including the cumulative-quantity rollup across
sous-étapes and the cabinet-configurable thresholds.

## State machines / workflows

```text
MaterialRequest:
    PENDING --magasinier_validate()--> VALIDATED --authorize()--> APPROVED --> ORDERED --> DELIVERED (terminal)
       |                                   |
       +----------- reject() --------------+--> REJECTED (terminal)
```

- **`PENDING → VALIDATED`**: `magasinier_validate()`, enforced in the model
  (raises if not `PENDING`). Triggered from the view
  `materials.views.request_validate`, gated by `MAGASINIER_VALIDATE_ROLES =
  ['MAGASINIER', 'DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']`.
- **`VALIDATED → APPROVED`**: `authorize()`, enforced in the model (raises if
  not `VALIDATED`). Triggered from `materials.views.approve_material_request`,
  gated by `chantiermobile.constants.FINAL_AUTHORIZATION_ROLES = ['DIRECTOR',
  'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']`. This step also creates the
  linked `Expense` (pre-`APPROVED`) when `total_estimated_cost > 0`.
- **`PENDING`/`VALIDATED → REJECTED`**: `reject()`, callable from either of
  the two action views above (either stage may reject).
- **`ORDERED`/`DELIVERED`**: present in `MaterialRequestStatus` and in the
  state diagram in `docs/architecture/overview.md`, but — as of this pass —
  there is no model method or view action in `materials` that drives these
  two transitions; they appear to be reserved for a later procurement-linking
  feature rather than something currently reachable from the UI.

Who can create a request at all: **anyone logged in** —
`MaterialRequestCreateView` has no `allowed_roles`/`RoleRequiredMixin`, only
`LoginRequiredMixin`. The `site` field is scoped to the user's own cabinet(s)
in `get_form()`, so a user can only request against a site they belong to,
but any role (including `WORKER`) can raise a request.

## Views & permissions

| View / endpoint | Who | Notes |
|---|---|---|
| `MaterialListView` | any logged-in user | catalog is shared, not cabinet-scoped |
| `MaterialCreateView` / `MaterialUpdateView` | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` | `allowed_roles` via `RoleRequiredMixin` |
| `MaterialQuickCreateView` | any logged-in user (via the picker) | `cabinet_scoped = False` — same shared-catalog rule |
| `MaterialRequestListView` | any logged-in user | cabinet-scoped by hand in `get_queryset()` |
| `MaterialRequestCreateView` | any logged-in user | no role gate at all (see above) |
| `MaterialRequestUpdateView` | the original requester, **or** `DIRECTOR`/`DIRECTEUR_TECHNIQUE`/`DIRECTEUR_GENERAL`/`CHIEF_ENGINEER` | only while still `PENDING` — both checks are in `dispatch()`, not just role-based |
| `MaterialRequestDetailView` | any member of the owning cabinet | `CabinetAccessMixin`, `cabinet_lookup_field='site__cabinet'` |
| `request_validate` (function view) | `MAGASINIER_VALIDATE_ROLES` | `can_act_for_cabinet(request, mat_request.site.cabinet, ...)` |
| `approve_material_request` (function view) | `FINAL_AUTHORIZATION_ROLES` | same pattern |
| `materials_data_api` | any logged-in user | `@login_required` only, no cabinet scoping — but `Material` is a shared catalog, so that's consistent with the rest of the app |

## Business rules & gotchas

- **Two-stage approval now blocks self-administration (fixed 2026-10-06).**
  `MaterialRequest.magasinier_validate()`, `authorize()`, and `reject()` all
  block `self.requested_by_id == user.pk` (bypassable only by a superuser),
  the same guard shape as `finance.Expense.approve()` and
  `finance.Avenant.approve()`/`reject()`. `DIRECTOR`/`DIRECTEUR_TECHNIQUE`/
  `DIRECTEUR_GENERAL` still sit in **both** `MAGASINIER_VALIDATE_ROLES` and
  `FINAL_AUTHORIZATION_ROLES` — that overlap is unchanged and intentional: a
  director-tier user can still validate *and then* authorize *someone else's*
  request end to end, just never their own. Authorization still auto-creates
  an already-`APPROVED` `Expense`, so the guard matters just as much there as
  at the request stage itself.
- A `MaterialRequestItem` can reference `Material` **or** a free-text name,
  never both, never neither (`clean()`) — any code touching `items` directly
  (bulk import, a management command) must preserve that invariant since it's
  not enforced at the DB level beyond the nullable FK.
- `MaterialRequest.clean()`'s "must have at least one item" check only runs
  once the request has a `pk` — a brand-new, unsaved instance is exempt,
  because the creation flow always saves the parent row before the item
  formset exists. Don't rely on `full_clean()` alone to prevent an empty
  request from ever being created; the creation view's formset
  (`min_num=1`, `validate_min=True`) is doing that work too.
- `_create_linked_expense()` is only called when `total_estimated_cost > 0`.
  A request made entirely of free-text (hors catalogue) items has no catalog
  price and therefore no automatic `Expense` — authorization still succeeds,
  but whoever pays has to record that expense by hand. Don't assume every
  `APPROVED` request has an `expense_id`.
- `ORDERED`/`DELIVERED` statuses exist in `MaterialRequestStatus` but nothing
  in this app currently transitions a request into either of them — if you're
  looking for where that happens, it isn't here yet.
- **`overage_justification` only gates `authorize()`, never `reject()`
  (added 2026-10-07).** The "Autoriser"/"Rejeter" actions share one `<form>`
  on `request_detail.html`; the justification `<textarea>` deliberately has
  **no** HTML `required` attribute (it would otherwise also block the
  Reject button via browser validation whenever the field is shown but
  empty) — the mandatory-when-red check is enforced entirely server-side in
  `authorize()`, surfaced through the existing `ValidationError` →
  `messages.error()` pattern this view already uses for every other action
  failure.
- **A material-level `PriceLibraryItem` line and a work-item (ouvrage)
  line that itself consumes the same material both count toward the same
  étape's baseline**, and nothing across `materials`/`pricing` detects the
  overlap if a cabinet accidentally prices the same material both ways on
  one DQE — see the equivalent gotcha in
  [`pricing.md`](pricing.md#business-rules--gotchas).
