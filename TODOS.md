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

## P2 — Expense Approval Race Condition

**What:** Add `select_for_update()` + `transaction.atomic()` to `Expense.approve()` and `Expense.reject()` in `finance/models.py`.

**Why:** Two concurrent approval POST requests could both pass the budget check independently, then both save, resulting in a budget overrun. Under current single-worker traffic this is unlikely, but it becomes a real risk under load or with multiple accountants approving simultaneously.

**Context:** Wrap `approve()` body in `with transaction.atomic():` and add `budget = Budget.objects.select_for_update().get(site=self.site)` before the budget check in `Expense.clean()`. The `select_for_update()` acquires a row lock so only one request can proceed through the budget check at a time.

**Effort:** S (human: 30min / CC+gstack: 5min)
**Priority:** P2
**Depends on:** None
