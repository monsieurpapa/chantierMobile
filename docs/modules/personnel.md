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
  Employé/Tâcheron/Prestataire), `skills` (M2M), `default_daily_rate`,
  `monthly_salary`, `category` (`AgentCategory`: Terrain/Administration),
  `trade` (`Trade`), `status` (`PersonnelStatus`: Actif/Inactif/Non
  éligible), `payroll_type` (`PersonnelPayrollType`: Ouvrier/Ingénieur —
  see ADR 0005).
- `is_subcontractor` — true for Tâcheron/Prestataire.
- `is_eligible` — `status == ACTIF`; gates new `SiteAssignment`s (see
  `SiteAssignment.clean()`).
- **`payroll_type` is independent of `personnel_type`/`category`** — there
  is no automatic inference between the three; it must be set deliberately
  at creation (see ADR 0005's Consequences section).

### SiteAssignment
Links a `Personnel` to a `Site` for a date range at an agreed `daily_rate`
— drives `Site.total_daily_personnel_cost` and the attendance/pointage
crew list (`AttendanceDailyView.get_rows`).
- `role` (free text), `start_date`/`end_date` (open-ended if null),
  `daily_rate`, `agreement_document`/`agreement_notes` (the signed
  convention), `convention_amount` (optional cap for one specific
  task/convention — a worker can hold several concurrent assignments to
  the same site, one per convention).
- `clean()` — blocks assigning a non-ACTIF personnel record. **Does not**
  check for overlapping date ranges against the same personnel's other
  assignments — double-booking the same person to two sites on the same
  dates is possible (a known, pre-existing limitation, not new).
- `paid_amount` — sum of `PayrollListItem`s booked against this assignment.
- `remaining_convention` — `convention_amount - paid_amount`; `None` when
  no cap is tracked; can go negative if items were entered before a cap
  was added.

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
member; `CreateView`/`UpdateView` gated to HR_ADMIN_ROLES; `DeleteView`
narrowed to director-tier only (no CHIEF_ENGINEER).

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
