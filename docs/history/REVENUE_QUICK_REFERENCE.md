# Revenue Module - Quick Reference Guide

## Navigation Access

Users can now access all revenue features via the vertical navigation menu:

```
Dashboard → Revenue ↓
              ├── Client Contracts
              ├── Invoices
              └── Payments
```

## Key Features for Civil Engineering Firms

### 1. **Contract Management**
- Track all client agreements per project
- Store contract value and signing date
- Link contracts directly to project sites
- Quick access to create invoices for each contract

**Use Case**: "We have a contract with ABC Construction Co. for $500,000 for the office complex project"

### 2. **Invoice Generation**
- Create itemized bills from contracts
- Track invoice status (Draft → Sent → Paid)
- Support for overdue payment tracking
- Cancellation for corrections

**Use Case**: "Create monthly progress-based invoices as work completes"

**Invoice Workflow**:
```
Draft (being prepared)
   ↓
Sent (sent to client)
   ↓
Paid (payment received) OR Overdue (past due date)
```

### 3. **Payment Recording**
- Record payment details when money arrives
- Support multiple payment methods:
  - Check
  - Bank Transfer
  - Cash
  - Digital Payment
- Track transaction references
- Automatic invoice settlement when fully paid

**Use Case**: "Client paid $100,000 via bank transfer - record it to invoice INV-001"

## Typical Daily Operations

### Morning: Check Pending Invoices
1. Navigate to **Revenue → Invoices**
2. Review invoices in "SENT" status awaiting payment
3. Identify any overdue invoices
4. Decide on follow-up actions

### Noon: Record Payment Received
1. Receive check or bank confirmation
2. Navigate to **Revenue → Invoices**
3. Find relevant invoice
4. Click "Record Payment"
5. Enter amount, date, method, and check/reference number
6. System auto-marks invoice as PAID if fully settled

### End of Day: Payment Reconciliation
1. Navigate to **Revenue → Payments**
2. Review all payments received today
3. Verify amounts match invoices
4. Check payment methods and references are correct

## Role-Based Access

| Role | Create Contract | Create Invoice | Record Payment |
|------|-----------------|----------------|----------------|
| Director | ✅ | ✅ | ✅ |
| Accountant | ✅ | ✅ | ✅ |
| Cashier | ❌ | ❌ | ✅ |
| Engineer | ❌ | ❌ | ❌ |
| Supervisor | ❌ | ❌ | ❌ |

## Business Rules Enforced

### Contract Rules
- One contract per project site
- Total value should be positive
- Automatically linked when created

### Invoice Rules
- ✅ Unique invoice numbers
- ✅ Due date must be after issue date
- ✅ Amount must be positive
- ✅ Status transitions are enforced
- ✅ Cannot edit after status changes
- ✅ Cannot delete if payments recorded

### Payment Rules
- ✅ Must reference an existing invoice
- ✅ Payment amount must be positive
- ✅ Multiple payments allowed per invoice
- ✅ Auto-marks invoice as PAID when fully settled

## Multi-Cabinet Support (For Firms with Multiple Locations)

Each cabinet (location/division) has separate:
- Contracts
- Invoices  
- Payments

Users only see revenue data for cabinets they're assigned to.

## Integration with Other Modules

### Linked to Projects
- Every contract is tied to a specific site
- Site detail page shows contract and invoices
- Quick action to create invoice from site view

### Linked to Finance
- Invoices are income (revenue)
- Expenses are costs (finance module)
- Together show project profitability

## Common Tasks & Where to Do Them

| Task | Navigate To | Steps |
|------|-------------|-------|
| View all contracts | Revenue → Contracts | List shown by default |
| Create new contract | Revenue → Contracts | Click "New Contract" button |
| View contract details | Revenue → Contracts → Click contract | Opens contract detail |
| Generate invoice | Revenue → Contracts → Click contract | Click "Invoice" button |
| View all invoices | Revenue → Invoices | List shown by default |
| Check invoice status | Revenue → Invoices | Look at Status column |
| Record payment | Revenue → Invoices → Click invoice | Click "Record Payment" |
| View payment history | Revenue → Invoice detail | Scroll to Payments section |
| See all payments | Revenue → Payments | Complete payment list |
| Check payment method | Revenue → Payments | Method column shows it |

## Status Meanings

### Invoice Statuses
- **DRAFT**: Being prepared, not yet sent to client
- **SENT**: Sent to client, awaiting payment
- **PAID**: Fully paid by client ✓
- **OVERDUE**: Not paid by due date ⚠️
- **CANCELLED**: Invoice was cancelled (corrections/reversals)

## Examples

### Example 1: New Project Contract
1. Director creates Site "Office Tower - Phase 1"
2. Goes to Revenue → Client Contracts
3. Clicks "New Contract"
4. Selects the new site, enters "Skyrise Corp" as client, "$1,000,000" as value
5. Sets signed date
6. Saves - Now contract is ready

### Example 2: Billing the Client
1. Accountant goes to Revenue → Invoices
2. Clicks "New Invoice"
3. Selects the Office Tower contract
4. Enters INV-001, amount $250,000 (25% of contract)
5. Sets issue date (today) and due date (30 days)
6. Saves - Invoice is in DRAFT status

### Example 3: Sending Invoice
1. Invoice is in DRAFT status in Invoices list
2. Accountant exports/prints invoice
3. Sends to Skyrise Corp
4. Updates invoice status to SENT
5. Sets reminder for due date

### Example 4: Payment Receipt
1. Skyrise Corp sends check for $250,000
2. Cashier goes to Revenue → Invoices
3. Finds INV-001
4. Clicks "Record Payment"
5. Enters: $250,000, Payment Date (today), Method "Check", Reference "Check #12345"
6. Saves - System updates invoice to PAID

## FAQ

**Q: Can I edit an invoice after sending it?**
A: No, invoice is locked once SENT. If changes needed, cancel and create new one.

**Q: What happens if I receive partial payment?**
A: Invoice stays SENT. When total received = invoice amount, status becomes PAID.

**Q: Can multiple people record payments for one invoice?**
A: Yes, you can record multiple payments. System tracks all of them.

**Q: How do I handle late payments?**
A: If payment not received by due date, invoice status becomes OVERDUE. Continue tracking until paid.

**Q: Can I see payment history for an invoice?**
A: Yes, click on any invoice in the list to see all payments received for it.

**Q: What if payment is for the wrong amount?**
A: Record it anyway. You can record additional payment to balance later.

## Support Features

All revenue operations include:
- ✅ Success messages when operations complete
- ✅ Error messages if something fails
- ✅ Confirmation dialogs for critical actions
- ✅ Data validation before saving
- ✅ Multi-level approval if configured
- ✅ Automatic calculations (invoice totals, balance due)

---

**Last Updated**: January 2026
**Status**: ✅ Production Ready
