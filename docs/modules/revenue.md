# `revenue`

`revenue` owns the client-facing side of a Site's finances: quoting
(`Devis`/`DevisLine`), the signed `Contract` a quote turns into, progress
billing against that contract (`SituationTravaux`/`SituationLine`),
one-off `Invoice`s, and `Payment`s received against them. A site's
commercial lifecycle generally runs: **Devis** (BROUILLON→ENVOYE→ACCEPTE)
→ **Contract** (created automatically on acceptance) → either direct
**Invoice**s or **SituationTravaux** progress statements (which themselves
generate an Invoice) → **Payment**s, which auto-mark the invoice PAID once
fully covered. It is the counterpart to `finance`'s spend side — see
`finance.models.Avenant` for how an authorized budget overage becomes
client debt tracked on `Contract.avenant_debt`.

## Models

### Contract
One per `Site` (`OneToOneField`), normally created by
`Devis.accept_and_create_contract()` rather than directly.
- `total_value`, `signed_date`, `avenant_debt` (extra debt from
  director-authorized budget overages — see `finance.models.Avenant.approve()`)
- `source_devis` — the ACCEPTE `Devis` this contract came from, if any
- `total_paid` — sum of `Payment` across all of this contract's invoices
- `client_balance` — `total_value + avenant_debt − total_paid`: what the
  client still owes, shown next to the site's (expense) budget so a
  director/cashier sees both sides of the ledger at a glance.

### Invoice
A billing statement against a `Contract`. Status: `InvoiceStatus`.
- `clean()` — `due_date >= issued_date`, positive amount, and the
  DRAFT/SENT/PAID/OVERDUE/CANCELLED transition table. **CANCELLED is only
  reachable from DRAFT** in this table — see Business rules & gotchas.
- `check_and_mark_paid(changed_by)` — SENT/OVERDUE→PAID once
  `payments.sum(amount) >= amount`; called from `Payment.save()` so it
  fires from any entry point (view, admin, shell), not just the payment
  form; logs via `StatusChangeLog`.

### Payment
A single payment against an `Invoice`.
- `save()` — on creation only, calls `invoice.check_and_mark_paid()`.
  Editing or soft-deleting a `Payment` afterwards does **not** re-evaluate
  or revert the invoice's PAID status.
- `method` — `PaymentMethod` (bank transfer / check / cash / mobile money).

### Devis / DevisLine (quoting)
`Devis`: a quote/estimate sent to a client before work begins. A `Site`
can have several (revisions/competing drafts) but — in intent — only one
may ever be accepted, since accepting one creates the site's `Contract`
(`OneToOneField`). Status: `DevisStatus`.
- `clean()` — `validity_date >= issue_date` and the
  BROUILLON/ENVOYE/ACCEPTE/REFUSE/EXPIRE transition table. **Does not**
  check for an existing `Contract` on the site — see gotchas.
- `accept_and_create_contract(changed_by)` — ENVOYE→ACCEPTE; creates the
  `Contract` from `total_ht`; this is where the "only one accepted devis
  per site" rule is actually enforced (`Contract.objects.filter(site_id=...).exists()`).
- `total_ht` / `total_items` — aggregated from `lines`.
- A `Devis` may carry a scanned `photo` instead of typed-in lines (create/
  update views drop the "at least one line" formset requirement when a
  photo is attached).
- `source_dqe` **(added 2026-10-07)** — optional FK to `pricing.DQE`,
  nullable, `SET_NULL`, `related_name='devis_set'`, scoped in
  `DevisForm.__init__` to DQEs belonging to the devis's own `site`. Purely
  informational on the `Devis`/`Contract` state machine above (it doesn't
  participate in any transition or validation here) — its entire purpose is
  downstream, in `pricing`: `pricing.services.baseline_quantity()` only
  looks at an **ACCEPTE** devis that has a `source_dqe` set, exploding that
  DQE's lines (by étape) to get the "what was actually budgeted" figure the
  Devis & États de besoin comparison engine checks material requests
  against. A `Devis` with no `source_dqe` (e.g. a hand-typed or
  photo-attached quote with no DQE behind it) simply has no baseline —
  every material request against that site's phases shows as
  `NOT_BUDGETED` rather than `GREEN`/`ORANGE`/`RED`. See
  [`pricing.md`](pricing.md#comparison-engine-pricingservicespy-added-2026-10-07)
  for the full engine.

`DevisLine`: one priced row (designation/unit/quantity/unit_price_ht),
freeform and self-contained (mirrors `pricing.DQELine`'s shape).
- `clean()` — quantity strictly positive; unit price ≥ 0.
- `total_ht` — `quantity × unit_price_ht`.

### SituationTravaux / SituationLine (progress billing)
`SituationTravaux`: a periodic progress-billing statement against a
signed `Contract`, numbered per contract (`unique_together =
('contract', 'numero')`). Status: `SituationStatus`.
- `clean()` — BROUILLON→VALIDEE→FACTUREE, each step terminal-forward only.
- `generate_invoice(changed_by, due_in_days=30)` — VALIDEE→FACTUREE;
  creates the period's `Invoice` for `total_ht_period` and links it
  (`OneToOneField`); logs via `StatusChangeLog`.
- `total_ht_cumulative` / `total_ht_period` — sums across `lines`.

`SituationLine`: one `DevisLine`'s cumulative advancement % on a given
situation (`unique_together = ('situation', 'devis_line')`), tying
progress billing back to the original quote's line items.
- `clean()` — 0 ≤ `cumulative_percentage` ≤ 100, and never lower than the
  same `DevisLine`'s percentage on an earlier situation of the same
  contract (progress only moves forward).
- `previous_cumulative_percentage` / `period_percentage` /
  `cumulative_amount_ht` / `period_amount_ht` — the period-vs-cumulative
  math `generate_invoice()` relies on.

## State machines / workflows

```text
Devis:               BROUILLON → ENVOYE → ACCEPTE      (terminal)
                                         → REFUSE       (terminal)
                               → EXPIRE                 (terminal)
                     BROUILLON → REFUSE                 (terminal)
  Send:    DEVIS_ACTION_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
           DIRECTEUR_GENERAL/CHIEF_ENGINEER/ACCOUNTANT) — devis_send
  Accept:  same roles — devis_accept (Devis.accept_and_create_contract())
  Reject:  same roles — devis_reject

Invoice:             DRAFT → SENT → PAID                (terminal)
                                  → OVERDUE → PAID       (terminal)
                           → CANCELLED                   (terminal; DRAFT only — see gotchas)
  Send:    INVOICE_ACTION_ROLES (DIRECTOR/DIRECTEUR_TECHNIQUE/
           DIRECTEUR_GENERAL/ACCOUNTANT) — invoice_send, DRAFT-only
  Cancel:  same roles — invoice_cancel, DRAFT-only
  SENT → OVERDUE happens automatically, not from a user action — see
  "Async tasks" below.
  SENT/OVERDUE → PAID is automatic too, via Payment.save() →
  Invoice.check_and_mark_paid() (no dedicated view).

SituationTravaux:    BROUILLON → VALIDEE → FACTUREE      (terminal)
  Validate: DEVIS_ACTION_ROLES — situation_validate
  Facturer: DEVIS_ACTION_ROLES — situation_generate_invoice
            (SituationTravaux.generate_invoice())
```

All transitions are validated in the model's own `clean()` (plus, for
`Devis.accept_and_create_contract()` / `SituationTravaux.generate_invoice()`
/ `Invoice.check_and_mark_paid()`, a dedicated method that also calls
`full_clean()`/`save()` and logs via `StatusChangeLog`) — per the
project-wide rule in
[`architecture/overview.md`](../architecture/overview.md#status-state-machines).

### Async tasks

`revenue.tasks.mark_overdue_invoices` (Celery, daily at 01:00
Africa/Kigali — see
[`architecture/overview.md`](../architecture/overview.md#async-tasks))
bulk-transitions every SENT invoice whose `due_date` has passed to
OVERDUE, via `bulk_update` (no per-row `clean()`/`save()`, since the
queryset already guarantees a valid SENT→OVERDUE starting state).

## Views & permissions

All in `revenue/views.py`. Two shared role-list constants:
`DEVIS_ACTION_ROLES` (DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/
CHIEF_ENGINEER/ACCOUNTANT — send/accept/reject a Devis, validate/invoice a
Situation) and `INVOICE_ACTION_ROLES` (DIRECTOR/DIRECTEUR_TECHNIQUE/
DIRECTEUR_GENERAL/ACCOUNTANT — send/cancel an Invoice).

**Contracts** — `ContractListView` open to any authenticated user
(cabinet-scoped); create/update gated to DIRECTOR tier + ACCOUNTANT.

**Invoices** — `InvoiceListView`/`InvoiceDetailView` open to any
authenticated user in the cabinet; `InvoiceCreateView` gated to DIRECTOR
tier + ACCOUNTANT; `invoice_send`/`invoice_cancel` gated to
`INVOICE_ACTION_ROLES`, both DRAFT-only. The detail view's status actions
(envoyer/annuler/enregistrer un paiement) deliberately live in one
role-gated "Actions" card in the template rather than as header actions —
see the comment on `InvoiceDetailView.get_header_actions()`.

**Payments** — `PaymentListView` gated to DIRECTOR tier + ACCOUNTANT
(note: **not** CASHIER); `PaymentCreateView` gated to the same roles
**plus** CASHIER — see gotchas.

**Devis** — `DevisListView`/`DevisDetailView` open to any authenticated
user in the cabinet; create/update/send/accept/reject all gated to
`DEVIS_ACTION_ROLES`.

**Situations de travaux** — `SituationTravauxListView`/`DetailView` open
to any authenticated user; create/validate/generate-invoice gated to
`DEVIS_ACTION_ROLES` (reused — same "who can touch billing progress"
circle as Devis actions).

**PDF export** — `invoice_pdf`, `contract_pdf` each render a single
document as a two-column field/value table (not a multi-row report),
reusing `core.pdf_utils.render_table_report_pdf`'s layout. Both are
read-only and available to anyone who can already view the underlying
object (cabinet-scoped, no extra role check beyond that).

## Business rules & gotchas

- **`Invoice` cannot be cancelled once SENT or OVERDUE — despite the
  architecture overview's summary diagram suggesting otherwise.**
  `docs/architecture/overview.md`'s state-machine summary describes
  Invoice CANCELLED as reachable "from any non-terminal" state, but
  `Invoice.clean()`'s actual `valid_transitions` table only allows
  `DRAFT: [SENT, CANCELLED]` — `SENT` and `OVERDUE` have no `CANCELLED` in
  their allowed-transitions list, and `invoice_cancel` (the only view that
  cancels one) also only acts when `status == DRAFT`. In practice this
  means there is **no way to cancel an invoice once it has been sent to
  the client** — a mistakenly-sent SENT invoice can only be left to go
  OVERDUE or be paid off, never cancelled, through anything in this
  codebase today.
- **`Devis`'s "only one accepted devis per site" guarantee lives in
  `accept_and_create_contract()`, not in `clean()`.** Every other status
  invariant in this app is self-protecting at the model level per the
  project-wide rule — but `Devis.clean()`'s transition table happily
  allows ENVOYE→ACCEPTE with no check against an existing `Contract`. The
  "can't accept a second devis for an already-contracted site" check only
  runs inside `accept_and_create_contract()`. Any other path that sets
  `devis.status = ACCEPTE` and calls `full_clean()`/`save()` directly
  (admin, shell, a future view) would bypass it, potentially leaving an
  ACCEPTE devis with no matching `Contract` or silently succeeding where a
  second `Contract` creation should have been blocked.
- **`PaymentListView` and `PaymentCreateView` have asymmetric role
  lists.** `PaymentCreateView.allowed_roles` includes CASHIER;
  `PaymentListView.allowed_roles` does not. A cashier can record a payment
  but cannot browse `revenue:payment_list` to see the history of payments
  they (or anyone else) recorded — likely an oversight rather than a
  deliberate restriction, since nothing else in the role model treats
  CASHIER as untrusted to view payment history.
- **`InvoiceListView`'s "Nouvelle facture" header action has no role
  check**, unlike most other list views' header actions in this app
  (which check a role before showing the button) — it's shown to every
  authenticated viewer regardless of role. Not a security gap (clicking
  through still hits `InvoiceCreateView`'s own `allowed_roles` gate), but
  an unprivileged viewer sees a button that will redirect/error on click.
- **`DevisUpdateView` doesn't itself re-check that the devis is still
  BROUILLON.** The UI only links to it while BROUILLON (see
  `DevisDetailView.get_header_actions()`), but the view has no equivalent
  guard, so a direct POST to the update URL could edit an already-ENVOYE
  or ACCEPTE devis's line items after the fact — a data-integrity
  concern more than an access-control one, since it's still role-gated to
  `DEVIS_ACTION_ROLES`.
- **Payment edits/deletes don't reopen a PAID invoice.** `Payment.save()`
  only calls `check_and_mark_paid()` `if is_new` — correcting or removing
  a `Payment` after an invoice has already been auto-marked PAID leaves
  that invoice PAID regardless of whether the payments on file still add
  up to the full amount.
