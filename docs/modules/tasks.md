# `tasks`

`tasks` owns a single, deliberately simple model — `Task` — for granular,
assignable work items on a `Site`. It's the fine-grained counterpart to
`projects.SiteProgress`'s coarse %-complete reporting: a phase's progress
report says "60% done", while its tasks say exactly which pieces of work
make up that 60%.

## Models

### Task
- `site` (required), `phase` (optional — a task can belong to the site
  generally, not one specific phase), `title`, `description`, `status`
  (`chantiermobile.constants.TaskStatus`), `priority` (`TaskPriority`:
  Basse/Normale/Haute/Urgente), `due_date`, `assigned_to` (optional FK to
  `personnel.Personnel` — any type, including Tâcherons and Prestataires),
  `completed_at`.
- `clean()` — three guards: `assigned_to` must belong to the same cabinet
  as `site` (no cross-tenant assignment); a selected `phase` must belong
  to the same `site`; and status changes must follow the transition table
  below. Enforced here (not only in one view) per the project-wide rule in
  [`architecture/overview.md`](../architecture/overview.md#status-state-machines).
- `is_overdue` — false for a completed task or one with no `due_date`;
  true only for a still-open task past its due date.
- `_transition(new_status, ...)` — shared path for every state change:
  stamps/clears `completed_at`, runs `full_clean()` (so `clean()`'s
  transition check actually fires), writes a `StatusChangeLog` entry.
- `start()`, `complete()`, `block(reason)`, `reopen()` — thin wrappers over
  `_transition`, one per edge in the diagram below.

## State machines / workflows

```text
Task:  A_FAIRE  → EN_COURS → TERMINEE
       A_FAIRE  → BLOQUEE
       EN_COURS → BLOQUEE
       EN_COURS → A_FAIRE
       BLOQUEE  → A_FAIRE
       BLOQUEE  → EN_COURS
       TERMINEE → A_FAIRE
       TERMINEE → EN_COURS
```

No single terminal state — any status can be revisited from most others
(this models real field work, where a "done" task sometimes needs rework).
Enforced in `Task.clean()`'s transition table, invoked via `full_clean()`
inside `_transition()`. All four transitions are gated the same way at the
view layer: `MANAGE_ROLES` (DIRECTOR/DIRECTEUR_TECHNIQUE/
DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER) **or** the task's own assignee
acting as themselves — see `_can_manage_task` below.

## Views & permissions

All in `tasks/views.py`.

- **`_can_manage_task(user, task)`** — the shared authorization check used
  by every mutating view/action below: true for a superuser, true for
  `MANAGE_ROLES` within `task.site.cabinet`
  (`UserCabinetRole.objects.filter(...)`), or true when `task.assigned_to`
  is linked to a `user` account matching the requester (self-service for a
  tâcheron/prestataire with a login, so they can update their own task's
  status without any cabinet role at all).
- **`TaskListView`** — cabinet-scoped by default; `?mine=1` switches to the
  requester's own assigned tasks (via their linked `Personnel`), which
  deliberately bypasses the cabinet-role filter entirely so a
  no-cabinet-role worker still sees their list.
- **`TaskCreateView`** — gated to `MANAGE_ROLES`, but that check is **not**
  cabinet-scoped (`RoleRequiredMixin` with no `get_role_cabinet()`
  override) — see gotchas. Actual tenant isolation comes from
  `_scope_form_querysets` narrowing the `site`/`phase`/`assigned_to` form
  fields to the requester's own cabinet(s).
- **`TaskUpdateView`** — same `MANAGE_ROLES` gate, but the object itself is
  cabinet-scoped via `CabinetAccessMixin` (`cabinet_lookup_field =
  'site__cabinet'`), so a cross-cabinet task 404s before the unscoped role
  check would matter.
- **`TaskDetailView`** — open to any cabinet member; `can_manage` (drives
  the "Modifier" action and the start/complete/block/reopen buttons in the
  template) comes from `_can_manage_task`.
- **`task_start`/`task_complete`/`task_block`/`task_reopen`** — function
  views, each gated by `_can_manage_task`, each wrapping the matching
  `Task` method.

## Business rules & gotchas

- **`TaskCreateView`'s role check isn't cabinet-scoped — only its form
  querysets are.** `MANAGE_ROLES` is checked via plain `RoleRequiredMixin`
  with no `get_role_cabinet()` override, so the check is really "does this
  user hold one of these roles *somewhere*", not "...in the cabinet they're
  about to create a task in". The only thing actually preventing a
  cross-cabinet task is `_scope_form_querysets` restricting the `site`
  field's choices to the user's own cabinet(s) — since Django validates a
  `ModelChoiceField` submission against its queryset, a tampered POST with
  a foreign `site` id still fails. This holds today, but it's a more
  fragile guarantee than the explicit cabinet check `TaskUpdateView` gets
  "for free" from `CabinetAccessMixin` — if `_scope_form_querysets` is ever
  skipped or refactored, there is no second check standing behind it.
- **Self-service only covers status transitions, not editing.** A
  tâcheron/prestataire can start/complete/block/reopen their own assigned
  task via `_can_manage_task`'s assignee branch, but `TaskUpdateView`
  itself (retitling, reassigning, changing due date) is still gated by
  `MANAGE_ROLES` alone — the assignee can't edit their own task's details,
  only its status.
- **A task's `assigned_to` can be any `Personnel`, including a Tâcheron or
  Prestataire** — `Task.clean()` only checks the cabinet match, not
  `personnel.is_eligible`, so a task can be (re)assigned to personnel whose
  `status` isn't ACTIF. Compare with `personnel.SiteAssignment.clean()`,
  which does block assigning an ineligible person to a site.
