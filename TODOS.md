# TODOS — ChantierMobile

Deferred work tracked here. Items added by `/plan-ceo-review` on 2026-03-31.

---

## P2 — Self-Approval Prevention

**What:** Prevent a user who submitted an expense from also approving it.

**Why:** Even in a small team, having the same person request and approve their own expense is a financial controls gap. Auditors flag this.

**Pros:** Strengthens financial controls; simple check.

**Cons:** Could be too restrictive for tiny cabinets where the Director is the only approver; may need an escape hatch for superusers.

**Context:** Add `if expense.requester == user: raise ValidationError(...)` to `Expense.approve()` in `finance/models.py`. Consider making it bypassable by `is_superuser` only.

**Effort:** S (human: 1h / CC+gstack: 5min)
**Priority:** P2
**Depends on:** None

---

## P2 — Status Change Audit Log

**What:** Track who changed the status of a Site or Invoice, when, and from what to what.

**Why:** Operational visibility — when a Site is paused or an invoice cancelled, there's currently no record of who made that decision or why. Hard to audit and debug post-hoc.

**Pros:** Full audit trail for compliance; enables "show history" UI.

**Cons:** Requires a new model and migration; need to hook into `save()` signals or override `save()` in Site/Invoice models.

**Context:** `ExpenseApproval` already does this for expenses — replicate the pattern generically. Options: (a) a generic `StatusChangeLog(content_type, object_id, changed_by, old_status, new_status, note, changed_at)` using ContentTypes framework, or (b) model-specific logs like `SiteStatusLog` and `InvoiceStatusLog`. Option (a) is more reusable.

**Effort:** M (human: 3h / CC+gstack: 15min)
**Priority:** P2
**Depends on:** None

---

## P3 — Budget Period Reporting

**What:** Add a budget utilization report showing spend by period, category breakdown, and forecast to end of period.

**Why:** Directors currently have to mentally calculate remaining budget from the expense list. A dashboard view would reduce errors and improve financial decision-making.

**Context:** `Budget.get_remaining_amount()` and `Budget.get_spent_amount()` already exist. Build a `BudgetDetailView` that aggregates by `ExpenseCategory` and projects spend rate to end of period.

**Effort:** M (human: 4h / CC+gstack: 20min)
**Priority:** P3
**Depends on:** expense_date field (already added)

---

~~## P3 — SiteDetailView Double Query~~ *(Fixed in commit 031deb1 — perf: eliminate duplicate site/expenses queries)*

---

## P1 — Cabinet Switcher for Superadmins

**What:** Session-based org context switcher in the top navbar, superadmin-only. Lets a superadmin scope all querysets to a single Cabinet without needing a separate login.

**Why:** Multi-tenant visibility — today a superadmin sees all tenant data interleaved with no filtering option. This is the foundation for per-tenant auditing, reporting, and support.

**Scope (locked):**
1. `POST /accounts/switch-cabinet/` → `SwitchCabinetView` (superadmin-only, CSRF, integer-validated `cabinet_id`)
2. `request.session['active_cabinet_id']` as context key
3. `CabinetAccessMixin.get_queryset()` — filter by session cabinet if set
4. `get_user_cabinet()` — use session cabinet for superusers (not `Cabinet.objects.first()`)
5. Cabinet dropdown in `navbar-top.html` (superadmin-only, `fas fa-building`)
6. Amber banner in `falcon_base.html` when session cabinet is active
7. `CabinetContextLog(cabinet, switched_by, action, created_at)` model + migration — `switched_by` must use `on_delete=SET_NULL, null=True`
8. `active_cabinet_context` context processor: injects `active_cabinet` into all templates (short-circuit for anonymous users)
9. Fix `BudgetListView.get_queryset()` and revenue view equivalents — currently return empty for superusers
10. Scope create form site dropdowns to session cabinet for superusers

**Security note:** Function-based action views (`approve_expense`, `approve_material_request`) ignore session cabinet — a superadmin can approve cross-tenant. Fix by adding explicit cabinet check in each action view before modifying the object.

**Effort:** M (human: 1 day / CC+gstack: 30min)
**Priority:** P1
**Depends on:** None

---

## P2 — Fix `IsSuperAdminMixin` Duplicate Definition

**What:** `IsSuperAdminMixin` is defined twice in `accounts/views.py` (lines 168 and 371). Second definition silently overrides first.

**Why:** Python class definitions are just assignments — the second one wins. If the two definitions ever diverge (someone edits one but not the other), behavior becomes unpredictable.

**Context:** Delete the second definition at line 371. Both are identical. One is enough.

**Effort:** XS (human: 5min / CC+gstack: 1min)
**Priority:** P2
**Depends on:** None

---

## P2 — Fix `cabinet_lookup_field` Pattern in `CabinetAccessMixin`

**What:** `CabinetAccessMixin.get_queryset()` uses `qs.filter(cabinet__in=cabinets)` which only works for models with a direct `cabinet` FK (`Site`, `Budget`). Models with indirect FKs (`Expense → site__cabinet`, `MaterialRequest → site__cabinet`, `Invoice → contract__site__cabinet`) return an empty queryset or crash silently.

**Why:** This is already worked around by individual view overrides, but the mixin's implicit contract is misleading. New models added without awareness of this will silently break.

**Context:** Add `cabinet_lookup_field = 'cabinet'` class attribute to `CabinetAccessMixin`. Views with indirect FKs set this to `'site__cabinet'`. Mixin uses it: `qs.filter(**{f'{self.cabinet_lookup_field}__in': cabinets})`.

**Effort:** S (human: 45min / CC+gstack: 5min)
**Priority:** P2
**Depends on:** Cabinet Switcher (P1)

---

## P2 — Expense Approval Race Condition

**What:** Add `select_for_update()` + `transaction.atomic()` to `Expense.approve()` and `Expense.reject()` in `finance/models.py`.

**Why:** Two concurrent approval POST requests could both pass the budget check independently, then both save, resulting in a budget overrun. Under current single-worker traffic this is unlikely, but it becomes a real risk under load or with multiple accountants approving simultaneously.

**Context:** Wrap `approve()` body in `with transaction.atomic():` and add `budget = Budget.objects.select_for_update().get(site=self.site)` before the budget check in `Expense.clean()`. The `select_for_update()` acquires a row lock so only one request can proceed through the budget check at a time.

**Effort:** S (human: 30min / CC+gstack: 5min)
**Priority:** P2
**Depends on:** None
