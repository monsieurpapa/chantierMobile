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

### ProjectPhase
- `site`, `name`, `start_date`, `end_date`, `status`
  (`chantiermobile.constants.PhaseStatus`), `closed_by`, `closed_at`,
  `closure_notes`.
- `is_closed` — `status == CLOTUREE`.
- `close(user, notes)` — EN_COURS→CLOTUREE, stamps `closed_by`/`closed_at`,
  writes a `StatusChangeLog` entry. Raises if already closed. **Who may
  call it is enforced entirely in the view** (`projects.views.phase_close`),
  not here — see gotchas.

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

- **`SiteProgressCreateView` has no cabinet scoping at all — a likely
  tenant-isolation gap, and the most significant finding of this pass.**
  Every sibling create view in this app (`ProjectPhaseCreateView`,
  `PlanningSubmissionCreateView`) overrides `RoleRequiredMixin.
  get_role_cabinet()` to scope the role check to the target site's own
  cabinet. `SiteProgressCreateView` does not: it has no
  `get_role_cabinet()` override and isn't mixed with `CabinetAccessMixin`,
  so `RoleRequiredMixin` only checks "does this user hold DIRECTOR/
  DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER in *any*
  cabinet they belong to" — not in the phase's own cabinet. Worse, the
  `phase` the report attaches to is fetched with a bare
  `get_object_or_404(ProjectPhase, unique_id=...)`, with no cabinet filter,
  and `form_valid()` assigns `form.instance.phase = self.phase` directly
  (phase isn't even a form field, so there's no queryset-based guard
  either). **Net effect: a user who holds e.g. ENGINEER in their own
  Cabinet A can file a progress report — with attached photos — against a
  phase belonging to an unrelated Cabinet B**, as long as they know or
  guess that phase's `unique_id` (a UUID in the URL — not trivially
  guessable, but also not secret: it can leak via a shared link, a log
  line, or a notification). This looks like an oversight rather than an
  intentional cross-cabinet allowance.
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
