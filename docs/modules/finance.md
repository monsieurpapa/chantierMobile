# `finance`

`finance` owns every money-movement workflow inside a Cabinet: project
budgets and the expense-approval pipeline that spends against them, the
balance-tracked Caisse (cash register) ledger with inter-caisse loans and
transfers, the two separate payroll tracks (progressive ouvrier payments
vs. fixed ingénieur/staff salaries — see
[ADR 0005](../architecture/decisions/0005-separate-payroll-tracks.md)),
and Avenant change-order authorization that lets a site's budget grow
beyond its original cap while turning the overage into client debt (see
`revenue.models.Contract.avenant_debt`). It is the app `docs/security.md`
means when it talks about "wire transfers, supplier credit... caisse...
payroll" needing director/accountant/cashier-tier roles.

## Models

### Budget
One per `Site` (`OneToOneField`) — a spending envelope for a fixed
`start_date`–`end_date` period.
- `total_amount`, `start_date`, `end_date`
- `is_budget_period_active()` / `get_spent_amount()` (APPROVED+PAID
  expenses whose `expense_date` falls in the period) / `get_remaining_amount()`
  / `is_budget_exceeded(amount)`
- A site with no Budget has **no spending cap enforced at all** — budgets
  are opt-in, not implicit.

### ExpenseCategory
Simple classification tag (name + description), managed from Django admin.

### Expense
A spend request against a `Site`, optionally a `ProjectPhase` and a
`personnel.Personnel` (for `ExpenseNature.MAIN_DOEUVRE` lines). Status:
`chantiermobile.constants.ExpenseStatus`.
- `clean()` — positive amount; a linked personnel must actually be
  assigned to the site and be eligible; the PENDING→APPROVED/REJECTED→
  PAID/REJECTED transition table; and, only when the status is (or is
  becoming) APPROVED and the site has a Budget, that the budget period is
  active and the amount fits what remains.
- `approve(user, comments)` — PENDING→APPROVED, creates an
  `ExpenseApproval`. **Blocks self-approval** (`requester == user`) unless
  `user.is_superuser`. Locks the site's `Budget` row
  (`select_for_update()`) first, to serialize concurrent approvals against
  the same budget.
- `reject(user, comments)` — PENDING→REJECTED, creates an
  `ExpenseApproval`. No self-rejection guard (rejecting your own request
  has no money-movement consequence).
- `pay(user, caisse)` — APPROVED→PAID; records a matching SORTIE
  `CaisseTransaction` on `caisse` *before* flipping the status, raising if
  `amount > caisse.balance`.
- `latest_approval` / `approved_by` — read the `ExpenseApproval` audit
  trail.

### ExpenseApproval
One approve/reject decision + comments, created by `Expense.approve()`/
`reject()`. Never updated in place — a reject-then-resubmit cycle produces
more than one row.

### Caisse
A cash register whose `balance` is a **live aggregate** over its
`CaisseTransaction` rows (ENTREE sum − SORTIE sum), not a stored counter.
- `cabinet`, optional `site` (project-dedicated caisse), `is_administrative`
  (the caisse other caisses remit to daily), `manual_site_entry` (serves
  external clients — e.g. a bétonnière rental caisse — via a free-text
  chantier/client label instead of an internal `Site` link).
- `responsible_cashier` (added 2026-10-06, permission table update) —
  optional FK to the `User` designated as this caisse's own cashier,
  settable from `CaisseCreateView`/`CaisseUpdateView` (`CaisseForm`),
  narrowed in those views to users holding an APPROVED `CASHIER` or
  `ACCOUNTANT` role in the caisse's cabinet
  (`CAISSE_RESPONSIBLE_CASHIER_ROLES`/`_responsible_cashier_candidates()`
  in `finance/views.py`) — `ACCOUNTANT` is included because a
  limited-staff cabinet often has its accountant act as cashier too. A
  caisse left without one simply has no per-caisse modification
  restriction beyond `CAISSE_MANAGE_ROLES`/`recorded_by` — see
  `CaisseTransaction.can_be_modified_by()` below and docs/security.md.
- `record(transaction_type, amount, user, ...)` — the low-level entry
  point used by every other money-moving method below. Uses
  `.objects.create()` directly and does **not** call `full_clean()` — see
  Business rules & gotchas.
- `transfer_to(target_caisse, amount, user, description)` — atomic
  SORTIE+ENTREE pair, no repayment tracked (use `CaisseLoan` for that).

### CaisseTransactionCategory
Filterable tag for a ledger movement (separate from `ExpenseCategory`).
Seeded names (`finance.0013`) include `"Achat matériaux"` — referenced by
the `MATERIALS_PURCHASE_CATEGORY_NAME` constant (`finance/models.py`),
which drives the material line-item section below (matched by name, not
by a dedicated flag on this model — an admin renaming that row would need
the constant updated too).

### CaisseTransaction
One ledger row (`ENTREE`/`SORTIE`). `clean()` only requires a positive
`amount` — and only actually runs on the manual-entry path (a
`CaisseTransactionForm`/admin save), not on the `Caisse.record()` path used
by `pay()`/`disburse()`/`transfer_to()`/`CaisseLoan`.
- `can_be_modified_by(user)` (added 2026-10-06, permission table update) —
  `True` for `is_superuser`, for the caisse's `responsible_cashier`, or
  for whoever recorded this specific row (`recorded_by`); `False`
  otherwise. Backs `CaisseTransactionUpdateView`'s object-level check
  (narrower than the `CAISSE_MANAGE_ROLES` role gate it also sits behind —
  see Views & permissions). Deliberately **not** wired into
  `CaisseTransactionDeleteView`, which keeps its original cabinet-wide
  `CAISSE_MANAGE_ROLES` gating unchanged — this restriction currently
  covers editing only, a conservative scope decision made since deleting
  a transaction already existed as a feature and narrowing it further
  wasn't explicitly requested.

### CaisseTransactionMaterialLine (added 2026-10-06)
One "description du matériel / quantité / P.U. / prix total" row on a
`CaisseTransaction` — lets a cash outflow (typically filed under the
`"Achat matériaux"` category, see above) itemize what was actually
bought. `transaction` FK (`related_name='material_lines'`),
`material`/`material_name` catalog-or-free-text XOR (same shape as
`materials.MaterialRequestItem` — see `clean()`), `quantity`,
`unit_price`, and a `line_total` property (`quantity * unit_price`,
mirroring `pricing.DQELine.line_total`).
- Built via `CaisseTransactionMaterialLineFormSet` (`finance/forms.py`,
  `inlineformset_factory`, prefix `'material'`, no `min_num` — the
  section is entirely optional), shown/hidden client-side in
  `caisse_transaction_form.html` by matching the selected `category`
  option's text against `MATERIALS_PURCHASE_CATEGORY_NAME` — nothing
  server-side actually requires that specific category, a line can be
  saved under any category.
- `MaterialLineFormSetMixin` (`finance/views.py`), shared by
  `CaisseTransactionCreateView`/`UpdateView`, mirrors `personnel`'s
  `ConventionFormSetMixin` (`personnel/views.py`) including its "formset
  not submitted" guard: a POST missing the section's management-form
  fields (an older client, a direct API call) saves the transaction with
  no material-line changes rather than raising.
- **Financial record only** (confirmed scope) — saving these lines does
  **not** touch `procurement.StockItem`/`StockMovement`. The chantier's
  actual stock-on-hand continues to be tracked entirely by the
  magasinier through the existing stock-movement flow (`procurement`
  app); see `docs/modules/projects.md`'s "Matériaux" tab section and
  `docs/modules/procurement.md` for where the technical team already has
  a daily/weekly/monthly historical view of that separate ledger
  (`procurement.StockReportView`, unmodified by this feature beyond a new
  link into it).

### CaisseLoan
A cash advance from one `Caisse` to another that must be repaid.
- `clean()` — lender ≠ borrower, positive amount, and — **creation only**
  (`not self.pk`) — the lender actually holds the funds.
- `disburse(user)` — atomic SORTIE (lender) + ENTREE (borrower) pair,
  called immediately after creation by `CaisseLoanCreateView`.
- `repay(amount, user)` — partial or full repayment (borrower→lender),
  rejects an amount that would exceed `outstanding_balance`.
- `outstanding_balance` / `is_fully_repaid` properties.

### PayrollList / PayrollListItem ("Main d'œuvre" — ouvriers, site-scoped)
`PayrollList`: one per `Site` (+ optional `ProjectPhase`), status
`PayrollListStatus` (`BROUILLON`→`SOUMISE`→`PAYEE`).
- `total_amount` — sum of its items.
- `submit(user)` — BROUILLON→SOUMISE, requires ≥1 item.
- `disburse(user, caisse)` — SOUMISE→PAYEE; records one SORTIE
  transaction for the OUVRIER total under category *"Main d'œuvre
  Ouvriers"* (and, as a legacy safety net for pre-guard data, a second one
  for any INGENIEUR total under *"Salaire Ingénieurs"*). Not
  concurrency-safe the same way `Expense.approve()` is (no row lock on the
  caisse before the balance check).

`PayrollListItem`: one ouvrier/amount row, optionally tied to a
`personnel.SiteAssignment` (convention).
- `clean()` — positive amount; personnel must be eligible; personnel's
  `payroll_type` must be `OUVRIER` (INGENIEUR is rejected — see
  `SalaryPaymentItem` instead); the assignment (if any) must belong to this
  personnel; and if the assignment has a `convention_amount` cap, this
  amount plus whatever was already paid against it must not exceed the
  cap (edits exclude the item's own prior amount from "already paid").
- **Chef de corps soft-overage rule (2026-10-07):** the cap check above is
  a hard block for everyone *except* `personnel.is_chef_de_corps`, whose
  renegotiated scope of work can legitimately run ahead of the avenant
  that will eventually catch up with it. For a chef de corps, exceeding
  the cap requires a non-empty `overage_note` instead of being rejected
  outright — see `docs/modules/personnel.md`'s ConventionAvenant section.
  Every chef-de-corps item with an `overage_note` is surfaced via
  `ConventionOverageListView` (below) for the DG/bureau technique.
- **Convention details at disbursement (2026-10-06):** `payroll_list_detail.html`
  (`PayrollListDetailView`) now shows, next to each item, the linked
  `assignment`'s convention `name` (falling back to `role` for an older,
  full affectation), its `phase` (étape), and — when a `convention_amount`
  cap is tracked — that cap and `remaining_convention`, so the cashier
  knows what a given payment is for and how much room is left before
  disbursing. `PayrollListDetailView.get_queryset()` prefetches
  `items__assignment__phase`/`items__assignment__site` to avoid an N+1.
  See `docs/modules/personnel.md`'s "Chantiers & conventions" section for
  where these `SiteAssignment` rows get created.

### SalaryPaymentList / SalaryPaymentItem ("Ingénieurs & Staff" — cabinet-scoped)
See [ADR 0005](../architecture/decisions/0005-separate-payroll-tracks.md)
for why this is a second, parallel model rather than one shared payroll
table. `SalaryPaymentList`: one per `Cabinet` (not a `Site`), same
`BROUILLON`→`SOUMISE`→`PAYEE` workflow and method shapes as `PayrollList`,
disbursing one SORTIE transaction under *"Salaire Ingénieurs"*.

`SalaryPaymentItem`: one agent/period/amount row.
- `clean()` — positive amount; `period` must match `AAAA-MM`; personnel
  eligible; personnel's `payroll_type` must be `INGENIEUR` (mirror image of
  `PayrollListItem`'s guard); personnel must belong to the same cabinet as
  the list.
- `unique_together = ('personnel', 'period')` — can't double-pay the same
  person for the same month across different lists.

### Avenant (change-order authorization)
A request to spend beyond a site's initial budget. Status `AvenantStatus`
(`PENDING`→`APPROVED`/`REJECTED`, both terminal).
- `approve(user, notes)` — grows `site.budget.total_amount` by
  `self.amount` and, if the site has a `Contract`, adds the same amount to
  `Contract.avenant_debt` (the client's extra debt for authorized overage).
- `reject(user, notes)` — no side effects.
- **No self-decision guard on either method** — see Business rules &
  gotchas, this is the headline finding of this pass.

## State machines / workflows

```text
Expense:              PENDING → APPROVED → PAID        (terminal)
                              → REJECTED                (terminal)
  Approve: DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/ACCOUNTANT
           (approve_expense view; Expense.approve() blocks self-approval)
  Reject:  same roles (reject_expense view)
  Pay:     DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CASHIER
           (mark_expense_paid view; Expense.pay())

PayrollList /
SalaryPaymentList:     BROUILLON → SOUMISE → PAYEE      (terminal)
  Submit:   PAYROLL_PREPARE_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
            DIRECTEUR_GENERAL/CHIEF_ENGINEER/ENGINEER) — .submit()
  Disburse: PAYROLL_DISBURSE_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
            DIRECTEUR_GENERAL/ACCOUNTANT/CASHIER/FINANCIER) — .disburse()
  These two role sets overlap on the three director-tier roles, so there
  is no enforced separation between who prepares and who disburses a
  given list.

Avenant:               PENDING → APPROVED               (terminal)
                               → REJECTED                (terminal)
  Request: AVENANT_REQUEST_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
           DIRECTEUR_GENERAL/CHIEF_ENGINEER/ACCOUNTANT) — AvenantCreateView
  Decide:  FINAL_AUTHORIZATION_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
           DIRECTEUR_GENERAL) — _avenant_decide() / Avenant.approve()/reject()
  All three director-tier roles can both REQUEST and DECIDE — see gotchas.

CaisseLoan:            created (funds move immediately via disburse()) →
                       repaid incrementally via repay() until
                       is_fully_repaid — no formal status field, tracked
                       via repaid_amount vs. amount.
```

All transitions above are validated in the model's own `clean()` (or, for
`Expense`/`Avenant`/payroll lists, the dedicated action method that also
calls `full_clean()`/`save()`), per the project-wide rule in
[`architecture/overview.md`](../architecture/overview.md#status-state-machines) —
not only from the one view that currently exposes it.

## Views & permissions

All in `finance/views.py`; role-list constants are defined once at the top
of that module and reused across views (`core/approvals.py` keeps its own
duplicated copy of `EXPENSE_APPROVAL_ROLES` for the pending-approvals
inbox, which must be updated by hand if this changes — see
[`docs/security.md`](../security.md#a-note-on-duplicated-role-lists)).

**Expenses** — `ExpenseListView`/`ExpenseDetailView` open to any
authenticated user (cabinet-scoped); `ExpenseCreateView` same;
`approve_expense`/`reject_expense` gated to `EXPENSE_APPROVAL_ROLES`
(DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/ACCOUNTANT);
`mark_expense_paid` gated to DIRECTOR/DIRECTEUR_TECHNIQUE/
DIRECTEUR_GENERAL/CASHIER. `ExpenseReportView` + `expense_report_pdf` gated
to `EXPENSE_REPORT_ROLES` (adds CASHIER to the approval roles, and —
2026-10-07 — `MAGASINIER_GENERAL`, read-only, see
[`docs/security.md`](../security.md)) — PDF via
`core.pdf_utils.render_table_report_pdf`.

**Dépassements de convention** (added 2026-10-07) —
`ConventionOverageListView` (`finance:convention_overage_list`) lists every
`PayrollListItem` with a non-empty `overage_note` (i.e. every chef-de-corps
payment that ran over its convention cap), for the DG/bureau technique to
review. Gated to `CONVENTION_OVERAGE_VIEW_ROLES` (DIRECTOR tier +
CHIEF_ENGINEER) — narrower than `EXPENSE_REPORT_ROLES`, since this is
specifically a DG/bureau-technique-facing report, not a general finance
report.

**Budgets** — `BUDGET_FULL_ACCESS_ROLES` (DIRECTOR tier + ACCOUNTANT +
CHIEF_ENGINEER) see every budget in the cabinet; a plain `ENGINEER`
(`BUDGET_VIEW_ROLES`) is scoped to only the sites they lead
(`_scope_budgets_for_viewer`). Create/update restricted to DIRECTOR tier +
ACCOUNTANT (ENGINEER/CHIEF_ENGINEER can view, not edit).

**Caisses** — `CaisseListView`/`CaisseDetailView` open to any authenticated
user in the cabinet; manual-transaction-entry/delete/transfer/
loan-create/loan-repay all gated to `CAISSE_MANAGE_ROLES` (DIRECTOR tier +
ACCOUNTANT + CASHIER + FINANCIER); `CaisseCreateView`/`CaisseUpdateView`
themselves use a narrower inline list (DIRECTOR tier + ACCOUNTANT only —
not the full `CAISSE_MANAGE_ROLES`). `CaisseReportView` + `caisse_report_pdf`
use the `CAISSE_MANAGE_ROLES` set.
- **`CaisseTransactionUpdateView`** (added 2026-10-06, permission table
  update — there was no edit path for a mouvement before this) sits
  behind two layers: `CAISSE_MANAGE_ROLES` scoped to the transaction's own
  caisse's cabinet (tighter than `CaisseTransactionDeleteView`'s
  cabinet-unscoped role check), **and** `CaisseTransaction.can_be_modified_by()`
  — only the caisse's `responsible_cashier`, or whoever recorded that
  specific transaction, may actually save a change (superuser bypasses
  both). A denied attempt is bounced back to `caisse_detail` with an
  error message, mirroring `MaterialRequestUpdateView`'s
  `dispatch()`-based self-administration guard (`materials/views.py`) —
  not a hard 403. The "Modifier" action only appears per-row in
  `caisse_detail.html` when `can_be_modified_by()` is true for the
  viewer; "Supprimer" is unaffected and still shows for any
  `CAISSE_MANAGE_ROLES` holder, since the delete view's own gating was
  deliberately left unchanged (see the CaisseTransaction model note
  above).

**Payroll (both tracks)** — list/detail views gated to `PAYROLL_VIEW_ROLES`
(union of prepare+disburse roles — payroll amounts are sensitive, unlike
most other list views in this app). Item-add views and `*_submit` gated to
`PAYROLL_PREPARE_ROLES`; `*_disburse` gated to `PAYROLL_DISBURSE_ROLES`.
PDF exports (`payroll_detail_pdf`, `salary_payment_detail_pdf`) gated to
`PAYROLL_VIEW_ROLES`.

**Avenants** — `AvenantListView` gated to `AVENANT_VIEW_ROLES` (requesters
∪ final authorizers); `can_decide` context flag further gates the
approve/reject buttons to `FINAL_AUTHORIZATION_ROLES`.
`AvenantCreateView` gated to `AVENANT_REQUEST_ROLES`.
`avenant_approve`/`avenant_reject` (thin wrappers over `_avenant_decide`)
gated to `FINAL_AUTHORIZATION_ROLES` — note these two views have **no
`@login_required` decorator**, unlike every other function view in this
module; they still fail closed for an anonymous request because
`can_act_for_cabinet()` returns `False` when `request.user` isn't
authenticated, but it's an inconsistency, not a deliberate design choice.

## Business rules & gotchas

- **Avenant now has a self-approval guard (fixed 2026-10-06).**
  `Avenant.approve()`/`reject()` block `self.requested_by_id == user.pk`
  the same way `Expense.approve()` does (see `docs/security.md`'s
  "self-approval" note) — bypassable only by a superuser.
  `AVENANT_REQUEST_ROLES` (who may file an avenant) and
  `FINAL_AUTHORIZATION_ROLES` (who may decide one) still **overlap on all
  three director-tier roles** (DIRECTOR, DIRECTEUR_TECHNIQUE,
  DIRECTEUR_GENERAL) — this is unchanged and intentional: a DIRECTOR can
  still request an avenant and *then* approve (or reject) a *different*
  director's/engineer's request, just never their own.
- **`Caisse.record()` does not validate the amount.** It's the common
  entry point for every programmatic money movement (`Expense.pay()`,
  both payroll `disburse()`s, `transfer_to()`, `CaisseLoan.disburse()`/
  `repay()`), but it calls `CaisseTransaction.objects.create()` directly,
  never `full_clean()`. `CaisseTransaction.clean()`'s positive-amount
  check only actually runs when a transaction is saved through a
  `ModelForm` (the manual-entry path). In practice every caller currently
  passes an amount that was already validated upstream (by the source
  model's own `clean()`, or by a view-level balance check), but there is
  no enforcement at the ledger layer itself — a future caller that skips
  that upstream check could write a zero/negative `CaisseTransaction`
  silently.
- **Deleting a `CaisseTransaction` doesn't reverse the record that
  created it.** `CaisseTransactionDeleteView` soft-deletes a transaction
  and `Caisse.balance` simply excludes it from its live aggregate going
  forward — but it does **not** revert the `Expense`'s `PAID` status, a
  `PayrollList`/`SalaryPaymentList`'s `PAYEE` status, or a `CaisseLoan`'s
  `repaid_amount`. Deleting a transaction tied to one of those silently
  makes the caisse's balance disagree with what those other records claim
  happened.
- **Payroll prepare/disburse roles overlap**, same way avenant request/
  decide roles do: `PAYROLL_PREPARE_ROLES` and `PAYROLL_DISBURSE_ROLES`
  share all three director-tier roles, so one person can prepare *and*
  disburse the same list with nobody else involved. Lower-stakes than the
  Avenant gap (no money moves until disburse, and the list itself is
  visible to everyone with `PAYROLL_VIEW_ROLES` before that point), but
  the same shape of gap.
- **`PayrollList.disburse()`/`SalaryPaymentList.disburse()` aren't
  concurrency-safe.** Unlike `Expense.approve()`, which locks the site's
  `Budget` row with `select_for_update()` before checking the cap, neither
  `disburse()` method locks the `Caisse` row before comparing
  `total > caisse.balance` — two concurrent disbursements against the
  same caisse could both pass the check before either's
  `CaisseTransaction` is written.
- **Budgets are opt-in.** A `Site` with no `Budget` has no spending cap
  enforced anywhere — `Expense.clean()`'s budget check only runs
  `if hasattr(self.site, 'budget')`. This is intentional (not every site
  needs a formal budget), but it means an unbudgeted site's expenses can
  be approved for any amount.
- **PDF exports** (`expense_report_pdf`, `caisse_report_pdf`,
  `payroll_detail_pdf`, `salary_payment_detail_pdf`) all share
  `core.pdf_utils.render_table_report_pdf` — a generic landscape/portrait
  tabular layout helper also used by other apps' reports.
