# `projects`

`projects` owns the chantier itself: `Site`, the tenancy anchor almost every
other app's records hang off (directly, like `finance.Budget`/`personnel.
SiteAssignment`, or indirectly through a site, like `finance.Expense`/
`tasks.Task`). It also owns the site's internal structure (`ProjectPhase`),
the engineer-facing planning-review loop (`PlanningSubmission`), and the
day-to-day advancement-reporting loop (`SiteProgress` + `ProgressPhoto` +
`ProgressComment`). See
[`architecture/overview.md`](../architecture/overview.md) for how `Site`
anchors the Cabinet multi-tenancy model.

## Models

### Site
- `cabinet` (owning tenant), `name`, `location`, `status`
  (`chantiermobile.constants.SiteStatus`), `start_date`, `expected_end_date`,
  `lead_engineer` (optional FK to a user — the site's own engineer, who gets
  extra authority elsewhere in the system; see gotchas).
- `contract_mode` (`chantiermobile.constants.ContractMode`, added
  2026-10-07; default `CLE_EN_MAIN`) — the contract type signed with the
  client (clé en main, main d'œuvre seulement, livraison étape par étape,
  suivi de chantier seulement). Pre-established at site creation
  (required field, `SiteForm`) and determines which of the Personnel/
  Materials/Finance tabs on `site_detail.html` are available — see
  `get_enabled_modules()`/`has_module()` below. Changeable later by a
  director/CHIEF_ENGINEER (`SiteUpdateView`) — never locked permanently;
  changing it only toggles which tabs are shown, it never deletes any
  underlying data, so switching back restores full visibility of
  whatever was already there.
- `get_enabled_modules()` — looks up `CONTRACT_MODE_MODULES[contract_mode]`
  (a `dict` of `ContractMode` → `set` of `'personnel'`/`'materials'`/
  `'finance'` module keys, in `chantiermobile/constants.py`); falls back to
  the fullest set (`{'personnel', 'materials', 'finance'}`) for an
  unrecognized mode ("fail open", not "fail hidden" — a future mode added
  to the enum but not yet to the dict shows everything rather than
  nothing). `has_module(name)` — `name in get_enabled_modules()`.
  `SiteDetailView` passes `enabled_modules` into the template context;
  `site_detail.html` wraps each tab's nav `<li>` and pane content in
  `{% if 'X' in enabled_modules %}`.
- `delete()` — soft-deletes the site **and cascades** to every owned child
  record (expenses, material requests, phases + their progress reports/
  photos/comments, assignments, planning submissions, budget, contract +
  its invoices/payments). Not a shortcut: this is a deliberately explicit,
  hand-maintained list of what "belongs to" a site.
- `clean()` — enforces the status transition table below; editing a site
  without changing `status` (e.g. just reassigning `lead_engineer`) is
  never blocked by this check.
- `active_assignments` — this site's `SiteAssignment`s covering today.
- `total_daily_personnel_cost` — sum of `daily_rate` across
  `active_assignments` (today's burn rate, not cumulative).
- `total_spent` — cumulative APPROVED+PAID `finance.Expense` amounts.
- `budget_usage_percentage` — `total_spent` / `budget.total_amount`, capped
  at 100; 0 when the site has no `Budget` row yet.
- `total_revenue` — cumulative PAID `revenue.Invoice` amounts via the
  site's optional one-to-one `Contract`; 0 with no contract.
- `net_profit` — `total_revenue - total_spent` (a running figure, not a
  final project margin — neither side counts pending money).
- **(added 2026-10-08, floors/structure feature)** `floor_count` (R+N,
  default 0), `basement_count` (default 0), `footprint_area_m2` (optional —
  falls back for a `SiteLevel`'s own `floor_area_m2` when left blank there),
  `structure_type` (`chantiermobile.constants.StructureType` —
  poteaux-poutres / maçonnerie portante / mixte; indicative only, doesn't
  gate any field). `SiteForm` makes all three non-required with a
  fallback-to-existing-value `clean_<field>()` (same pattern as
  `contract_mode`) so a POST that omits one doesn't silently reset a
  site's floor count and wipe its levels.
- `sync_levels()` **(added 2026-10-08)** — called by `SiteCreateView`/
  `SiteUpdateView.form_valid()` after every save. Creates/restores/removes
  `SiteLevel` rows so they exactly match `floor_count`/`basement_count`
  (0=RDC, 1..floor_count=R+1..R+N, -1..-basement_count=Sous-sol 1..N). A
  level outside the new range is soft-deleted, not hard-deleted — raising
  the count back later restores the same row (via `SiteLevel.all_objects`)
  rather than creating a blank one.
- `total_concrete_volume_m3` / `total_wall_area_m2` / `estimated_rebar_kg`
  **(added 2026-10-08)** — sum of every level's own `concrete_volume_m3`/
  `wall_area_m2`, and `total_concrete_volume_m3 × cabinet.
  rebar_density_kg_per_m3`, respectively. Feed
  `pricing.services.structural_quantity_estimate()` (see
  [`pricing.md`](pricing.md)) and the "Structure du chantier" card on
  `site_detail.html`.

### SiteLevel **(added 2026-10-08)**
One physical floor of a Site's building (RDC, R+1, R+2..., or a negative
`level_index` for a sous-sol) — see the floors/structure feature. Rows are
entirely managed by `Site.sync_levels()`; there is no create/delete form —
changing `floor_count`/`basement_count` on the Site form and saving is the
only way to add or remove one. `unique_together = ('site', 'level_index')`.

Fields are deliberately *aggregated* per level, not member-by-member (one
total beam length and a typical section, not each beam individually) — a
quick avant-métré, not a full structural member schedule:
- `height_m`, `floor_area_m2` (blank falls back to `Site.footprint_area_m2`
  — see `effective_floor_area_m2`), `wall_length_m` (périmètre + refends),
  `opening_area_m2` (portes/fenêtres, deducted from wall area).
- `beam_count`, `beam_section_width_m`/`beam_section_height_m`,
  `beam_total_length_m` (sum of every beam's span on this level, **not** one
  beam's length) — `beam_volume_m3` = length × width × height.
- `column_count`, `column_section_width_m`/`column_section_depth_m` —
  `column_volume_m3` = count × `height_m` × width × depth (a column is
  assumed to run the full level height).
- `slab_thickness_m` — this level's dalle haute (the floor above, or the
  toiture-terrasse for the top level); `slab_volume_m3` =
  `effective_floor_area_m2` × thickness.
- `concrete_volume_m3` = beams + columns + slab. `wall_area_m2` =
  `wall_length_m × height_m − opening_area_m2` (floored at 0; `None`, not
  0, when `wall_length_m`/`height_m` aren't filled in yet — "not entered"
  and "zero wall" are different facts).
- `label` — `"Rez-de-chaussée (RDC)"` / `"R+N"` / `"Sous-sol N"` from
  `level_index`.

Edited via `SiteStructureUpdateView` (`projects:site_structure_update`,
`site_structure_form.html`) — a plain `modelformset_factory(extra=0,
can_delete=False)`, since the row count is fixed by `sync_levels()`, not
user-adjustable from this page. Gate: director-tier/`CHIEF_ENGINEER`, **or**
the site's own `lead_engineer` (`_site_structure_can_act`, mirrors
`personnel.views._attendance_can_act`) — the engineer who actually took the
on-site measurements should be able to fill this in without a management
role. The form's JS recomputes each level's concrete/wall totals live as
the engineer types (pure client-side arithmetic — no AJAX needed, since the
row count never changes on this page).

### ProjectPhase
- `site`, `name`, `start_date`, `end_date`, `status`
  (`chantiermobile.constants.PhaseStatus`), `closed_by`, `closed_at`,
  `closure_notes`.
- `parent_phase` **(added 2026-10-07)** — self-FK, nullable, `SET_NULL`,
  `related_name='sub_phases'`. Lets an étape have sous-étapes — but **only
  one level deep**: `clean()` rejects setting `parent_phase` to self, rejects
  a `parent_phase` on a different `site`, and (the actual nesting cap)
  rejects a `parent_phase` that **itself already has a `parent_phase`** — a
  sous-étape can never itself have sous-étapes. This single-level
  invariant is what the `pricing` comparison engine's
  `_phase_and_descendants()` rollup relies on (it only ever looks one
  `sub_phases` lookup deep, never recurses) — see
  [`pricing.md`](pricing.md#comparison-engine-pricingservicespy-added-2026-10-07).
- `is_sub_phase` **(added 2026-10-07)** — `parent_phase_id is not None`.
  `top_level_phase` **(added 2026-10-07)** — `self.parent_phase` if a
  sub-phase, else `self`. `__str__` renders a sub-phase as
  `"{site} - {parent.name} > {name}"` so it reads unambiguously in any
  dropdown/log line that just calls `str()` on a phase.
- `is_closed` — `status == CLOTUREE`.
- `close(user, notes)` — EN_COURS→CLOTUREE, stamps `closed_by`/`closed_at`,
  writes a `StatusChangeLog` entry. Raises if already closed. **Who may
  call it is enforced entirely in the view** (`projects.views.phase_close`),
  not here — see gotchas. Closing a top-level phase does **not** cascade to
  or require closing its sous-étapes first, and vice versa — each phase's
  `status` is independent of its parent's/children's.

### PlanningSubmission
The engineer self-service planning flow: "Soumettre la planification aux
ingénieurs concernés". `site`, optional `phase`, `description`, `status`
(`chantiermobile.constants.PlanningStatus`), `submitted_by`/`submitted_at`,
`reviewed_by`/`reviewed_at`/`review_notes`.
- `submit(user)` — BROUILLON→SOUMISE.
- `_decide(user, new_status, notes)` — shared approve/reject path. Only a
  SOUMISE submission can be decided, and **blocks the submitter from
  deciding their own submission** (mirrors `Expense.approve()`'s
  self-approval guard) — but does **not** check that `user` is this site's
  `lead_engineer`; see gotchas.
- `approve(user, notes)` / `reject(user, notes)` — thin wrappers over
  `_decide`.

### SiteProgress
A dated %-complete + free-text report against one `ProjectPhase` — the
coarse day-to-day counterpart to `tasks.Task`'s granular tracking.
- `report_date`, `percentage_complete` (0-100, see `clean()`), `description`.
- `clean()` — keeps `percentage_complete` within
  `ProjectConfig.MIN_PROGRESS`/`MAX_PROGRESS`.

### ProgressPhoto
A photo attached to a `SiteProgress` (`progress`, `image`, `uploaded_by`).
Addable any time after the report is filed, not only when it's first
created — follow-up evidence often arrives over the following days.

### ProgressComment
A comment on a `SiteProgress`, or — when `photo` is set — on one specific
photo within it. `progress`, optional `photo`, `author`, `body`.
- `clean()` — a photo-scoped comment's `photo` must belong to the same
  `progress` it's attached to.
- Deliberately **open to anyone with cabinet access**, not just the roles
  that can file reports/photos — a shared discussion thread, not an
  engineer-only channel.

## State machines / workflows

```text
Site:               PLANNING → ACTIVE ↔ PAUSED → COMPLETED (terminal)
                              ↘ CANCELLED (from any non-terminal) (terminal)
  Enforced in Site.clean(); transitions happen through SiteUpdateView
  (DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER).

ProjectPhase:        EN_COURS → CLOTUREE (terminal)
  Enforced by ProjectPhase.close()'s own is_closed guard (not a full
  transition table — there's only one non-terminal state to leave).
  Who can call close(): PHASE_CLOSE_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
  DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER), checked in the
  `phase_close` view via can_act_for_cabinet(site.cabinet, ...) — cabinet-
  scoped only, not restricted to the site's own lead_engineer (gotcha).

PlanningSubmission:  BROUILLON → SOUMISE → APPROUVEE (terminal)
                                         → REJETEE   (terminal)
  Submit: PlanningSubmissionCreateView, PLANNING_SUBMIT_ROLES (DIRECTOR/
          DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER),
          scoped to the site's cabinet via get_role_cabinet(); creates as
          BROUILLON then immediately calls submit() in the same request.
  Decide: planning_submission_approve/reject, PLANNING_REVIEW_ROLES (same
          five roles), can_act_for_cabinet(site.cabinet, ...) plus
          PlanningSubmission._decide()'s self-review guard. Cabinet-scoped
          only, not restricted to the site's own lead_engineer (gotcha).
```

## Views & permissions

All in `projects/views.py`.

**Sites** — `SiteListView`/`SiteDetailView` open to any authenticated
cabinet member (`CabinetAccessMixin`); `SiteCreateView`/`SiteUpdateView`
gated to DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER;
`SiteDeleteView` narrowed to director-tier only (no CHIEF_ENGINEER).

`SiteDetailView`'s "Matériaux" tab (`site_detail.html`) shows two
separate things, both scoped to this site: each `MaterialRequest`'s own
line items (`req.items.all` — fixed 2026-10-06; it previously read
`req.material`/`req.quantity` directly, fields that don't exist on
`MaterialRequest` itself, only on its related `items`, so every row
silently rendered blank), and, since 2026-10-06, the
`finance.CaisseTransactionMaterialLine` rows recorded against an "Achat
matériaux" mouvement on this site (`context['material_purchase_lines']`,
built in `SiteDetailView.get_context_data()`) — see
`docs/modules/finance.md`'s `CaisseTransactionMaterialLine` section. This
second list is a financial record only; it is **not** the site's actual
stock-on-hand. A "Historique des mouvements de stock" link next to the
tab's header (gated the same as `procurement.STOCK_REPORT_ROLES`) sends
the technical team to the existing `procurement:stock_report`, pre-filtered
to this site, for that.

**Phases** — `ProjectPhaseCreateView`/`UpdateView`/`DeleteView` gated to
DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER, scoped to the
phase's own site's cabinet via `get_role_cabinet()`. `phase_close` (function
view) gated to `PHASE_CLOSE_ROLES` (adds ENGINEER) via `can_act_for_cabinet`.

**Progress** — `SiteProgressCreateView` gated to DIRECTOR/
DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER — **but see
the gotcha below: this check is not cabinet-scoped at all.**
`ProgressDetailView` cabinet-scoped (any member can view).
`progress_photo_add` gated to `PROGRESS_PHOTO_ROLES` via
`can_act_for_cabinet`. `progress_comment_add` only requires
`can_view_cabinet` (any role in the cabinet) — deliberately looser, see the
model's own docstring.

**Planning submissions** — `PlanningSubmissionCreateView` gated to
`PLANNING_SUBMIT_ROLES`, scoped to the target site's cabinet via
`get_role_cabinet()`. `planning_submission_approve`/`_reject` gated to
`PLANNING_REVIEW_ROLES` via `can_act_for_cabinet`, plus the model's
self-review guard.

## Business rules & gotchas

- **`SiteProgressCreateView` is now cabinet-scoped (fixed 2026-10-06).** It
  previously had no `get_role_cabinet()` override and looked up its `phase`
  with a bare `get_object_or_404(ProjectPhase, unique_id=...)` — no cabinet
  filter at all — so a user who held e.g. ENGINEER in their own Cabinet A
  could file a progress report, with attached photos, against a phase
  belonging to an unrelated Cabinet B if they knew/guessed its `unique_id`.
  It now mirrors its siblings (`ProjectPhaseCreateView`,
  `PlanningSubmissionCreateView`): the phase lookup goes through a
  cabinet-scoped `_phase_queryset()` (same superuser/session-cabinet
  convention as `CabinetAccessMixin`), and `get_role_cabinet()` returns
  `self.phase.site.cabinet`. See `tests/test_progress_photos_comments.py`
  for the regression coverage.
- **"Own site only" for an ENGINEER is enforced inconsistently across
  this app.** `PHASE_CLOSE_ROLES`, `PLANNING_SUBMIT_ROLES` and
  `PLANNING_REVIEW_ROLES` all include `ENGINEER`, but the views that check
  them (`phase_close`, `PlanningSubmissionCreateView`,
  `planning_submission_approve`/`_reject`) only call
  `can_act_for_cabinet(request, site.cabinet, roles)` — i.e. "does this
  user hold one of these roles *anywhere in the site's cabinet*", not
  "...and are they this specific site's `lead_engineer`". The only
  additional guard is `PlanningSubmission._decide()`'s self-review check
  (can't approve/reject your own submission) — there's no check that the
  reviewer is the site's own lead engineer either. In practice, **any**
  ENGINEER in the cabinet can close **any** site's phase, or submit/review
  **any** other site's planning, not just one they lead.
  [`docs/security.md`](../security.md#representative-permission-matrix)
  currently documents this row as "ENGINEER (own site only)" — the code
  doesn't actually enforce the "own site" part. Contrast with
  `personnel/views.py`, where the equivalent restriction (assigning
  personnel, declaring leave, recording attendance) is enforced explicitly
  via `site.lead_engineer_id == request.user.pk` — this app's planning/
  phase views don't have that check.
- **`Site.delete()`'s cascade is a hand-maintained list.** A new child
  model added under `Site` in the future (directly or via `ProjectPhase`)
  needs its own line added here, or it will survive a "deleted" site's
  soft-delete untouched while every sibling record disappears.
- **A site with no `Budget` row has `budget_usage_percentage == 0` and no
  spending cap enforced anywhere** (see `finance`'s module doc) — this is
  intentional (budgets are opt-in), but it means an unbudgeted active site
  looks indistinguishable from a healthy one on the dashboard's
  budget-usage widget.
- **`total_revenue`/`net_profit` only count money that has actually
  moved** (PAID invoices, APPROVED+PAID expenses) — they are not a
  forecast and will understate a site's eventual margin while invoices are
  still SENT/OVERDUE or expenses still PENDING.
- **`parent_phase` is now actually reachable from the UI (fixed
  2026-10-07, same pass that added the field).** The field shipped in a
  migration without ever being added to `ProjectPhaseForm` or
  `phase_form.html` — there was a model-level sous-étape concept with no
  way for any user to create one. `ProjectPhaseForm` now takes a `site=`
  kwarg and exposes a `parent_phase` picker scoped to that site's
  top-level phases (excluding the phase itself on edit, and excluding
  everything when the phase being edited already has its own sous-étapes
  — see the next gotcha); `phase_form.html` renders it as a plain
  `<select>`, matching the template's existing hand-rolled-field style
  rather than `{{ form.as_p }}`. `ProjectPhaseCreateView`/`UpdateView`
  pass `site=` via `get_form_kwargs()` and also compute the same
  queryset into `top_level_phases` context for the template, since the
  template doesn't render form fields directly.
- **One-level nesting is now enforced from both directions in
  `ProjectPhase.clean()` (fixed 2026-10-07).** The original check only
  looked at the *new parent's* parent (rejecting `grandchild.parent =
  child_of(X)`), but said nothing about a phase that already **has**
  sous-étapes being assigned a parent itself — which would have produced
  the same 2-level nesting from the other direction
  (`Y.parent_phase = X` where `X` already has children). `clean()` now
  also rejects that case (`self.sub_phases.exists()` when
  `self.parent_phase_id` is being set), and `ProjectPhaseForm` pre-empts
  it at the UI layer by emptying the `parent_phase` queryset entirely for
  such a phase, rather than letting the user pick an option that would
  only fail on submit.
