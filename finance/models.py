"""Money-handling models for a Cabinet's operations: project budgets and
expense approval, the balance-tracked Caisse (cash register) ledger with
inter-caisse loans/transfers, the two payroll tracks (ouvriers vs.
ingénieurs/staff — see ADR 0005), and Avenant change-order authorization.

This is the app where the "who can spend/move/pay money, and under what
check" questions live. Every status field here follows the project-wide
rule (see docs/architecture/overview.md#status-state-machines): the
transition is validated in the model's own clean()/action method, not only
from the one view that currently exposes it.
"""
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site, ProjectPhase
from accounts.models import Cabinet
from chantiermobile.constants import (
    ExpenseStatus, ExpenseNature, FileUploadConfig, CaisseType, CaisseTransactionType,
    PayrollListStatus, AvenantStatus, PersonnelPayrollType,
)

# Caisse category names used when splitting a liste de paie décaissement —
# seeded once via a data migration (finance.0015) so they're always
# available in the "Catégorie" dropdown/filter, referenced here by name
# rather than re-created on the fly.
PAYROLL_OUVRIER_CATEGORY_NAME = "Main d'œuvre Ouvriers"
PAYROLL_INGENIEUR_CATEGORY_NAME = "Salaire Ingénieurs"

class Budget(BaseModel):
    """A site's spending envelope for a fixed period. One Budget per Site
    (OneToOneField) — Expense.clean() and .approve() check against it when
    an expense's status is set to APPROVED, so a site with no Budget has no
    spending cap enforced at all (budgets are optional, not implicitly
    created)."""
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='budget')
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    
    def __str__(self):
        return f"Budget for {self.site.name}: {self.total_amount}"
    
    def is_budget_period_active(self, check_date=None):
        """Check if the budget period is active on given date."""
        from django.utils import timezone
        if check_date is None:
            check_date = timezone.localdate()
        return self.start_date <= check_date <= self.end_date
    
    def get_spent_amount(self):
        """Get total spent amount within budget period (approved/paid expenses).

        Filters by expense_date (date the expense was incurred), not created_at,
        so that expenses submitted in one period but incurred in another are
        correctly attributed.
        """
        return self.site.expenses.filter(
            status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID],
            expense_date__gte=self.start_date,
            expense_date__lte=self.end_date,
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    def get_remaining_amount(self):
        """Get remaining budget amount."""
        from decimal import Decimal
        spent = self.get_spent_amount()
        return self.total_amount - Decimal(spent)

    def is_budget_exceeded(self, amount=0):
        """Check if budget would be exceeded with additional amount."""
        from decimal import Decimal
        remaining = self.get_remaining_amount()
        return Decimal(amount) > remaining

class ExpenseCategory(BaseModel):
    """A classification tag for an Expense (e.g. "Matériaux", "Transport").
    Managed from Django admin; referenced by name from reports and the
    expense form's dropdown."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Expense Categories"

    def __str__(self):
        return self.name

class Expense(BaseModel):
    """A single spend request against a Site, going through
    PENDING -> APPROVED -> PAID (or REJECTED from PENDING, or REJECTED from
    APPROVED) — see clean() for the enforced transition table and the
    budget-cap check, and approve()/reject()/pay() for the user-facing
    actions. Self-approval (approving your own request) is blocked in
    approve() for everyone except a superuser."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='expenses')
    phase = models.ForeignKey(
        ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses',
        verbose_name=_('Étape'), help_text=_("Étape du projet concernée par cette dépense (optionnel)"),
    )
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='requested_expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    nature = models.CharField(
        max_length=20, choices=ExpenseNature.choices, default=ExpenseNature.MATERIEL,
        verbose_name=_("Matériel ou main d'œuvre"),
        help_text=_("Cette dépense couvre-t-elle un achat de matériel ou de la main d'œuvre ?"),
    )
    personnel = models.ForeignKey(
        'personnel.Personnel', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses',
        verbose_name=_("Personnel concerné"),
        help_text=_("Pour une dépense de main d'œuvre : le personnel enregistré sur ce chantier concerné par cette dépense"),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField(help_text=_("Date the expense was incurred (used for budget period matching)"))
    description = models.TextField(verbose_name=_('Désignation'))
    recipient = models.CharField(
        max_length=255, blank=True, verbose_name=_('Bénéficiaire'),
        help_text=_("Qui a reçu ce paiement (fournisseur, ouvrier, tiers...) — pour la traçabilité, pas forcément une fiche du système."),
    )
    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.PENDING)
    receipt_image = models.ImageField(upload_to=FileUploadConfig.EXPENSE_RECEIPT_PATH, blank=True, null=True)

    def clean(self):
        """Enforces, in one place so no write path (view, admin, shell) can
        bypass it: a positive amount, that a "main d'œuvre" personnel link
        is actually assigned to this site and eligible, the PENDING ->
        APPROVED/REJECTED -> PAID/REJECTED transition table, and — only
        when transitioning TO or already APPROVED and the site has a
        Budget — that the budget period is active and this expense's
        amount fits what remains (see the amount_to_check delta logic
        below for the APPROVED-editing case)."""
        from django.core.exceptions import ValidationError
        from decimal import Decimal

        # Validate positive amount (None means the amount field itself already
        # failed form-level validation and is excluded from clean_fields())
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Amount must be a positive number.'})

        # A "main d'œuvre" personnel link only makes sense for that person's
        # own project — otherwise the searchable dropdown (scoped to the
        # site's active assignments in the form) could still be bypassed by
        # posting an arbitrary personnel id directly.
        if self.personnel_id and self.site_id:
            if not self.personnel.assignments.filter(site_id=self.site_id).exists():
                raise ValidationError({
                    'personnel': _("Ce membre du personnel n'est pas affecté à ce chantier."),
                })
            if not self.personnel.is_eligible:
                raise ValidationError({
                    'personnel': _(
                        "%(name)s n'est pas éligible (statut : %(status)s)."
                    ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
                })

        # Validate status transition
        original = None
        if self.pk:  # Only if updating existing expense
            original = Expense.objects.get(pk=self.pk)
            # PENDING → APPROVED | REJECTED
            # APPROVED → PAID | REJECTED
            # REJECTED and PAID are terminal states
            valid_transitions = {
                ExpenseStatus.PENDING: [ExpenseStatus.APPROVED, ExpenseStatus.REJECTED],
                ExpenseStatus.APPROVED: [ExpenseStatus.PAID, ExpenseStatus.REJECTED],
                ExpenseStatus.REJECTED: [],
                ExpenseStatus.PAID: [],
            }

            if original.status != self.status:  # Only check on actual transition
                allowed = valid_transitions.get(original.status, [])
                if self.status not in allowed:
                    raise ValidationError({
                        'status': f'Cannot transition from {original.status} to {self.status}.'
                    })

        # Validate against budget if expense is being approved
        if self.status == ExpenseStatus.APPROVED and hasattr(self.site, 'budget'):
            budget = self.site.budget
            if not budget.is_budget_period_active():
                raise ValidationError({
                    'status': 'Budget period is not active for this expense.'
                })

            # Check if this expense would exceed budget.
            # Only subtract original.amount when it was already APPROVED (i.e. already
            # counted in get_spent_amount()). PENDING expenses are not counted, so we
            # check the full self.amount when transitioning PENDING → APPROVED.
            amount_to_check = self.amount
            if original and original.status == ExpenseStatus.APPROVED:
                # Delta only: original.amount is already in get_spent_amount()
                amount_to_check = self.amount - original.amount
            
            if budget.is_budget_exceeded(amount_to_check):
                remaining = budget.get_remaining_amount()
                raise ValidationError({
                    'amount': f'Budget exceeded. Remaining budget: {remaining}. This expense is {self.amount}.'
                })
    
    def approve(self, user, comments=""):
        """PENDING -> APPROVED, recording an ExpenseApproval row. Blocks
        self-approval (requester approving their own request) for every
        role except a superuser — see docs/security.md's "self-approval"
        note. Locks the site's Budget row first (select_for_update) so two
        concurrent approvals on the same site can't both pass the
        budget-cap check in clean() and jointly overrun it."""
        from django.core.exceptions import ValidationError
        if not user.is_superuser and self.requester_id == user.pk:
            raise ValidationError(_("You cannot approve your own expense request."))
        with transaction.atomic():
            # Lock the budget row to serialize concurrent approvals and prevent budget overruns.
            if hasattr(self.site, 'budget'):
                Budget.objects.select_for_update().get(site=self.site)
            self.status = ExpenseStatus.APPROVED
            self.full_clean()
            self.save()
            ExpenseApproval.objects.create(
                expense=self,
                approver=user,
                status=ExpenseApproval.Status.APPROVED,
                comments=comments
            )

    def reject(self, user, comments=""):
        """PENDING -> REJECTED, recording an ExpenseApproval row. Unlike
        approve(), this has no self-rejection guard — rejecting your own
        request has no money-movement consequence, so it isn't gated."""
        with transaction.atomic():
            self.status = ExpenseStatus.REJECTED
            self.full_clean()
            self.save()
            ExpenseApproval.objects.create(
                expense=self,
                approver=user,
                status=ExpenseApproval.Status.REJECTED,
                comments=comments
            )
    
    def can_be_paid(self):
        """Check if expense can be marked as paid."""
        return self.status == ExpenseStatus.APPROVED

    @transaction.atomic
    def pay(self, user, caisse):
        """Mark this expense as PAID and record the matching outflow on the
        given caisse, atomically — mirrors PayrollList.disburse(). Before
        this, marking an expense PAID never touched any Caisse, so paid
        expenses were invisible in the livre de caisse; now every payout
        actually leaves the ledger it came from and shows up on
        CaisseTransaction.expense."""
        from django.core.exceptions import ValidationError
        if not self.can_be_paid():
            raise ValidationError(_("Seules les dépenses approuvées peuvent être payées."))
        if self.amount > caisse.balance:
            raise ValidationError(_("Solde de caisse insuffisant pour payer cette dépense."))
        caisse.record(
            CaisseTransactionType.SORTIE, self.amount, user,
            site=self.site, phase=self.phase, expense=self,
            description=_("Paiement dépense — %(desc)s") % {'desc': self.description[:80]},
        )
        self.status = ExpenseStatus.PAID
        self.full_clean()
        self.save()

    @property
    def latest_approval(self):
        """The most recent approve/reject decision on this expense, if any
        — the audit trail behind the "who approved this" question, kept
        as its own ExpenseApproval record (with date + comments) rather
        than a single denormalized field, since a rejected-then-resubmitted
        expense can go through this more than once."""
        return self.approvals.order_by('-approval_date').first()

    @property
    def approved_by(self):
        """The user who approved this expense, or None if it isn't
        (yet) approved — what the director/accountant actually asks for."""
        approval = self.approvals.filter(status=ExpenseApproval.Status.APPROVED).order_by('-approval_date').first()
        return approval.approver if approval else None

    def __str__(self):
        return f"{self.amount} - {self.category} ({self.status})"

class ExpenseApproval(BaseModel):
    """One approve/reject decision on an Expense — the audit trail entry
    created by Expense.approve()/reject(). An expense can accumulate more
    than one of these if it's rejected and later resubmitted, so this is
    never updated in place."""
    class Status(models.TextChoices):
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    approval_date = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(blank=True)

    def __str__(self):
        return f"{self.status} by {self.approver} on {self.approval_date}"


# ---------------------------------------------------------------------
# Caisse (cash register) ledger — balance-tracked, unlike the plain
# CaisseType tag on procurement.PurchaseOrder. Covers: "Générer un livre
# de caisse quotidien", "gestion de caisse", inter-caisse loans that must
# be repaid, and the daily transfer to the "caisse de gestion administrative".
# ---------------------------------------------------------------------

class Caisse(BaseModel):
    """A physical/logical cash register whose balance is derived live from
    its CaisseTransaction rows (see `balance`) rather than stored — so
    there is no counter to drift out of sync, but it also means `record()`
    (and anything that calls it) does not itself enforce a non-negative
    result; callers (views, `pay()`, `disburse()`, `transfer_to()`) are
    expected to check `amount <= self.balance` first."""
    cabinet = models.ForeignKey('accounts.Cabinet', on_delete=models.CASCADE, related_name='caisses')
    name = models.CharField(max_length=150, verbose_name=_('Nom'))
    caisse_type = models.CharField(max_length=20, choices=CaisseType.choices, default=CaisseType.SECONDAIRE, verbose_name=_('Type'))
    site = models.ForeignKey(
        Site, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisses',
        verbose_name=_('Chantier'), help_text=_("Optionnel : caisse dédiée à un projet (ex: location d'engins)."),
    )
    is_administrative = models.BooleanField(
        default=False, verbose_name=_('Caisse de gestion administrative'),
        help_text=_("La caisse vers laquelle les autres caisses transfèrent leurs recettes quotidiennes."),
    )
    manual_site_entry = models.BooleanField(
        default=False, verbose_name=_('Chantier saisi manuellement (clients externes)'),
        help_text=_(
            "Pour une caisse qui sert aussi des clients externes (ex : location de la bétonnière) : "
            "sur cette caisse, le formulaire de mouvement demande un chantier/client en texte libre "
            "au lieu d'imposer un chantier interne."
        ),
    )

    class Meta:
        ordering = ['-is_administrative', 'name']

    def __str__(self):
        return self.name

    @property
    def balance(self):
        """Current balance: sum of ENTREE transactions minus sum of SORTIE
        transactions, computed live (not cached) so a soft-deleted
        transaction (excluded by the default manager) or an edit is always
        reflected without a separate reconciliation step."""
        agg = self.transactions.aggregate(
            entrees=models.Sum('amount', filter=models.Q(transaction_type=CaisseTransactionType.ENTREE)),
            sorties=models.Sum('amount', filter=models.Q(transaction_type=CaisseTransactionType.SORTIE)),
        )
        return (agg['entrees'] or 0) - (agg['sorties'] or 0)

    def record(self, transaction_type, amount, user, description='', date=None, site=None, phase=None,
               expense=None, proof=None, recipient='', category=None, external_site_label=''):
        """Create a single ledger entry. Use transfer_to()/CaisseLoan for
        moves between two caisses so both legs are created atomically."""
        from django.utils import timezone as _tz
        return CaisseTransaction.objects.create(
            caisse=self,
            transaction_type=transaction_type,
            amount=amount,
            date=date or _tz.localdate(),
            description=description,
            site=site,
            phase=phase,
            expense=expense,
            proof=proof,
            recorded_by=user,
            recipient=recipient,
            category=category,
            external_site_label=external_site_label,
        )

    @transaction.atomic
    def transfer_to(self, target_caisse, amount, user, description=''):
        """Move funds from this caisse to another (e.g. the daily remittance
        to the caisse de gestion administrative). Not a loan — no repayment
        is tracked; use CaisseLoan.lend() when repayment is expected."""
        if target_caisse.pk == self.pk:
            raise ValueError(_("La caisse de destination doit être différente."))
        out_tx = self.record(CaisseTransactionType.SORTIE, amount, user, description=description)
        in_tx = target_caisse.record(CaisseTransactionType.ENTREE, amount, user, description=description)
        return out_tx, in_tx


class CaisseTransactionCategory(BaseModel):
    """A filterable tag for what a caisse movement was for (entrée or
    sortie) — separate from ExpenseCategory, which only classifies
    Dépenses. Managed from Django admin, like ExpenseCategory."""
    name = models.CharField(max_length=100, verbose_name=_('Nom'))
    description = models.TextField(blank=True, verbose_name=_('Description'))

    class Meta:
        verbose_name_plural = 'Caisse Transaction Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class CaisseTransaction(BaseModel):
    """One ledger entry (entrée or sortie) on a Caisse. Created either
    directly (manual movement, via CaisseTransactionCreateView/form, which
    does run clean() through the ModelForm) or through Caisse.record()
    (used by Expense.pay(), PayrollList/SalaryPaymentList.disburse(),
    transfer_to(), CaisseLoan.disburse()/repay()) — record() uses
    .objects.create() directly and does not call full_clean(), so those
    programmatic paths rely on the caller having already validated the
    amount (clean() below is only reached via the manual-entry form path).
    Soft-deletable like every BaseModel; Caisse.balance simply excludes
    deleted rows from its aggregate, so deleting a transaction tied to a
    paid Expense/PayrollList/CaisseLoan changes the caisse's balance
    without reverting that other record's own PAID/PAYEE status or
    repaid_amount — see the finance module notes for this gap."""
    caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=CaisseTransactionType.choices, verbose_name=_('Type'))
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Montant'))
    date = models.DateField(verbose_name=_('Date'))
    description = models.CharField(max_length=255, blank=True, verbose_name=_('Description'))
    site = models.ForeignKey(
        Site, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions', verbose_name=_('Chantier'),
        help_text=_("Chantier interne. Laisser vide et utiliser le champ texte libre pour un client externe (ex : Bétonnière)."),
    )
    external_site_label = models.CharField(
        max_length=255, blank=True, verbose_name=_('Chantier / Client (texte libre)'),
        help_text=_("Pour les caisses à clients externes : nom du chantier ou du client tel que communiqué, sans lien vers un chantier interne."),
    )
    phase = models.ForeignKey(ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions', verbose_name=_('Étape'))
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions')
    recipient = models.CharField(
        max_length=255, blank=True, verbose_name=_('Bénéficiaire'),
        help_text=_("Qui a reçu ou remis ce montant — pour la traçabilité, pas forcément une fiche du système."),
    )
    category = models.ForeignKey(
        CaisseTransactionCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions', verbose_name=_('Catégorie'),
    )
    proof = models.FileField(upload_to='caisse/proofs/', null=True, blank=True, verbose_name=_('Justificatif'))
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='caisse_transactions_recorded')

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        sign = '+' if self.transaction_type == CaisseTransactionType.ENTREE else '-'
        return f"{self.caisse} {sign}{self.amount} ({self.date})"

    def clean(self):
        """Only checked when a CaisseTransaction is saved through a
        ModelForm (full_clean() runs there) — see the class docstring for
        why the programmatic record()-based paths skip this."""
        from django.core.exceptions import ValidationError
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': _('Le montant doit être positif.')})


class CaisseLoan(BaseModel):
    """A cash advance from one caisse to another that must be repaid — e.g.
    the equipment-rental caisse lending to the main site caisse."""
    lender_caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='loans_given')
    borrower_caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='loans_received')
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Montant prêté'))
    date = models.DateField(verbose_name=_('Date du prêt'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    repaid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name=_('Montant remboursé'))
    lend_transaction = models.ForeignKey(CaisseTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    receive_transaction = models.ForeignKey(CaisseTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.lender_caisse} → {self.borrower_caisse}: {self.amount} ({self.date})"

    def clean(self):
        """Same-caisse and positive-amount guards, plus a lender-solvency
        check that only runs `and not self.pk` (creation only) — see the
        inline comment below for why that's deliberate and not a gap."""
        from django.core.exceptions import ValidationError
        if self.lender_caisse_id and self.borrower_caisse_id and self.lender_caisse_id == self.borrower_caisse_id:
            raise ValidationError(_("La caisse prêteuse et la caisse emprunteuse doivent être différentes."))
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': _('Le montant doit être positif.')})
        if self.amount is not None and self.lender_caisse_id and not self.pk:
            # Only checked on creation — a loan is disbursed immediately
            # once created (see disburse()), so this is the one moment that
            # matters: the lender caisse must actually hold the funds.
            if self.amount > self.lender_caisse.balance:
                raise ValidationError({'amount': _(
                    "Solde insuffisant sur %(caisse)s : solde disponible %(balance)s, montant demandé %(amount)s."
                ) % {'caisse': self.lender_caisse, 'balance': self.lender_caisse.balance, 'amount': self.amount}})

    @property
    def outstanding_balance(self):
        """Amount still owed by the borrower caisse."""
        return self.amount - self.repaid_amount

    @property
    def is_fully_repaid(self):
        """True once repaid_amount has caught up with the original loan
        amount (repay() never allows it to exceed that)."""
        return self.repaid_amount >= self.amount

    @transaction.atomic
    def disburse(self, user):
        """Move the loaned amount from lender to borrower and record the
        paired ledger entries on the loan itself."""
        out_tx = self.lender_caisse.record(
            CaisseTransactionType.SORTIE, self.amount, user,
            description=_("Prêt à %(caisse)s") % {'caisse': self.borrower_caisse},
        )
        in_tx = self.borrower_caisse.record(
            CaisseTransactionType.ENTREE, self.amount, user,
            description=_("Prêt reçu de %(caisse)s") % {'caisse': self.lender_caisse},
        )
        self.lend_transaction = out_tx
        self.receive_transaction = in_tx
        self.save(update_fields=['lend_transaction', 'receive_transaction', 'updated_at'])

    @transaction.atomic
    def repay(self, amount, user):
        """Record a (possibly partial) repayment: borrower → lender."""
        from django.core.exceptions import ValidationError
        if amount <= 0:
            raise ValidationError(_("Le montant du remboursement doit être positif."))
        if self.repaid_amount + amount > self.amount:
            raise ValidationError(_("Le remboursement dépasse le montant restant dû."))
        self.borrower_caisse.record(
            CaisseTransactionType.SORTIE, amount, user,
            description=_("Remboursement à %(caisse)s") % {'caisse': self.lender_caisse},
        )
        self.lender_caisse.record(
            CaisseTransactionType.ENTREE, amount, user,
            description=_("Remboursement reçu de %(caisse)s") % {'caisse': self.borrower_caisse},
        )
        self.repaid_amount = self.repaid_amount + amount
        self.save(update_fields=['repaid_amount', 'updated_at'])


# ---------------------------------------------------------------------
# Progressive worker payroll — "l'archi reçoit les demandes de paiements
# venant des ouvriers, analyse dépendamment de l'avancement du projet et
# prépare une sorte de liste de paie à soumettre à la caisse et la caisse
# débourse l'argent aux ouvriers; chaque ouvrier signe pour accusé de
# réception (sur papier)."
# ---------------------------------------------------------------------

class PayrollList(BaseModel):
    """A site-scoped "liste de paie" for ouvriers: an engineer/director
    prepares a draft of who-gets-paid-what against progress, submits it,
    and a cashier/accountant/director disburses the whole list from one
    Caisse in a single action. BROUILLON -> SOUMISE -> PAYEE, each step
    gated by a distinct role set (see PAYROLL_PREPARE_ROLES /
    PAYROLL_DISBURSE_ROLES in finance/views.py) — the same roles can hold
    both gates, so there's no enforced separation between who prepares and
    who disburses a given list."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='payroll_lists')
    phase = models.ForeignKey(ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_lists')
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='payroll_lists_prepared')
    status = models.CharField(max_length=20, choices=PayrollListStatus.choices, default=PayrollListStatus.BROUILLON)
    notes = models.TextField(blank=True, verbose_name=_("Analyse de l'avancement"))
    caisse = models.ForeignKey('finance.Caisse', on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_lists')
    submitted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_lists_disbursed')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Liste de paie — {self.site.name} ({self.get_status_display()})"

    @property
    def total_amount(self):
        """Sum of this list's item amounts — what disburse() will move out
        of the chosen Caisse in one shot."""
        return self.items.aggregate(t=models.Sum('amount'))['t'] or 0

    def submit(self, user):
        """BROUILLON -> SOUMISE. Requires at least one item — an empty
        list can't be sent to the caisse for disbursement."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != PayrollListStatus.BROUILLON:
            raise ValidationError(_("Seule une liste en brouillon peut être soumise."))
        if not self.items.exists():
            raise ValidationError(_("Ajoutez au moins un ouvrier avant de soumettre."))
        self.status = PayrollListStatus.SOUMISE
        self.submitted_at = _tz.now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])

    @transaction.atomic
    def disburse(self, user, caisse):
        """SOUMISE -> PAYEE: records one or two SORTIE CaisseTransactions
        (ouvrier total and, as a legacy safety net, any ingénieur total —
        see the comment below) against `caisse` and stamps who/when. Checks
        `total > caisse.balance` up front, but this is not itself
        concurrency-safe the way Expense.approve() locks Budget — two
        disburse() calls racing against the same caisse could both pass
        this check before either's CaisseTransaction is written."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != PayrollListStatus.SOUMISE:
            raise ValidationError(_("Seule une liste soumise peut être décaissée."))
        total = self.total_amount
        if total <= 0:
            raise ValidationError(_("Le montant total doit être positif."))
        if total > caisse.balance:
            raise ValidationError(_("Solde de caisse insuffisant."))

        # Liste de paie is Main d'œuvre (Ouvrier) only — PayrollListItem.clean()
        # rejects Ingénieur/Staff personnel, so ingenieur_total should always
        # be 0 for lists created going forward. The split is kept here as a
        # safety net for any item that predates that guard (created via
        # .objects.create(), which bypasses clean()) so old/legacy data still
        # disburses correctly under its own category.
        ouvrier_total = self.items.filter(
            personnel__payroll_type=PersonnelPayrollType.OUVRIER
        ).aggregate(t=models.Sum('amount'))['t'] or 0
        ingenieur_total = self.items.filter(
            personnel__payroll_type=PersonnelPayrollType.INGENIEUR
        ).aggregate(t=models.Sum('amount'))['t'] or 0
        ouvrier_category = CaisseTransactionCategory.objects.filter(name=PAYROLL_OUVRIER_CATEGORY_NAME).first()
        ingenieur_category = CaisseTransactionCategory.objects.filter(name=PAYROLL_INGENIEUR_CATEGORY_NAME).first()

        if ouvrier_total > 0:
            caisse.record(
                CaisseTransactionType.SORTIE, ouvrier_total, user, site=self.site, phase=self.phase,
                category=ouvrier_category,
                description=_("Paiement liste de paie (main d'œuvre) — %(site)s") % {'site': self.site.name},
            )
        if ingenieur_total > 0:
            caisse.record(
                CaisseTransactionType.SORTIE, ingenieur_total, user, site=self.site, phase=self.phase,
                category=ingenieur_category,
                description=_("Paiement liste de paie (ingénieurs) — %(site)s") % {'site': self.site.name},
            )
        self.status = PayrollListStatus.PAYEE
        self.caisse = caisse
        self.paid_at = _tz.now()
        self.paid_by = user
        self.save(update_fields=['status', 'caisse', 'paid_at', 'paid_by', 'updated_at'])


class PayrollListItem(BaseModel):
    """One ouvrier's line on a PayrollList. clean() enforces: positive
    amount, the personnel is eligible, personnel.payroll_type is OUVRIER
    (Ingénieurs/Staff are rejected — see SalaryPaymentItem instead), the
    assignment (if any) belongs to this personnel, and — when the
    assignment has a convention_amount cap — that this amount plus whatever
    was already paid against that convention doesn't exceed the cap."""
    payroll_list = models.ForeignKey(PayrollList, on_delete=models.CASCADE, related_name='items')
    personnel = models.ForeignKey('personnel.Personnel', on_delete=models.CASCADE, related_name='payroll_items')
    assignment = models.ForeignKey(
        'personnel.SiteAssignment', on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_items',
        verbose_name=_('Convention / affectation'),
        help_text=_("La convention (SiteAssignment) précise que ce paiement couvre — permet le plafond par convention et le rapprochement déjà payé/reste à payer."),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    progress_note = models.TextField(blank=True, verbose_name=_("Avancement / justification"))
    signed_receipt = models.FileField(
        upload_to='payroll/receipts/', null=True, blank=True,
        verbose_name=_('Accusé de réception signé'),
        help_text=_("Scan du reçu papier signé par l'ouvrier."),
    )

    class Meta:
        ordering = ['personnel__last_name']

    def __str__(self):
        return f"{self.personnel} — {self.amount}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': _('Le montant doit être positif.')})
        if self.personnel_id and not self.personnel.is_eligible:
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'est pas éligible (statut : %(status)s) et ne peut pas être payé(e)."
                ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
            })
        # Liste de paie (chantier-scoped) is Main d'œuvre only — Ingénieurs
        # et Staff sont payés via SalaryPaymentList (onglet "Ingénieurs & Staff"),
        # qui n'est pas rattaché à un chantier.
        if self.personnel_id and self.personnel.payroll_type != PersonnelPayrollType.OUVRIER:
            raise ValidationError({
                'personnel': _(
                    "%(name)s est payé(e) via la paie du personnel (Ingénieurs & Staff), "
                    "pas via la liste de paie d'un chantier."
                ) % {'name': self.personnel},
            })
        if self.assignment_id and self.personnel_id and self.assignment.personnel_id != self.personnel_id:
            raise ValidationError({
                'assignment': _("Cette convention n'appartient pas à ce membre du personnel."),
            })
        # The convention cap only applies to Ouvriers (main d'œuvre) — an
        # Ingénieur's Liste de paie payment is a plain salary line, not
        # capped against a per-task convention amount.
        if (
            self.assignment_id and self.personnel_id and self.amount is not None
            and self.personnel.payroll_type == PersonnelPayrollType.OUVRIER
            and self.assignment.convention_amount is not None
        ):
            already_paid = self.assignment.paid_amount
            if self.pk:
                # Editing an existing item: don't double-count its own
                # prior amount as "already paid" against itself.
                prior = PayrollListItem.all_objects.filter(pk=self.pk).values_list('amount', flat=True).first()
                already_paid -= (prior or 0)
            remaining = self.assignment.convention_amount - already_paid
            if self.amount > remaining:
                raise ValidationError({'amount': _(
                    "Ce montant dépasse le reste à payer sur la convention de %(name)s : "
                    "%(remaining)s restant sur %(total)s."
                ) % {
                    'name': self.personnel, 'remaining': remaining, 'total': self.assignment.convention_amount,
                }})


# ---------------------------------------------------------------------
# Paie du personnel — "Ingénieurs & Staff" tab: fixed monthly salaries for
# personnel with Personnel.payroll_type == INGENIEUR (engineers and
# administrative/office staff), not tied to any chantier. Mirrors
# PayrollList/PayrollListItem — the chantier-scoped "Main d'œuvre" tab
# reserved for Ouvriers (see PersonnelPayrollType and
# PayrollListItem.clean()) — but scoped by cabinet instead of by site,
# since Ingénieurs & Staff aren't attached to a chantier. Same
# brouillon -> soumise -> payée workflow: an engineer/staff member is
# added to a draft list, the list is submitted, and the cashier/finance
# team décaisse the whole list in one action.
# ---------------------------------------------------------------------

class SalaryPaymentList(BaseModel):
    """Cabinet-scoped "paie du personnel" for ingénieurs/staff — the
    counterpart to PayrollList, see ADR 0005 for why these are two separate
    models rather than one. Same BROUILLON -> SOUMISE -> PAYEE workflow and
    the same prepare/disburse role overlap caveat as PayrollList."""
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='salary_payment_lists')
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='salary_payment_lists_prepared',
    )
    status = models.CharField(max_length=20, choices=PayrollListStatus.choices, default=PayrollListStatus.BROUILLON)
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    caisse = models.ForeignKey(
        'finance.Caisse', on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_payment_lists',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_payment_lists_disbursed',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Paie du personnel — {self.cabinet.name} ({self.get_status_display()})"

    @property
    def total_amount(self):
        """Sum of this list's item amounts, disbursed as one outflow."""
        return self.items.aggregate(t=models.Sum('amount'))['t'] or 0

    def submit(self, user):
        """BROUILLON -> SOUMISE. Requires at least one item."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != PayrollListStatus.BROUILLON:
            raise ValidationError(_("Seule une liste en brouillon peut être soumise."))
        if not self.items.exists():
            raise ValidationError(_("Ajoutez au moins un agent avant de soumettre."))
        self.status = PayrollListStatus.SOUMISE
        self.submitted_at = _tz.now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])

    @transaction.atomic
    def disburse(self, user, caisse):
        """SOUMISE -> PAYEE: one SORTIE CaisseTransaction for the whole
        list's total, under the "Salaire Ingénieurs" category. Same
        non-concurrency-safe balance check as PayrollList.disburse()."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != PayrollListStatus.SOUMISE:
            raise ValidationError(_("Seule une liste soumise peut être décaissée."))
        total = self.total_amount
        if total <= 0:
            raise ValidationError(_("Le montant total doit être positif."))
        if total > caisse.balance:
            raise ValidationError(_("Solde de caisse insuffisant."))

        # Paie du personnel is Ingénieurs & Staff only — SalaryPaymentItem.clean()
        # rejects Ouvrier personnel, so this is always a single outflow under
        # the "Salaire Ingénieurs" category.
        category = CaisseTransactionCategory.objects.filter(name=PAYROLL_INGENIEUR_CATEGORY_NAME).first()
        caisse.record(
            CaisseTransactionType.SORTIE, total, user,
            category=category,
            description=_("Paie du personnel (ingénieurs & staff) — %(cabinet)s") % {'cabinet': self.cabinet.name},
        )
        self.status = PayrollListStatus.PAYEE
        self.caisse = caisse
        self.paid_at = _tz.now()
        self.paid_by = user
        self.save(update_fields=['status', 'caisse', 'paid_at', 'paid_by', 'updated_at'])


class SalaryPaymentItem(BaseModel):
    """One ingénieur/staff member's line on a SalaryPaymentList for a given
    `period` (AAAA-MM). clean() enforces: positive amount, valid period
    format, personnel is eligible, personnel.payroll_type is INGENIEUR
    (mirror image of PayrollListItem's OUVRIER-only guard), and the
    personnel belongs to the same cabinet as the list. unique_together on
    (personnel, period) prevents double-paying the same person for the same
    month across different lists."""
    salary_payment_list = models.ForeignKey(SalaryPaymentList, on_delete=models.CASCADE, related_name='items')
    personnel = models.ForeignKey(
        'personnel.Personnel', on_delete=models.CASCADE, related_name='salary_payment_items',
        verbose_name=_('Agent'),
    )
    period = models.CharField(
        max_length=7, verbose_name=_('Période (AAAA-MM)'),
        help_text=_("Mois concerné par ce paiement, ex : 2026-09"),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Montant'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        ordering = ['-period', 'personnel__last_name']
        unique_together = ('personnel', 'period')

    def __str__(self):
        return f"{self.personnel} — {self.period} — {self.amount}"

    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': _('Le montant doit être positif.')})
        if self.period and not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', self.period):
            raise ValidationError({'period': _("Format attendu : AAAA-MM (ex : 2026-09).")})
        if self.personnel_id and not self.personnel.is_eligible:
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'est pas éligible (statut : %(status)s) et ne peut pas être payé(e)."
                ) % {'name': self.personnel, 'status': self.personnel.get_status_display()},
            })
        # Mirror image of PayrollListItem.clean(): this flow is for
        # Ingénieurs & Staff only — Ouvriers are paid via the chantier-scoped
        # Liste de paie (Main d'œuvre tab) instead.
        if self.personnel_id and self.personnel.payroll_type != PersonnelPayrollType.INGENIEUR:
            raise ValidationError({
                'personnel': _(
                    "%(name)s est un(e) Ouvrier(ère) et doit être payé(e) via la liste de paie "
                    "d'un chantier (onglet Main d'œuvre), pas via la paie du personnel."
                ) % {'name': self.personnel},
            })
        if (
            self.personnel_id and self.salary_payment_list_id
            and self.personnel.cabinet_id != self.salary_payment_list.cabinet_id
        ):
            raise ValidationError({
                'personnel': _(
                    "%(name)s n'appartient pas au même cabinet que cette liste de paie."
                ) % {'name': self.personnel},
            })


# ---------------------------------------------------------------------
# Avenant (change order): authorizes spend beyond the initial budget,
# with the resulting overage recorded as client debt.
# ---------------------------------------------------------------------

class Avenant(BaseModel):
    """A change-order request authorizing spend beyond a site's initial
    budget: PENDING -> APPROVED (grows the site's Budget and the client's
    Contract.avenant_debt) or PENDING -> REJECTED (no side effects). Both
    are terminal — see approve()/reject().

    FIXED 2026-10-06: approve()/reject() now block self-decision the same
    way Expense.approve() does (see docs/security.md's "self-approval"
    note) — a requester can't decide their own avenant, bypassable only
    by a superuser. This does not remove the role overlap: a single
    director-tier role (DIRECTOR, DIRECTEUR_TECHNIQUE, DIRECTEUR_GENERAL)
    can still both request avenants (AVENANT_REQUEST_ROLES,
    finance/views.py) and decide them (FINAL_AUTHORIZATION_ROLES) — that
    overlap is unchanged and, in a single-director cabinet, intentional
    (mirrors the same accepted trade-off already made for Expense). What
    changed is that the *same person* can no longer be both the requester
    and the decider of one specific avenant; a second director-tier user,
    or CHIEF_ENGINEER/ACCOUNTANT requesting with a director deciding,
    still works exactly as before."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='avenants')
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Montant additionnel'))
    justification = models.TextField(verbose_name=_('Justification'))
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='avenants_requested')
    status = models.CharField(max_length=20, choices=AvenantStatus.choices, default=AvenantStatus.PENDING)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='avenants_decided')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Avenant {self.site.name}: +{self.amount} ({self.get_status_display()})"

    @transaction.atomic
    def approve(self, user, notes=''):
        """PENDING -> APPROVED: grows the site's Budget.total_amount by
        this avenant's amount and, if the site has a signed Contract, adds
        the same amount to Contract.avenant_debt (the client's extra debt
        for work authorized beyond the original contract price). Blocks
        self-approval (requester deciding their own avenant) for every
        role except a superuser — mirrors Expense.approve(); see the
        class docstring."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if not user.is_superuser and self.requested_by_id == user.pk:
            raise ValidationError(_("Vous ne pouvez pas décider de votre propre avenant."))
        if self.status != AvenantStatus.PENDING:
            raise ValidationError(_("Cet avenant a déjà été décidé."))
        if hasattr(self.site, 'budget'):
            budget = self.site.budget
            budget.total_amount = budget.total_amount + self.amount
            budget.save(update_fields=['total_amount', 'updated_at'])
        self.status = AvenantStatus.APPROVED
        self.decided_by = user
        self.decided_at = _tz.now()
        self.decision_notes = notes
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_notes', 'updated_at'])
        # The budget grows by the avenant amount, but that additional spend
        # was not part of what the client originally agreed to pay for —
        # it becomes debt owed by the client on top of the contract price.
        if hasattr(self.site, 'contract'):
            contract = self.site.contract
            contract.avenant_debt = (contract.avenant_debt or 0) + self.amount
            contract.save(update_fields=['avenant_debt', 'updated_at'])

    def reject(self, user, notes=''):
        """PENDING -> REJECTED. No budget/contract side effects. Blocks
        self-rejection the same way approve() blocks self-approval — see
        the class docstring; kept symmetric even though rejecting your
        own request has no money-movement consequence, since it's still
        a review step that should involve a second person."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if not user.is_superuser and self.requested_by_id == user.pk:
            raise ValidationError(_("Vous ne pouvez pas décider de votre propre avenant."))
        if self.status != AvenantStatus.PENDING:
            raise ValidationError(_("Cet avenant a déjà été décidé."))
        self.status = AvenantStatus.REJECTED
        self.decided_by = user
        self.decided_at = _tz.now()
        self.decision_notes = notes
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_notes', 'updated_at'])
