# `accounts`

`accounts` owns identity and multi-tenancy: the custom `User` model, the `Cabinet`
tenant boundary that every business model in the system ultimately hangs off, and
`UserCabinetRole` — the single table that *is* the system's entire authorization model.
There is no Django permission/group usage anywhere else in the codebase; every RBAC
check in `core.mixins` and every app's views reads `UserCabinetRole` directly. It also
owns the superuser cabinet-context switcher and its audit log, and the superadmin-only
screens for managing users, cabinets and role assignments.

## Models

### `User` (`accounts/models.py`, `AUTH_USER_MODEL`)

Extends `django.contrib.auth.models.AbstractUser` with:

| Field | Purpose |
|---|---|
| `phone_number` | Optional contact field. |
| `must_change_password` | Forces a redirect to the password-change page on every request (`core.middleware.ForcePasswordChangeMiddleware`) until cleared. Set `True` whenever a temporary password is generated — new-user creation (`UserCreateAdminView`), password reset (`UserResetPasswordAdminView`), and the `bootstrap_admin_and_roles` / `seed_test_data` management commands. Cleared automatically by a signal handler in `AccountsConfig.ready()` once allauth reports the password actually changed. |

Carries no role or Cabinet reference itself — see `UserCabinetRole` below.

### `Cabinet` (`accounts/models.py`)

```
name · address · tax_id (NIF/TIN) · logo
```

The tenancy boundary (see [ADR 0001](../architecture/decisions/0001-cabinet-multi-tenancy.md)
and [`docs/architecture/overview.md`](../architecture/overview.md#multi-tenancy-cabinet)).
Every `Site`, and everything that hangs off a `Site` or directly off a `Cabinet`
(`Personnel`, `Budget`, ...), belongs to exactly one `Cabinet`. A `Cabinet` has no
owner/admin field of its own — who can act on it is entirely determined by
`UserCabinetRole` rows pointing at it, plus superusers, who can act on any Cabinet.

### `UserCabinetRole` (`accounts/models.py`) — the authorization grant

```
user (FK) · cabinet (FK) · role (UserRoles choice) · status (ApprovalStatus choice)
unique_together: (user, cabinet)
```

This one row *is* a user's access to a Cabinet. Every RBAC primitive in `core.mixins`
(`CabinetAccessMixin`, `RoleRequiredMixin`, `can_act_for_cabinet`, `can_view_cabinet`)
and the `has_role` template filter query this table directly — there is no other
permission store, and Django's built-in `is_staff`/permission/group system is not used
for business authorization (only for Django admin access).

- **`role`** — one of `chantiermobile.constants.UserRoles` (`DIRECTOR`,
  `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER`, `ENGINEER`, `FINANCIER`,
  `ACCOUNTANT`, `CASHIER`, `MAGASINIER`, `WORKER`). `unique_together` caps a user at one
  role per Cabinet — changing a user's role in a Cabinet means editing this row, not
  adding a second one.
- **`status`** — `ApprovalStatus` (`PENDING` / `APPROVED` / `REJECTED`), set by a
  superadmin when creating or reviewing an assignment
  (`CabinetUserRoleQuickStatusView`, `AssignUserToCabinetForm`). **Important:** the RBAC
  helper functions themselves do **not** filter on `status` — see Gotchas below.

A user can hold different roles in different Cabinets simultaneously (a `DIRECTOR` in
Cabinet A can be an `ENGINEER` in Cabinet B, or have no role in Cabinet C at all).

### `CabinetContextLog` (`accounts/models.py`)

```
cabinet (FK, nullable) · switched_by (FK User, nullable) · action (SWITCH | CLEAR) · created_at
```

Append-only audit trail for the superuser cabinet-switcher — see below. Registered
read-only in the Django admin (`has_add_permission`/`has_change_permission` both return
`False`); the only way a row is created is through `SwitchCabinetView`.

## State machines / workflows

`UserCabinetRole.status` is the one lifecycle this app owns:

```
PENDING -> APPROVED   (superadmin, via CabinetUserRoleQuickStatusView or
                        CabinetUserRoleUpdateView — one-click or full edit form)
PENDING -> REJECTED   (same views)
```

There is no `clean()`-level validation on this transition (unlike the status machines
documented in `docs/architecture/overview.md#status-state-machines` for other apps) —
any status value in `ApprovalStatus.choices` can be set from any other at any time,
enforced only by the superadmin-only view layer (`IsSuperAdminMixin`), not by the model
itself. A regular (non-superuser) code path can never create or change a
`UserCabinetRole` row at all — every view that touches this model is gated
`SUPERADMIN ONLY`.

## Superuser cabinet-switcher flow

A superuser can "switch into" a specific Cabinet for their session to browse/administer
it as if they were a member of it:

1. `SwitchCabinetView` (POST-only, `accounts:switch_cabinet`) — with a `cabinet_id`,
   stores it in `request.session['active_cabinet_id']` and logs a `SWITCH`
   `CabinetContextLog` row; with no `cabinet_id`, pops the session key and logs `CLEAR`.
2. `core.mixins.get_session_cabinet(request)` resolves that session value back into a
   `Cabinet` on every subsequent request, **re-validating** it: a non-superuser's stored
   selection is checked against their own `UserCabinetRole` rows every time (so a
   revoked role drops the stale selection silently), but a **superuser's selection is
   trusted without a `UserCabinetRole` check** — they can switch into any Cabinet in the
   system, by design (platform-admin impersonation).
3. While active, the navbar shows an amber "viewing as" banner
   (`core.context_processors.active_cabinet_context`, superuser-only). Without an active
   selection, a superuser sees every Cabinet unfiltered.
4. A **regular** multi-cabinet user can also populate the same session key (there's no
   navbar UI pointing them at it, but the endpoint doesn't block them) — this is how
   `CabinetAccessMixin.get_user_cabinet()` disambiguates which Cabinet a new record
   should be tagged with for someone who belongs to more than one.

`SwitchCabinetView` scopes a regular user's switch target with
`get_object_or_404(Cabinet, pk=cabinet_pk, user_roles__user=request.user)` — they can
never activate a Cabinet they don't actually hold a role in, even by guessing an id.

## Views & permissions

| View | URL name | Access | Notes |
|---|---|---|---|
| `SwitchCabinetView` | `switch_cabinet` | Any authenticated user | See flow above; POST-only. |
| `UserProfileUpdateView` | `profile_update` | Any authenticated user, own profile only | `get_object()` always returns `self.request.user`; `form_valid()` double-checks `form.instance.id == request.user.id` as a belt-and-braces guard. |
| `UserListAdminView`, `UserCreateAdminView`, `UserEditAdminView`, `UserDeleteAdminView`, `UserDetailAdminView`, `UserResetPasswordAdminView`, `UserToggleActiveAdminView` | `admin_users_*` | **SUPERADMIN ONLY** (`IsSuperAdminMixin`, `is_superuser` check) | New accounts get a random temporary password with `must_change_password=True` forced on. Self-deactivation and self-deletion are explicitly blocked; editing your own account silently reverts an attempt to remove your own `is_active`/`is_staff`/`is_superuser` flags rather than letting you lock yourself out. |
| `RoleAssignmentListAdminView` | `admin_role_assignments_list` | **SUPERADMIN ONLY** | System-wide, cross-Cabinet view of every `UserCabinetRole`. |
| `CabinetListAdminView`, `CabinetDetailAdminView`, `CabinetCreateView`, `CabinetUpdateView`, `CabinetDeleteView` | `admin_cabinet*` | **SUPERADMIN ONLY** | `CabinetDeleteView` surfaces a cascade-impact count (sites/expenses/invoices) before confirming. |
| `AssignUserToCabinetView`, `AssignUserToCabinetFromDetailView`, `CabinetUserRoleUpdateView`, `CabinetUserRoleDeleteView`, `CabinetUserRoleQuickStatusView` | `assign_user_to_cabinet`, `admin_assign_user_to_cabinet`, `admin_cabinet_user_role_*` | **SUPERADMIN ONLY** | Create/edit/revoke a `UserCabinetRole`; the quick-status view is the one-click approve/reject path. |

None of these use `allowed_roles`/`can_act_for_cabinet` — admin management here is
gated purely on `is_superuser`, a level above the per-Cabinet role model these views
themselves administer.

## Business rules & gotchas

- **This is the only permission store.** Django's built-in permission/group framework
  is not used for business authorization anywhere — don't reach for
  `user.has_perm(...)` expecting it to reflect a Cabinet role; check `UserCabinetRole`
  (directly, or via `core.mixins`/`has_role`) instead.
- **`UserCabinetRole.status` is not enforced by the RBAC helpers.** `can_act_for_cabinet`,
  `can_view_cabinet`, `CabinetAccessMixin` and `RoleRequiredMixin` all query
  `UserCabinetRole` by `(user, cabinet, role)` only — none of them filter on
  `status=APPROVED`. In practice this means a `PENDING` assignment already grants full
  access as if it were approved; `status` is effectively a superadmin bookkeeping/review
  field, not a gate. If this surprises you, it's worth double-checking before relying on
  "pending means no access yet" anywhere.
- **A superuser's switched-in Cabinet is never role-checked.** `get_session_cabinet`
  only re-validates a *non*-superuser's session selection against `UserCabinetRole`; a
  superuser can switch into (and act fully within) any Cabinet in the system regardless
  of whether they hold any role there at all — by design, but worth remembering when
  reasoning about "who can do X" from the data alone.
- **Self-protection guards are deliberately narrow.** `UserEditAdminView` blocks you
  from deactivating yourself, removing your own staff access, or removing your own
  superuser access *only when editing your own account* — a second superadmin can still
  do any of those to you. `UserDeleteAdminView` and `UserToggleActiveAdminView` block
  self-deletion/self-deactivation outright (no bypass).
- **Temporary passwords are shown exactly once**, in a Django messages-framework
  success message after creation or reset — they are not stored anywhere in retrievable
  form (only the hash). If the message is missed, the only recovery path is another
  reset.
- **`CabinetContextLog` rows are never deleted or edited** (admin has both permissions
  disabled) — it's an append-only trail by design; don't expect to "clean it up" through
  the admin.
