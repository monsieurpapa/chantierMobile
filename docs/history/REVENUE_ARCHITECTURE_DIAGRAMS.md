# Revenue Module - Architecture & Workflow Diagrams

## 1. Navigation Structure

```
┌─────────────────────────────────────────────────────────────┐
│                         DASHBOARD                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  MODULES                         NAVIGATION MENU             │
│  ├── Dashboard                   Revenue (dropdown)           │
│  ├── Projects & Sites            ├── Client Contracts        │
│  ├── Personnel                   ├── Invoices                │
│  ├── Finance                     └── Payments                │
│  ├── Materials                                               │
│  └── Revenue ──────────────────► ✓ Fully Implemented       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Revenue Module Components

```
┌────────────────────────────────────────────────────────────────┐
│                     REVENUE MODULE                              │
├────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │    Contracts     │  │    Invoices      │  │  Payments   │  │
│  ├──────────────────┤  ├──────────────────┤  ├─────────────┤  │
│  │ • List view      │  │ • List view      │  │ • List view │  │
│  │ • Create form    │  │ • Create form    │  │ • Create    │  │
│  │ • Edit form      │  │ • Detail view    │  │   form      │  │
│  │ • Linked to      │  │ • Status machine │  │ • Track     │  │
│  │   Sites          │  │ • Payment track  │  │   payment   │  │
│  │                  │  │                  │  │   history   │  │
│  └──────────────────┘  └──────────────────┘  └─────────────┘  │
│         ▲                       ▲                    │          │
│         │                       │                    ▼          │
│         └───────────────────────┴─────────────────────────────┘
│                                                                  │
│              All operations filtered by Cabinet                │
│            (Multi-tenant for different locations)              │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow Diagram

```
PROJECT CREATION
       │
       ▼
   Create Site
       │
       ├─────────────────────────┐
       │                         │
       ▼                         ▼
  Finance Module          Revenue Module
  (Expenses/Budgets)     (Contracts/Invoices)
       │                         │
       │                    Create Contract
       │                         │
       │                         ├──► Linked to Site
       │                         ├──► Store value & terms
       │                         │
       │                         ▼
       │                    Create Invoice
       │                         │
       │                    ├──► DRAFT status
       │                    ├──► Set dates & amount
       │                    ├──► Send to client (→ SENT)
       │                    │
       │                    ▼
       │                Record Payment
       │                    │
       │                ├──► CASH IN ✓
       │                ├──► Update invoice status
       │                └──► Check if fully paid
       │
       └─────────────────────────┘
              PROFITABILITY
           (Income - Expenses)
```

---

## 4. Invoice Status State Machine

```
┌──────────┐
│  DRAFT   │ ← Initial state when created
└────┬─────┘
     │ Invoice sent to client
     ▼
┌──────────┐
│  SENT    │ ← Awaiting payment
└────┬─────┘
     │
     ├─────────────────────┬─────────────────┐
     │ Full payment         │ Not paid by     │
     │ received             │ due date        │
     ▼                      ▼                 │
┌──────────┐            ┌───────────┐      │
│  PAID ✓  │            │  OVERDUE  │      │
│ (Final)  │            │           │      │
└──────────┘            └─────┬─────┘      │
                              │ Payment    │
                              │ received   │
                              ▼            │
                          ┌──────────┐    │
                          │  PAID ✓  │◄───┘
                          │ (Final)  │
                          └──────────┘

Alternative Path:
┌──────────┐
│  DRAFT   │
└────┬─────┘
     │ Cancel (corrections needed)
     ▼
┌────────────┐
│ CANCELLED  │ ← Final state, create new invoice
└────────────┘
```

---

## 5. User Interaction Flow

```
User Action                     View                          Result
─────────────────────────────────────────────────────────────────

ACCESS REVENUE
        │
        ▼
Click "Revenue" menu    ─────► Navbar-Vertical    ─────► Dropdown expands
        │                                                  ↓
        ├─ Click "Contracts"  ─► ContractListView  ─────► See all contracts
        │                                               (New Contract button)
        │
        ├─ Click "Invoices"   ─► InvoiceListView   ─────► See all invoices
        │                                               (New Invoice button)
        │
        └─ Click "Payments"   ─► PaymentListView   ─────► See all payments
                                                        (Summary cards)


CREATE CONTRACT
        │
        ▼
Click "New Contract"    ─► ContractCreateView  ─► Form
        │                                         ├─ Select Site
        │                                         ├─ Enter Client Name
        │                                         └─ Enter Total Value
        │
        ▼
Submit Form             ─► Validate            ─► Success message
        │
        ▼
Redirect to List        ─► ContractListView    ─► See new contract


CREATE INVOICE
        │
        ▼
Click "New Invoice"     ─► InvoiceCreateView   ─► Form
        │                                         ├─ Select Contract
        │                                         ├─ Enter Amount
        │                                         ├─ Set Issue Date
        │                                         └─ Set Due Date
        │
        ▼
Submit Form             ─► Validate            ─► Invoice created (DRAFT)
        │
        ▼
View Invoice            ─► InvoiceDetailView   ─► Show with status
        │                                         & payment history
        ▼
Update Status           ─► Manual update       ─► DRAFT → SENT


RECORD PAYMENT
        │
        ▼
Click "Record Payment"  ─► PaymentCreateView   ─► Form
        │                                         ├─ Select Invoice
        │                                         ├─ Amount
        │                                         ├─ Date
        │                                         ├─ Method
        │                                         └─ Reference
        │
        ▼
Submit Form             ─► Validate            ─► Payment saved
        │                                         ↓
        │                                         Invoice updated
        │                                         (Check if fully paid)
        │
        ▼
Redirect                ─► InvoiceDetailView   ─► Show payment in history


VIEW PAYMENT HISTORY
        │
        ▼
Click "Payments"        ─► PaymentListView     ─► All payments
                                                  ├─ Summary cards
                                                  └─ Payment table
```

---

## 6. Database Relationships

```
┌──────────────────┐
│      Site        │
│ (from Projects)  │
│                  │
│ • name           │
│ • location       │
│ • unique_id      │
└────────┬─────────┘
         │ 1:1
         │
         ▼
┌──────────────────┐
│    Contract      │
│                  │
│ • site_id        │─────► (FK) Site
│ • client_name    │
│ • total_value    │
│ • signed_date    │
└────────┬─────────┘
         │ 1:M
         │
         ▼
┌──────────────────┐
│     Invoice      │
│                  │
│ • contract_id    │─────► (FK) Contract
│ • invoice_number │
│ • amount         │
│ • issued_date    │
│ • due_date       │
│ • status         │
└────────┬─────────┘
         │ 1:M
         │
         ▼
┌──────────────────┐
│     Payment      │
│                  │
│ • invoice_id     │─────► (FK) Invoice
│ • amount         │
│ • payment_date   │
│ • method         │
│ • reference      │
└──────────────────┘
```

**Cascade Delete Behavior**:
- Delete Site → Delete Contract → Delete Invoices → Delete Payments
- Ensures data integrity across cascade

---

## 7. Role-Based Access Control

```
┌─────────────────────────────────────────────────────────────┐
│                    REVENUE MODULE                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│   Permission Level              Allowed Operations           │
│   ─────────────────────────────────────────────────────      │
│                                                               │
│   DIRECTOR                                                    │
│   ├─ View Contracts           ✓                              │
│   ├─ Create/Edit Contracts    ✓                              │
│   ├─ View Invoices            ✓                              │
│   ├─ Create/Edit Invoices     ✓                              │
│   ├─ View Payments            ✓                              │
│   └─ Record Payments          ✓                              │
│                                                               │
│   ACCOUNTANT                                                  │
│   ├─ View Contracts           ✓                              │
│   ├─ Create/Edit Contracts    ✓                              │
│   ├─ View Invoices            ✓                              │
│   ├─ Create/Edit Invoices     ✓                              │
│   ├─ View Payments            ✓                              │
│   └─ Record Payments          ✓                              │
│                                                               │
│   CASHIER                                                     │
│   ├─ View Contracts           ✗                              │
│   ├─ Create/Edit Contracts    ✗                              │
│   ├─ View Invoices            ✗                              │
│   ├─ Create/Edit Invoices     ✗                              │
│   ├─ View Payments            ✓                              │
│   └─ Record Payments          ✓                              │
│                                                               │
│   OTHER STAFF                                                 │
│   ├─ Any Revenue Operation    ✗                              │
│   └─ (View-only via reports)  ✓                              │
│                                                               │
│   All operations filtered by Cabinet (multi-tenant)         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Integration with Other Modules

```
        ┌─────────────────┐
        │    PROJECTS     │
        │  (Site, Phase)  │
        └────────┬────────┘
                 │
                 │ 1:1
                 │ Creates
                 ▼
        ┌─────────────────┐
        │    Revenue      │
        │  (Contracts,    │
        │   Invoices,     │──────┐
        │   Payments)     │      │
        └────────┬────────┘      │
                 │               │
                 │ Tracks        │
                 │ Income        │
                 ▼               │
        ┌─────────────────┐      │
        │    Finance      │      │
        │  (Expenses,     │◄─────┘
        │   Budgets)      │
        │ Tracks Costs    │
        └────────┬────────┘
                 │
                 │ Both together
                 ▼
        ┌──────────────────┐
        │ Profitability    │
        │ = Income - Costs │
        └──────────────────┘

Integration Points:
• Contract → Site (project context)
• Invoice → Expense tracking (cost vs revenue)
• Payment → Budget reconciliation
• Invoice/Payment → Financial reports
```

---

## 9. Payment Method Reference

```
┌────────────────────────────────────────┐
│      SUPPORTED PAYMENT METHODS          │
├────────────────────────────────────────┤
│                                         │
│ 1. CHECK                                │
│    └─ Reference: Check #12345           │
│                                         │
│ 2. BANK TRANSFER (Wire/ACH)             │
│    └─ Reference: Transaction ID         │
│                                         │
│ 3. CASH                                 │
│    └─ Reference: Receipt # or note      │
│                                         │
│ 4. DIGITAL PAYMENT                      │
│    └─ Reference: Mobile Money ID        │
│       or Credit Card TX#                │
│                                         │
│ When recording payment:                 │
│ • Select method from dropdown           │
│ • Enter amount                          │
│ • Enter reference for reconciliation    │
│                                         │
└────────────────────────────────────────┘
```

---

## 10. Daily Operations Timeline

```
TIME            OPERATION                    VIEW/ACTION
─────────────────────────────────────────────────────────

09:00 AM        Morning Review              Revenue → Invoices
                Check pending invoices      (Filter by SENT status)

10:00 AM        Create new invoice          Click "New Invoice"
                for yesterday's work        Select contract & enter details

12:00 PM        Payment Received            Revenue → Invoices
                via bank transfer           Find invoice → Record Payment
                                           (Auto-marks PAID)

02:00 PM        Follow-up on overdue        Revenue → Invoices
                invoices                    (Filter by OVERDUE status)

04:00 PM        Payment Reconciliation      Revenue → Payments
                Check all payments          Verify amounts & methods
                recorded today

05:00 PM        End of day report           Payment list summary
                Total payments received     = Alert on dashboard
```

---

**Diagrams Last Updated**: January 30, 2026
**Status**: Complete & Production Ready
