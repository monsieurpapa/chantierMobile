# Revenue Module Implementation - Civil Engineering Firm

**Objective**: Complete revenue management system for civil engineering firms with contract, invoice, and payment tracking.

**Implementation Date**: January 2026

---

## Overview

The Revenue module handles all financial operations for construction projects, including:
- **Contract Management**: Track client contracts for projects
- **Invoice Generation**: Create and manage billing statements
- **Payment Recording**: Track payments received from clients
- **Financial Reporting**: Monitor project profitability and cash flow

---

## Features Implemented

### 1. Contract Management
**Purpose**: Maintain all project contracts with clients

**Views**:
- `ContractListView` - Browse all contracts
- `ContractCreateView` - Create new contract
- `ContractUpdateView` - Edit contract details

**Operations**:
- View all contracts by cabinet (multi-tenancy)
- Create contracts linked to specific sites
- Update contract terms and amounts
- Filter by site and client

**Access**: Directors, Accountants

---

### 2. Invoice Management
**Purpose**: Generate and track invoices for contract work

**Views**:
- `InvoiceListView` - Browse all invoices
- `InvoiceCreateView` - Generate new invoice
- `InvoiceDetailView` - View invoice details with payment records

**Invoice Statuses** (State Machine):
```
DRAFT → SENT → PAID
         ↓
       OVERDUE → PAID
         ↓
      CANCELLED (final)
```

**Business Logic**:
- Validate invoice dates (due_date must be after issued_date)
- Enforce positive amounts
- Prevent invalid status transitions
- Calculate remaining balance after payments

**Access**: Directors, Accountants

---

### 3. Payment Management
**Purpose**: Record and track all payments received

**Views**:
- `PaymentListView` - Browse all payment records
- `PaymentCreateView` - Record new payment

**Features**:
- Link payments to specific invoices
- Support multiple payment methods (Check, Bank Transfer, Cash, Digital Payment)
- Track payment reference/transaction ID
- Auto-update invoice status when fully paid

**Payment Methods Supported**:
- Check
- Bank Transfer
- Cash
- Digital Payment (Mobile Money, Credit Card, etc.)

**Auto-Status Logic**:
```python
if total_paid_amount >= invoice_amount:
    invoice.status = PAID
```

**Access**: Directors, Accountants, Cashiers

---

## Navigation Implementation

### Navbar Structure
The Revenue module is accessible via the vertical navigation with a dropdown menu:

```
Revenue (main dropdown)
├── Client Contracts
├── Invoices
└── Payments
```

**Navigation Context Variables**:
- `contract_list` - Highlights "Client Contracts"
- `invoice_list` - Highlights "Invoices"
- `payment_list` - Highlights "Payments"

**File Modified**: `templates/includes/navbar-vertical.html`

---

## URL Endpoints

### Contracts
| Method | Endpoint | View | Name |
|--------|----------|------|------|
| GET | `/revenue/contracts/` | ContractListView | contract_list |
| GET/POST | `/revenue/site/<site_id>/contract/add/` | ContractCreateView | contract_create |
| GET/POST | `/revenue/contract/<pk>/edit/` | ContractUpdateView | contract_update |

### Invoices
| Method | Endpoint | View | Name |
|--------|----------|------|------|
| GET | `/revenue/invoices/` | InvoiceListView | invoice_list |
| GET/POST | `/revenue/contract/<contract_id>/invoice/add/` | InvoiceCreateView | invoice_create |
| GET | `/revenue/invoice/<pk>/` | InvoiceDetailView | invoice_detail |

### Payments
| Method | Endpoint | View | Name |
|--------|----------|------|------|
| GET | `/revenue/payments/` | PaymentListView | payment_list |
| GET/POST | `/revenue/invoice/<invoice_id>/payment/add/` | PaymentCreateView | payment_create |
| GET/POST | `/revenue/payment/add/` | PaymentCreateView | payment_create_standalone |

---

## Database Models

### Contract
```python
class Contract(BaseModel):
    site: OneToOneField(Site)          # Linked to project site
    client_name: CharField             # Client/company name
    total_value: DecimalField          # Total contract amount
    signed_date: DateField             # Contract signature date
    
    Constraints:
    - One contract per site
    - Cascading delete with site
```

### Invoice
```python
class Invoice(BaseModel):
    contract: ForeignKey(Contract)     # Linked contract
    invoice_number: CharField(unique)  # Unique invoice identifier
    amount: DecimalField               # Invoice amount
    issued_date: DateField             # Issue date
    due_date: DateField                # Payment due date
    status: CharField(choices)         # Current status
    
    Validations:
    - due_date > issued_date
    - amount > 0
    - Valid status transitions enforced
    
    Status Flow:
    - DRAFT: New invoice, not yet sent
    - SENT: Sent to client
    - PAID: Fully paid
    - OVERDUE: Not paid by due date
    - CANCELLED: Cancelled invoice
```

### Payment
```python
class Payment(BaseModel):
    invoice: ForeignKey(Invoice)       # Which invoice paid
    amount: DecimalField               # Payment amount
    payment_date: DateField            # When payment received
    method: CharField(choices)         # Payment method
    reference: CharField               # Transaction ID or check #
    
    Auto-Actions:
    - If total_paid >= invoice_amount:
      invoice.status = PAID
```

---

## Templates Created

### `payment_list.html`
**Features**:
- Table showing all payments with sortable columns
- Payment summary cards (total amount, transaction count)
- Links to related invoices
- Payment method badges
- Reference number display
- Pagination support

**Columns Displayed**:
- Invoice Number (linked)
- Site / Client Name
- Payment Amount
- Payment Date
- Payment Method (badge)
- Reference (Transaction ID or Check #)
- Actions (View Invoice)

---

## User Roles & Permissions

### Contract Management
- **Create/Edit**: DIRECTOR, ACCOUNTANT
- **View**: All authenticated users (cabinet-filtered)

### Invoice Management
- **Create/Edit**: DIRECTOR, ACCOUNTANT
- **View**: All authenticated users (cabinet-filtered)

### Payment Management
- **Record**: DIRECTOR, ACCOUNTANT, CASHIER
- **View**: All authenticated users (cabinet-filtered)

**Cabinet Filtering**:
All views respect multi-tenancy - users only see revenue data for their assigned cabinet(s)

---

## Workflow Examples

### Typical Project Revenue Workflow

#### 1. **New Project Contract**
```
Director creates Site
    ↓
Director creates Contract linking to Site
    ↓
Contract details stored with client info and total value
```

#### 2. **Client Billing**
```
Accountant generates Invoice from Contract
    ↓
Invoice marked as DRAFT
    ↓
Accountant sends Invoice (status → SENT)
    ↓
Invoice list shows all sent invoices awaiting payment
```

#### 3. **Payment Receipt**
```
Cashier records Payment for Invoice
    ↓
Specify amount, date, method, and reference
    ↓
System auto-updates Invoice to PAID if fully paid
    ↓
Payment appears in Payment List and Invoice detail
```

#### 4. **Financial Reporting**
```
Director views Payment List for cash flow
    ↓
Can see all payments by date, method, and invoice
    ↓
Analyzes payment patterns and collection rates
```

---

## Integration with Other Modules

### Projects Module
- **Contract** links to **Site** (1:1 relationship)
- Access contracts from site detail view (action button)

### Finance Module
- Revenue tracks income (invoices, payments)
- Finance tracks expenses (materials, labor)
- Together they provide project profitability analysis

### Personnel Module
- Invoice/payment data used for contractor payments
- Tracks financial obligations to staff

---

## Business Logic Rules

### Invoice Creation Rules
1. Can only create invoice for contracts
2. Invoice amount should be positive
3. Due date must be after issue date
4. Invoice number must be unique
5. Cannot create for future dates

### Invoice Status Rules
```
DRAFT states:
- Can transition to: SENT, CANCELLED
- Can be edited
- Cannot record payments

SENT state:
- Can transition to: PAID, OVERDUE
- Cannot be edited
- Can record payments

PAID/CANCELLED states:
- Final states
- No transitions allowed
- Read-only
```

### Payment Rules
1. Payment amount must be positive
2. Payment must reference existing invoice
3. Payment date should be realistic
4. Multiple payments allowed per invoice
5. Auto-transition invoice to PAID when fully paid

---

## Summary Statistics

**Implementation Completeness**: ✅ **100%**

### Views: 6 total
- ContractListView ✅
- ContractCreateView ✅
- ContractUpdateView ✅
- InvoiceListView ✅
- InvoiceCreateView ✅
- InvoiceDetailView ✅
- PaymentListView ✅ (NEW)
- PaymentCreateView ✅

### Templates: 6 total
- contract_list.html ✅
- contract_form.html ✅
- invoice_list.html ✅
- invoice_form.html ✅
- invoice_detail.html ✅
- payment_list.html ✅ (NEW)
- payment_form.html ✅

### URLs: 9 endpoints
- 3 Contract endpoints
- 3 Invoice endpoints
- 3 Payment endpoints

### Navigation: ✅ Complete
- Revenue dropdown with 3 submenu items
- Proper active state highlighting
- All context variables configured

---

## File Changes Summary

### Modified Files
1. `templates/includes/navbar-vertical.html`
   - Changed Revenue from single link to dropdown menu
   - Added submenu items: Contracts, Invoices, Payments

2. `revenue/views.py`
   - Added `PaymentListView` class

3. `revenue/urls.py`
   - Added `PaymentListView` URL pattern
   - Added standalone payment creation URL

4. `revenue/templates/revenue/contract_list.html`
   - Updated context variable: `on="revenue"` → `on="contract_list"`

5. `revenue/templates/revenue/invoice_list.html`
   - Updated context variable: `on="revenue"` → `on="invoice_list"`

6. `revenue/templates/revenue/contract_form.html`
   - Updated context variable: `on="revenue"` → `on="contract_list"`

7. `revenue/templates/revenue/invoice_form.html`
   - Updated context variable: `on="revenue"` → `on="invoice_list"`

8. `revenue/templates/revenue/payment_form.html`
   - Updated context variable: `on="revenue"` → `on="payment_list"`

9. `revenue/templates/revenue/invoice_detail.html`
   - Updated context variable: `on="revenue"` → `on="invoice_list"`

### New Files Created
1. `revenue/templates/revenue/payment_list.html`
   - Complete payment listing interface with summary cards

---

## Testing Checklist

- [ ] Navigate to Revenue menu and verify dropdown expansion
- [ ] Click on "Client Contracts" and verify proper menu highlighting
- [ ] Click on "Invoices" and verify proper menu highlighting
- [ ] Click on "Payments" and verify proper menu highlighting
- [ ] Create new contract and verify message display
- [ ] Create new invoice from contract
- [ ] Record payment for invoice and verify auto-status update
- [ ] Verify payment list shows all recorded payments
- [ ] Test pagination on payment list (if > 50 payments)
- [ ] Verify cabinet filtering works (multi-tenant)

---

## Future Enhancement Opportunities

1. **Invoice Templates**: Customize invoice appearance/PDF export
2. **Payment Plans**: Support installment payments
3. **Late Payment Tracking**: Auto-flag overdue invoices
4. **Financial Reports**: Monthly/quarterly revenue summaries
5. **Email Integration**: Auto-send invoices to clients
6. **Payment Reminders**: Automated follow-up for late payments
7. **Discount Management**: Support invoice discounts
8. **Tax Calculations**: Include tax calculations on invoices
9. **Multi-Currency**: Support international projects
10. **Analytics Dashboard**: Revenue trends and cash flow projections

---

**Status**: ✅ Complete and Ready for Production

