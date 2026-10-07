# `personnel`

`personnel` owns the HR side of a Cabinet: the people (`Personnel`), what
they can do (`Skill`), where they're working (`SiteAssignment`), their
paperwork (`PersonnelDocument`), and their time (`Leave`, `Holiday`,
`Attendance`). `Personnel.payroll_type` is the fork point with `finance`'s
two parallel payroll tracks — see
[ADR 0005](../architecture/decisions/0005-separate-payroll-tracks.md) for
why ouvriers and ingénieurs/staff are paid through entirely separate models
rather than one generic payroll entity.

## Models

### Skill
`name`, `description` — a shared tag (e.g. Maçon, Ferrailleur), **not**
cabinet-scoped (`SkillQuickCreateView.cabinet_scoped = False`).

### Personnel
- `cabinet`, optional one-to-one `user` (login self-service, e.g. a
  tâcheron viewing their own assigned `tasks.Task`s), `first_name`/
  `last_name`, `personnel_type` (`chantiermobile.constants.PersonnelType`:
  Employé/Tâcheron/Prestataire), `skills` (M2M), `default_daily_rate`
  (optional since 2026-10-06 — `null=True, blank=True`; a worker paid
  purely by chantier convention rather than at the journalier has no
  reason to carry one), `monthly_salary` (labeled "Convention" in the
  Personnel form since 2026-10-06 — cosmetic, the field/column itself is
  unchanged), `category` (`AgentCategory`: Terrain/Administration),
  `trade` (`Trade`), `status` (`PersonnelStatus`: Actif/Inactif/Non
  éligible), `payroll_type` (`PersonnelPayrollType`: Ouvrier/Ingénieur —
  see ADR 0005).
- `is_subcontractor` — true for Tâcheron/Prestataire.
- `is_eligible` — `status == ACTIF`; gates new `SiteAssignment`s (see
  `SiteAssignment.clean()`).
- **`payroll_type` is independent of `personnel_type`/`category`** — there
  is no automatic inference between the three; it must be set deliberately
  at creation (see ADR 0005's Consequences section).
- `is_chef_de_corps` (added 2026-10-07) — flags a subcontracting trade
  lead ("chef de corps"): the entreprise contracts with this person per
  `SiteAssignment`/convention rather than with their individual ouvriers,
  who the chef de corps pays himself without Cabinet involvement except in
  a dispute. Drives the `ChefDeCorpsListView` listing and the soft
  convention-overage rule in `finance.PayrollListItem.clean()` (see
  `docs/modules/finance.md`). `Trade` (`chantiermobile/constants.py`) is
  reused as the corps-de-métier lookup — extended 2026-10-07 with
  `CHARPENTIER`/`SOUDEUR` to cover all 7 corps named in the client's spec
  (MACON/FERRAILLEUR/PLOMBIER/ELECTRICIEN/CARRELEUR already existed); the
  list stays open to future trades via the same `TextChoices` pattern.

### SiteAssignment
Links a `Personnel` to a `Site` for a date range at an agreed `daily_rate`
— drives `Site.total_daily_personnel_cost` and the attendance/pointage
crew list (`AttendanceDailyView.get_rows`).
- `role` (free text), `start_date`/`end_date` (open-ended if null),
  `daily_rate`, `agreement_document`/`agreement_notes` (the signed
  convention), `convention_amount` (optional cap for one specific
  task/convention — a worker can hold several concurrent assignments to
  the same site, one per convention).
- `name` and `phase` (FK to `projects.ProjectPhase`, added 2026-10-06):
  a convention entered from the Personnel form's "Chantiers & conventions"
  section (see below) is named by whoever fills the form and tied to a
  chantier étape, rather than to a full role/date-range affectation.
- **`role`/`start_date`/`daily_rate` are optional at the model level**
  (`null=True`/`blank=True`, since 2026-10-06) so that lighter-weight
  convention row can be saved with only `site`/`name`/`phase`/
  `convention_amount` set. `SiteAssignmentForm` — the standalone
  affectation flow (`SiteAssignmentCreateView`) — re-asserts all three as
  form-required in `__init__`, so that flow's behavior is unchanged; only
  `ConventionForm` (`personnel/forms.py`), used by the Personnel form's
  dynamic section, leaves them unset.
- `clean()` — blocks assigning a non-ACTIF personnel record. **Does not**
  check for overlapping date ranges against the same personnel's other
  assignments — double-booking the same person to two sites on the same
  dates is possible (a known, pre-existing limitation, not new).
- `paid_amount` — sum of `PayrollListItem`s booked against this assignment.
- `remaining_convention` — `convention_amount - paid_amount`; `None` when
  no cap is tracked; can go negative if items were entered before a cap
  was added.
- `initial_convention_amount` (added 2026-10-07) — the convention's
  original cap, backfilled automatically the first time a
  `ConventionAvenant` is recorded against this assignment; `None` until
  then. `effective_initial_amount` returns it, falling back to the current
  `convention_amount` when no avenant has ever been recorded (so callers
  don't need to branch on whether one exists).

### ConventionAvenant (added 2026-10-07)
Audit trail of every renegotiation of a `SiteAssignment`'s
`convention_amount` — the client's "avenant sur convention" workflow: a
chef technique announces a renegotiated scope of work (typically a
surplus) to the caissière, who records it here with the date and a
reason. **Not** the same model as `finance.Avenant` (a project-level
budget/contract change-order with its own PENDING/APPROVED/REJECTED
workflow) — the name clash is deliberate-but-scoped: this one tracks a
single convention, not a whole chantier's budget.
- `assignment` (FK to `SiteAssignment`), `date`, `previous_amount`,
  `new_amount`, `reason`, `recorded_by` (the user who recorded it, usually
  CASHIER/ACCOUNTANT/a director).
- `ConventionAvenant.record(assignment, new_amount, reason, user, date=None)`
  — the only way this should be created: a `@transaction.atomic`
  classmethod that creates the audit row **and** updates
  `assignment.convention_amount` to `new_amount` in the same transaction,
  backfilling `initial_convention_amount` from the pre-avenant value the
  first time it's ever called for that assignment. Calling
  `ConventionAvenant.objects.create()` directly would log the change
  without moving the live cap — always go through `.record()`.
- Ordered most-recent-first (`-date`, `-created_at`); `ConventionAvenant
  Form`/`ConventionAvenantCreateView` (`personnel/views.py`) render the
  full history alongside the "new avenant" form so the caissière can see
  the convention's full renegotiation trail before recording another one.
- Gated to `CONVENTION_AVENANT_ROLES` (CASHIER/ACCOUNTANT/director-tier) —
  the chef technique *announces* the avenant verbally/on paper; the
  caissière (or an accountant/director) is who actually records it.

### Chef de Corps overage rule (finance, added 2026-10-07)
A chef de corps's convention can legitimately run ahead of the avenant
that will eventually catch up with it (a renegotiation announced but not
yet recorded). So `PayrollListItem.clean()` lets a payment to a chef de
corps exceed the current `convention_amount` **with a mandatory
`overage_note`** explaining the overage — a soft rule, not a hard block.
Every other personnel record (the default case) keeps the pre-existing
hard block: a payment that would exceed the cap is rejected outright. Every
recorded overage is surfaced to the DG/bureau technique via
`finance.ConventionOverageListView` — see `docs/modules/finance.md`.

### Personnel form's "Chantiers & conventions" section (2026-10-06)
`PersonnelCreateView`/`PersonnelUpdateView` now also render an inline
formset (`ConventionFormSet`, `personnel/forms.py`) letting the person
filling the Personnel form assign the worker to one or more chantiers in
the same submission, each row naming a convention tied to one of that
chantier's étapes (`ProjectPhase`):
- Each row captures `site`, a convention `name`, a `phase`, and an
  optional `convention_amount` — no `role`/dates/`daily_rate` (confirmed
  scope: "name + étape + montant").
- A row can either pick an existing `phase` or type a new étape name
  (`new_phase_name`, not a model field). On save, `ConventionFormSetMixin`
  (`personnel/views.py`) resolves `new_phase_name` via
  `ProjectPhase.objects.get_or_create(site=site, name__iexact=..., ...)`
  — **a duplicate name on the same site reuses the existing étape rather
  than creating a second one** (confirmed scope).
- The formset is entirely additive: a POST that doesn't include its
  management-form fields at all (an older client, a direct API call, any
  caller unaware of this section) is treated as "no conventions
  submitted" rather than erroring — see `ConventionFormSetMixin.
  _formset_submitted()`.
- At payroll disbursement, `finance/templates/finance/
  payroll_list_detail.html` now shows each item's `assignment.name`
  (falling back to `.role`), `.phase.name`, and the convention's cap/
  remaining — see `docs/modules/finance.md`.

### PersonnelDocument
A file in a personnel's "dossier" (ID copy, diploma, contract, medical
certificate). `personnel`, `label`, `file`, `uploaded_at`.

### Holiday
A cabinet-wide public holiday (`cabinet`, `name`, `date`;
`unique_together('cabinet', 'date')`). Applies to everyone — a per-worker
absence is `Leave` instead.

### Leave
A personnel absence (congé). `personnel`, `leave_type` (`LeaveType`),
`start_date`/`end_date`, `reason`, `status` (`ApprovalStatus`: Pending/
Approved/Rejected), `decided_by`/`decided_at`.
- `duration_days` — inclusive day count (a single-day leave is 1, not 0).
- **No model-level `clean()`** validating `end_date >= start_date` — that
  check only exists in `LeaveForm.clean()` (form-level). A `Leave` created
  outside that form (Django admin, shell, a future API/bulk-import path)
  isn't protected against an inverted date range.

### Attendance
Daily pointage: one row per `(personnel, site, date)` recording whether a
worker showed up (`AttendanceStatus`: Présent/Absent/En retard/
Demi-journée). `notes`, `recorded_by`. `unique_together('personnel',
'site', 'date')` — keyed on personnel+site+date rather than the
`SiteAssignment`, so a same-day assignment change doesn't orphan the
record and the same combination can never be recorded twice by accident.
Recently added (item 14 of the Directors/Engineers audit) — there was
previously no attendance tracking at all.

## State machines / workflows

`Leave.status` is the only status field this app owns:

```text
Leave:   PENDING → APPROVED (terminal)
                 → REJECTED (terminal)
  Decide: _decide_leave (leave_approve/leave_reject), HR_ADMIN_ROLES
          (DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CHIEF_ENGINEER)
          only, via can_act_for_cabinet(personnel.cabinet, ...) — a
          cabinet-wide check, not restricted to the requester's own
          lead_engineer. ENGINEER may *create* a leave for their own crew
          (LEAVE_CREATE_ROLES) but is deliberately excluded from deciding
          one, even their own crew's.
```

`SiteAssignment` and `Attendance` have no status field of their own —
`SiteAssignment.clean()`'s eligibility check runs on every save, and
`Attendance` rows are simply created/updated via `update_or_create`
(`AttendanceDailyView.post`), no lifecycle to track.

## Views & permissions

All in `personnel/views.py`. The recurring pattern across this module:
`HR_ADMIN_ROLES` (DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/
CHIEF_ENGINEER — cabinet-wide HR authority) vs. a plain `ENGINEER` scoped
explicitly to **their own crew** — the site(s) where they're
`Site.lead_engineer` — via `_is_hr_admin()` plus an explicit
`lead_engineer` check at each call site. This is the one app in this
pass's scope where that "own site" scoping is actually enforced at the
query/check level, not just at the role-list level (contrast with
`projects`'s planning/phase-close views — see that module's gotchas).

**Personnel** — `PersonnelListView`/`DetailView` open to any cabinet
member; `CreateView`/`UpdateView` gated to HR_ADMIN_ROLES **plus CASHIER**
(an inline role list, not the shared `HR_ADMIN_ROLES` constant — added
2026-10-06, permission table update: a cashier can register and edit
personnel, but this does not extend to Leave/Holiday decisions or Skills,
which still check `HR_ADMIN_ROLES` itself); `DeleteView` narrowed to
director-tier only (no CHIEF_ENGINEER, no CASHIER).

**Skills** — `SkillListView` (list + inline create) gated to
HR_ADMIN_ROLES; not cabinet-scoped (Skill has no cabinet FK).

**Site assignments** — `SiteAssignmentCreateView` gated to
`SITE_ASSIGNMENT_ROLES` (HR_ADMIN_ROLES + ENGINEER); a plain ENGINEER's
`site` field is narrowed to `Site.objects.filter(lead_engineer=user)` in
`get_form()`.

**Dossier** — `PersonnelDocumentCreateView`/`DeleteView` gated to
HR_ADMIN_ROLES, scoped to the document's own personnel's cabinet via
`get_role_cabinet()`.

**Congés** — `LeaveCreateView` gated to `LEAVE_CREATE_ROLES`
(HR_ADMIN_ROLES + ENGINEER; a plain ENGINEER's `personnel` choices
narrowed to their own crew). `_decide_leave` (`leave_approve`/
`leave_reject`) gated to HR_ADMIN_ROLES only — ENGINEER can create but
never decide, even for their own crew.

**Jours fériés** — `HolidayCreateView`/`DeleteView` gated to
HR_ADMIN_ROLES.

**Pointage** — `AttendanceDailyView`/`AttendanceHistoryView` gated by
`_attendance_can_act`: HR_ADMIN_ROLES for any site, or
`site.lead_engineer_id == request.user.pk` for a plain ENGINEER's own
site. Same ownership rule as site-assignment/leave scoping above.

**Chefs de corps** (added 2026-10-07) — `ChefDeCorpsListView` (
`personnel:chef_de_corps_list`, linked from the nav right under
"Personnel") lists every `Personnel` with `is_chef_de_corps=True`, their
trade, and their chantiers/conventions (built on the existing Personnel +
SiteAssignment data, not a parallel table). Open to any authenticated
cabinet member, like the main Personnel list — no extra role gate.
`ConventionAvenantCreateView` (`personnel:convention_avenant_create`,
one per `SiteAssignment`) is gated to `CONVENTION_AVENANT_ROLES`
(CASHIER/ACCOUNTANT/director-tier).

## Business rules & gotchas

- **`SiteAssignment.clean()` doesn't catch overlapping assignments.** The
  same `Personnel` can be assigned to two different sites (or the same
  site twice) over overlapping date ranges — nothing in the model or the
  views rejects it. The comment in `clean()` flags this as deferred to
  "the form/view" for the MVP, but neither actually implements it today.
  This would silently double-count someone's `total_daily_personnel_cost`
  across two sites for the same days.
- **`Leave`'s date-range validity is form-only, not model-level.** Any
  write path that bypasses `LeaveForm` (admin, shell, a future bulk
  endpoint) can save a `Leave` with `end_date < start_date`; `duration_days`
  would then return a negative number silently rather than raising.
- **Attendance/leave records are not independently corroborated** — a
  `recorded_by`/`decided_by` user with the right role can mark a worker
  PRESENT (or approve/reject a leave) for any day, with no secondary
  check against e.g. a site visit log or geolocation. This is inherent to
  a manual pointage system, not a bug, but worth knowing before treating
  `Attendance` as an audit-grade source of truth for payroll disputes.
- **Skill is global, not cabinet-scoped** — a skill added by one cabinet's
  staff is visible and selectable by every other cabinet in the system.
  Intentional (shared taxonomy), but means a cabinet can't maintain a
  private/custom skill list.
- **This app's "own site" ENGINEER scoping is the more carefully-built
  sibling of `projects`'s planning/phase-close checks** — if you're
  extending engineer self-service elsewhere in the app, the pattern here
  (`_is_hr_admin()` + an explicit `site.lead_engineer_id == user.pk`
  check) is the one to copy, not `projects`'s cabinet-only checks.
