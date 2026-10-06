# Data Model

Split into five diagrams for readability — organizational core, projects/personnel,
finance, revenue/pricing, and procurement — rather than one dense graph. Every model
shown also inherits `core.models.BaseModel` (soft delete, audit fields, UUID) unless
noted otherwise; that's omitted below since it's uniform.

## Organizational core

```mermaid
erDiagram
    USER ||--o{ USERCABINETROLE : holds
    CABINET ||--o{ USERCABINETROLE : grants
    CABINET ||--o{ CABINETCONTEXTLOG : "switched into"
    USER ||--o{ CABINETCONTEXTLOG : switches

    CABINET {
        string name
        string logo
    }
    USERCABINETROLE {
        string role "UserRoles choice"
    }
```

A `UserCabinetRole` row is the entire authorization grant: `(user, cabinet, role)`. A
user with no row for a given Cabinet has zero access to it (barring superuser).

## Projects & Personnel

```mermaid
erDiagram
    CABINET ||--o{ SITE : owns
    CABINET ||--o{ PERSONNEL : employs
    CABINET ||--o{ HOLIDAY : defines
    SITE ||--o{ PROJECTPHASE : "broken into"
    SITE ||--o{ SITEASSIGNMENT : staffed-by
    SITE ||--o{ PLANNINGSUBMISSION : plans
    SITE ||--o{ ATTENDANCE : records
    SITE ||--o| USER : "lead_engineer"
    PROJECTPHASE ||--o{ SITEPROGRESS : "progress reports"
    PROJECTPHASE ||--o{ PLANNINGSUBMISSION : "(optional) scopes"
    SITEPROGRESS ||--o{ PROGRESSPHOTO : attaches
    SITEPROGRESS ||--o{ PROGRESSCOMMENT : discussed-in
    PERSONNEL ||--o{ SITEASSIGNMENT : assigned
    PERSONNEL ||--o{ PERSONNELDOCUMENT : files
    PERSONNEL ||--o{ LEAVE : requests
    PERSONNEL ||--o{ ATTENDANCE : "clocked for"
    PERSONNEL }o--o| USER : "login account (optional)"

    SITE {
        string status "SiteStatus"
        string name
    }
    PERSONNEL {
        string personnel_type "Employe/Tacheron/Prestataire"
        string payroll_type "Ouvrier/Ingenieur"
        string status "Actif/Inactif/NonEligible"
    }
    SITEASSIGNMENT {
        decimal convention_amount
        string role_on_site
    }
    PLANNINGSUBMISSION {
        string status "Brouillon/Soumise/Approuvee/Rejetee"
    }
    ATTENDANCE {
        string status "Present/Absent/Retard/DemiJournee"
        date work_date
    }
```

`Site` exposes computed properties (`total_spent`, `total_revenue`, `net_profit`,
`budget_usage_percentage`) that aggregate across the finance/revenue apps at read time
— these are not stored columns.

## Finance

```mermaid
erDiagram
    SITE ||--o| BUDGET : capped-by
    SITE ||--o{ EXPENSE : incurs
    SITE ||--o{ PAYROLLLIST : "pays ouvriers via"
    CABINET ||--o{ SALARYPAYMENTLIST : "pays staff via"
    CABINET ||--o{ CAISSE : operates
    EXPENSECATEGORY ||--o{ EXPENSE : categorizes
    EXPENSE ||--o{ EXPENSEAPPROVAL : "approval history"
    EXPENSE ||--o| MATERIALREQUEST : "(optional) funds"
    CAISSE ||--o{ CAISSETRANSACTION : ledgers
    CAISSE ||--o{ CAISSELOAN : "lends / borrows"
    CAISSE ||--o{ PAYROLLLIST : disburses
    CAISSE ||--o{ SALARYPAYMENTLIST : disburses
    PAYROLLLIST ||--o{ PAYROLLLISTITEM : lines
    SALARYPAYMENTLIST ||--o{ SALARYPAYMENTITEM : lines
    PAYROLLLISTITEM }o--|| PERSONNEL : pays
    SALARYPAYMENTITEM }o--|| PERSONNEL : pays
    SITE ||--o{ AVENANT : "change-orders"

    BUDGET {
        decimal total_amount
        date start_date
        date end_date
    }
    EXPENSE {
        string status "Pending/Approved/Rejected/Paid"
        string nature "Materiel/MainDoeuvre/Autre"
    }
    CAISSETRANSACTION {
        string type "Entree/Sortie"
    }
    PAYROLLLIST {
        string status "Brouillon/Soumise/Payee"
    }
    SALARYPAYMENTLIST {
        string status "Brouillon/Soumise/Payee"
    }
    AVENANT {
        string status "Pending/Approved/Rejected"
    }
```

Two payroll tracks are kept deliberately separate end-to-end — see
`PersonnelPayrollType` in `chantiermobile/constants.py` for the rationale: **ouvriers**
are paid progressively per-site through `PayrollList` (capped by
`SiteAssignment.convention_amount`); **ingénieurs/staff** are paid a fixed monthly
salary, not tied to a site, through `SalaryPaymentList`.

## Revenue & Pricing

```mermaid
erDiagram
    SITE ||--o| CONTRACT : "signed under"
    SITE ||--o{ DEVIS : quoted-by
    SITE ||--o{ DQE : estimated-by
    CONTRACT ||--o{ INVOICE : bills
    CONTRACT ||--o{ SITUATIONTRAVAUX : "progress-bills"
    INVOICE ||--o{ PAYMENT : receives
    INVOICE ||--o| SITUATIONTRAVAUX : "(optional) generated-from"
    DEVIS ||--o{ DEVISLINE : lines
    SITUATIONTRAVAUX ||--o{ SITUATIONLINE : lines
    SITUATIONLINE }o--|| DEVISLINE : "percent-complete of"
    CABINET ||--o{ PRICELIBRARYITEM : catalogs
    DQE ||--o{ DQELINE : lines
    DQELINE }o--|| PRICELIBRARYITEM : prices

    CONTRACT {
        decimal total_value
    }
    INVOICE {
        string status "Draft/Sent/Paid/Overdue/Cancelled"
        date due_date
    }
    DEVIS {
        string status "Brouillon/Envoye/Accepte/Refuse/Expire"
    }
    SITUATIONTRAVAUX {
        string status "Brouillon/Validee/Facturee"
    }
    PRICELIBRARYITEM {
        string item_type "Labor/Material/Equipment/Service/WorkItem"
    }
    DQE {
        string status "Draft/Validated/Archived"
    }
```

## Procurement & Materials

```mermaid
erDiagram
    SITE ||--o{ MATERIALREQUEST : raises
    SITE ||--o{ STOCKITEM : stocks
    SITE ||--o{ PURCHASEORDER : orders
    MATERIALREQUEST ||--o{ MATERIALREQUESTITEM : lines
    MATERIALREQUESTITEM }o--o| MATERIAL : "(optional, free-text allowed)"
    CABINET ||--o{ SUPPLIER : sources-from
    SUPPLIER ||--o{ PURCHASEORDER : fulfills
    SUPPLIER ||--o{ SUPPLIERCREDIT : extends
    SUPPLIERCREDIT ||--o{ SUPPLIERCREDITPAYMENT : repaid-by
    SUPPLIERCREDIT }o--o| PURCHASEORDER : "(optional) finances"
    PURCHASEORDER ||--o{ PURCHASEORDERLINE : lines
    PURCHASEORDERLINE }o--|| STOCKITEM : receives-into
    STOCKITEM ||--o{ STOCKMOVEMENT : moves

    MATERIALREQUEST {
        string status "Pending/Validated/Approved/Rejected/Ordered/Delivered"
    }
    PURCHASEORDER {
        string status "Brouillon/Envoyee/RecuePartielle/Recue/Annulee"
        string payment_method "Caisse/Virement"
    }
    STOCKMOVEMENT {
        string movement_type "In/Out/Adjustment/Transfer"
    }
```

`MaterialRequest` is a two-stage approval: a `MAGASINIER` validates it first
(`PENDING → VALIDATED`), then a director-tier role gives final authorization
(`VALIDATED → APPROVED`) — see `chantiermobile.constants.FINAL_AUTHORIZATION_ROLES`.
A `StockMovement` with `movement_type=TRANSFER` pairs two rows via `transfer_pair`
(one `OUT` of the source `StockItem`, one `IN` to the destination).

## Tasks (cross-cutting)

```mermaid
erDiagram
    SITE ||--o{ TASK : tracks
    PROJECTPHASE ||--o{ TASK : "(optional) scopes"
    USER ||--o{ TASK : "assigned to"

    TASK {
        string status "AFaire/EnCours/Bloquee/Terminee"
        string priority "Basse/Normale/Haute/Urgente"
    }
```
