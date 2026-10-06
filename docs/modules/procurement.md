# `procurement`

The `procurement` app owns the supplier directory, purchase orders raised
against suppliers, the stock those orders replenish, and credit financing for
purchases made on account. It is the "achats & stocks" half of the materials
story: `materials` raises an état de besoin and (optionally) books an
`Expense`; `procurement` is where an actual order gets placed with a named
supplier, received into a Site's stock, and — for cash-light cabinets — paid
off over time as supplier credit instead of up front.

## Models

### `Supplier`
A cabinet-scoped fournisseur directory entry.

| Field | Notes |
|---|---|
| `cabinet` | direct FK, cascade |
| `name`, `contact_name`, `phone`, `email`, `address`, `notes` | |

Notable: `total_orders`, `total_credit_outstanding` (properties).

### `SupplierCredit` / `SupplierCreditPayment`
Financing a purchase on account (achat à crédit), with installment payments
tracked separately so the audit trail always shows who paid what, when.

| Field (`SupplierCredit`) | Notes |
|---|---|
| `supplier` | cascade |
| `purchase_order` | nullable, `SET_NULL` — a credit doesn't have to be tied to one order |
| `amount` / `paid_amount` | running totals; `paid_amount` only ever advances through `record_payment()` |

Notable methods: `record_payment(amount, user, caisse=None, date=None)` —
atomically creates the `SupplierCreditPayment`, optionally books a `SORTIE`
on a `Caisse` if paid from cash on hand, and bumps `paid_amount` (rejecting
anything that would push it past `amount`). `outstanding_balance`,
`is_fully_paid` — properties.

`SupplierCreditPayment` rows are always created through `record_payment()`,
never directly, so `paid_amount` on the parent stays in sync.

### `StockItem`
A tracked inventory item at a `projects.Site` — `quantity_on_hand` is a
running total that is **only ever changed through `StockMovement`** (a
receipt, a manual entry/exit, a correction, or a transfer), never written
directly by a view or form past initial creation (the form disables the
field once the instance has a `pk`).

| Field | Notes |
|---|---|
| `site` | cascade |
| `material` | nullable FK to `materials.Material` — a stock item doesn't have to be catalog-linked |
| `quantity_on_hand`, `reorder_threshold` | |

Notable: `is_below_reorder_threshold` (property), `transfer_to(destination,
quantity, user, ...)` — moves stock to another `StockItem` (typically the
same material at a different site) by creating a paired `TRANSFER`
`StockMovement` on both sides atomically, linked via `transfer_pair`.

### `PurchaseOrder`
A bon de commande against a `Supplier`, for a `Site`.

| Field | Notes |
|---|---|
| `site`, `supplier` | cascade / protect |
| `status` | `PurchaseOrderStatus` (see state machine) |
| `caisse` | `CaisseType` — which cash register funded it; tag for filtering reports, not a balance-tracked relation |
| `payment_method` | `PurchasePaymentMethod` — `CAISSE` or `VIREMENT` |
| `transfer_proof`, `entered_by_cashier`, `entered_at`, `validated_by_financier`, `validated_at` | the wire-transfer sign-off trail, populated only for `VIREMENT` orders |

Notable methods:
- `receive(changed_by=None, lines_received=None)` — creates an `IN`
  `StockMovement` per line still outstanding (full remaining quantity by
  default, or a partial amount per line via `lines_received`), bumping each
  line's `quantity_received`, and transitions the order to `RECUE` or
  `RECUE_PARTIELLE` depending on whether every line is now fully received.
- `submit_transfer_proof(user, proof_file)` — la caissière enters the proof
  the financier sent her; **resets** any prior validation.
- `validate_transfer(user)` — le financier validates the submitted proof.
- `is_transfer_validated` (property) — `True` only for a `VIREMENT` order
  with `validated_by_financier` set.
- `clean()` — delivery-date ordering, plus the `status` state machine below
  (only checked once the order already has a `pk`).

### `PurchaseOrderLine`
A line item, tied to the `StockItem` it will replenish.

| Field | Notes |
|---|---|
| `purchase_order`, `stock_item` | cascade / protect |
| `quantity`, `quantity_received`, `unit_price` | |

`clean()` enforces `quantity_received <= quantity` and that `stock_item.site
== purchase_order.site` — nothing at the DB/FK level guarantees that second
one. `line_total`, `remaining_quantity` — properties.

### `StockMovement`
The one and only path by which `StockItem.quantity_on_hand` changes — an
audit-trailed row for every receipt, manual entry/exit, correction, or
transfer leg.

| Field | Notes |
|---|---|
| `stock_item` | protect |
| `movement_type` | `StockMovementType`: `IN` / `OUT` / `ADJUSTMENT` / `TRANSFER` |
| `purchase_order_line` | set when this movement came from receiving a PO |
| `is_transfer_source`, `transfer_pair` | `TRANSFER`-only: which side of the pair this row is, and a `OneToOneField('self')` linking the two |
| `phase` | optional `ProjectPhase` tag |

`save()` is where the real work happens: on creation, it re-checks the
negative-stock guard against a freshly-refreshed `quantity_on_hand`, then
applies the signed delta (`_signed_delta()`: negative for `OUT` and the
`TRANSFER` source leg, positive otherwise) to the related `StockItem` via an
`F()`-expression `UPDATE` — not a Python read-modify-write — so the
arithmetic itself survives concurrent writes. `clean()` additionally checks
phase/site consistency and quantity sign rules, but only runs when something
calls `full_clean()` explicitly; `save()`'s own guard is the one check that
always fires, including for rows created directly via `.objects.create()`
(`transfer_to()`, `PurchaseOrder.receive()`) that never call `full_clean()`.

## State machines / workflows

```text
PurchaseOrder:
    BROUILLON --send()--> ENVOYEE --receive()--> RECUE_PARTIELLE --receive()--> RECUE (terminal)
       |                     |         (direct, if every line fully received) --> RECUE (terminal)
       |                     |
       +------ cancel() -----+----------------------------------------------> ANNULEE (terminal)
```
(`send`/`receive`/`cancel` here are the function-based *view* names; the
model itself only exposes `receive()` — `send`/`cancel` are plain status
assignments followed by `full_clean()`/`save()` in the view.)

- **`BROUILLON → ENVOYEE`**: `purchase_order_send` view. Role gate:
  `PURCHASE_ORDER_ACTION_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE',
  'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']`. Enforced via
  `PurchaseOrder.clean()`'s transition table.
- **`ENVOYEE`/`RECUE_PARTIELLE → RECUE`/`RECUE_PARTIELLE`**:
  `purchase_order_receive` view → `PurchaseOrder.receive()`. Same role gate.
- **`BROUILLON`/`ENVOYEE → ANNULEE`**: `purchase_order_cancel` view. Same
  role gate; blocked once any line has been received (`clean()`'s transition
  table has no edge out of `RECUE_PARTIELLE`/`RECUE` into `ANNULEE`).
- **Wire-transfer sign-off** (informational, see gotchas below):
  `purchase_order_submit_transfer_proof` (la caissière) — role gate
  `TRANSFER_ENTRY_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE',
  'DIRECTEUR_GENERAL', 'CASHIER']` — then `purchase_order_validate_transfer`
  (le financier) — role gate `TRANSFER_VALIDATE_ROLES = ['DIRECTOR',
  'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'FINANCIER']`.

```text
StockItem.quantity_on_hand: only moved by StockMovement.save() —
    IN / ADJUSTMENT(+)  -> increases
    OUT / ADJUSTMENT(-) -> decreases (blocked if it would go negative)
    TRANSFER source leg -> decreases this item, TRANSFER dest leg -> increases the paired item
```

## Views & permissions

| View / endpoint | Who | Notes |
|---|---|---|
| `SupplierListView` / `StockItemListView` / `PurchaseOrderListView` | any member of the cabinet | `CabinetAccessMixin` |
| `SupplierCreateView`/`UpdateView`, `StockItemCreateView`/`UpdateView`, `PurchaseOrderCreateView`/`UpdateView` | `DIRECTOR`, `DIRECTEUR_TECHNIQUE`, `DIRECTEUR_GENERAL`, `CHIEF_ENGINEER` (+ `ACCOUNTANT` for purchase orders) | `allowed_roles` |
| `stock_movement_create`, `stock_transfer_create` | `STOCK_ACTION_ROLES` (adds `MAGASINIER`) | `can_act_for_cabinet` |
| `purchase_order_send` / `_receive` / `_cancel` | `PURCHASE_ORDER_ACTION_ROLES` | `can_act_for_cabinet`; object fetched unscoped, role check carries the cabinet scoping |
| `purchase_order_submit_transfer_proof` | `TRANSFER_ENTRY_ROLES` | la caissière |
| `purchase_order_validate_transfer` | `TRANSFER_VALIDATE_ROLES` | le financier |
| `SupplierCreditListView`/`CreateView`, `supplier_credit_repay` | `CREDIT_MANAGE_ROLES` (director-tier, `ACCOUNTANT`, `CASHIER`, `FINANCIER`) | |
| `AchatsReportView` / `achats_report_pdf` | `ACHATS_REPORT_ROLES` | |
| `StockReportView` / `stock_report_pdf` | `STOCK_REPORT_ROLES` (adds `ENGINEER`, `MAGASINIER`) | |

## Business rules & gotchas

- **The financier's wire-transfer validation does not gate anything.**
  `purchase_order_receive` (and `PurchaseOrder.receive()`/`clean()`) never
  check `is_transfer_validated`. A `VIREMENT`-funded order can be sent and
  fully received — stock booked in, `RECUE` reached — whether or not the
  financier ever validated the cashier's transfer proof, or even before any
  proof was submitted at all. The caissière-enters/financier-valide flow is a
  record-keeping trail alongside the order, not a precondition enforced on
  `send`/`receive`. If the business expects "no goods in before the money is
  confirmed sent," that expectation is not currently encoded anywhere in code.
- **The transfer sign-off can be self-administered.** `TRANSFER_ENTRY_ROLES`
  and `TRANSFER_VALIDATE_ROLES` both include `DIRECTOR`/`DIRECTEUR_TECHNIQUE`/
  `DIRECTEUR_GENERAL`, and neither `submit_transfer_proof()` nor
  `validate_transfer()` checks that two different people performed the two
  steps. A director-tier user can upload the transfer proof and then
  immediately validate it themselves — the two-person dual control the French
  copy ("la caissière saisit... le financier valide") implies is not actually
  enforced for anyone in that role band.
- **`PurchaseOrderUpdateView` has no status guard.** The UI only shows
  "Modifier" while an order is `BROUILLON` (`PurchaseOrderDetailView.
  get_header_actions`), but the view/URL itself doesn't check status —
  someone with `PURCHASE_ORDER_ACTION_ROLES` who navigates there directly can
  still edit an order's lines/fields after it's been sent or partially
  received. `PurchaseOrderLine.clean()` blocks reducing `quantity` below
  what's already `quantity_received`, but `unit_price`, `supplier`, `site`,
  etc. have no such backstop.
- **Negative-stock guard has a check-then-act race window.**
  `StockMovement.save()` re-checks "would this go negative?" against a
  freshly refreshed `quantity_on_hand` and then applies the delta via an
  `F()`-expression update — the arithmetic update itself is race-safe, but
  the guard check and that update are two separate statements. Two genuinely
  concurrent movements against the same `StockItem` (no explicit
  `select_for_update()` anywhere in this path) can each read the same
  pre-movement quantity, both pass the guard, and both apply their delta —
  landing stock below zero despite the check. Low-likelihood in a
  single-request-at-a-time admin tool, but worth knowing if this ever moves
  behind a queue or a busier API.
- `Supplier`/`StockItem`/`PurchaseOrder` function-based action views
  (`purchase_order_send`/`_receive`/`_cancel`, `stock_movement_create`,
  `stock_transfer_create`, `supplier_credit_repay`, the transfer-proof views)
  all fetch their target object with a bare `get_object_or_404(Model,
  pk=pk)` — no cabinet-scoped queryset. This is **not** a tenant-isolation
  gap: the permission check immediately after (`can_act_for_cabinet(request,
  <obj>.site.cabinet, ROLES)`) uses the object's *own* cabinet, so a user
  outside it is rejected by the role lookup even without a queryset filter.
  It only works because every one of these checks is present — if a future
  endpoint is added following this pattern and the `can_act_for_cabinet` call
  is forgotten, there would be nothing else stopping it.
- `CaisseType` (on `PurchaseOrder.caisse`) is a plain tag for report
  filtering, not a balance-tracked relation to `finance.Caisse` — don't
  expect it to reconcile against actual caisse transactions the way
  `SupplierCredit.record_payment()`'s `caisse` argument does.
