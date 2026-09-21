from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site, ProjectPhase
from chantiermobile.constants import (
    ExpenseStatus, ExpenseNature, FileUploadConfig, CaisseType, CaisseTransactionType,
)

class Budget(BaseModel):
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
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"

    def __str__(self):
        return self.name

class Expense(BaseModel):
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
    status = models.CharField(max_length=20, choices=ExpenseStatus.choices, default=ExpenseStatus.PENDING)
    receipt_image = models.ImageField(upload_to=FileUploadConfig.EXPENSE_RECEIPT_PATH, blank=True, null=True)

    def clean(self):
        """Validate expense data."""
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

    def __str__(self):
        return f"{self.amount} - {self.category} ({self.status})"

class ExpenseApproval(BaseModel):
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

    class Meta:
        ordering = ['-is_administrative', 'name']

    def __str__(self):
        return self.name

    @property
    def balance(self):
        agg = self.transactions.aggregate(
            entrees=models.Sum('amount', filter=models.Q(transaction_type=CaisseTransactionType.ENTREE)),
            sorties=models.Sum('amount', filter=models.Q(transaction_type=CaisseTransactionType.SORTIE)),
        )
        return (agg['entrees'] or 0) - (agg['sorties'] or 0)

    def record(self, transaction_type, amount, user, description='', date=None, site=None, phase=None, expense=None, proof=None):
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


class CaisseTransaction(BaseModel):
    caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=CaisseTransactionType.choices, verbose_name=_('Type'))
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Montant'))
    date = models.DateField(verbose_name=_('Date'))
    description = models.CharField(max_length=255, blank=True, verbose_name=_('Description'))
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions', verbose_name=_('Chantier'))
    phase = models.ForeignKey(ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions', verbose_name=_('Étape'))
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='caisse_transactions')
    proof = models.FileField(upload_to='caisse/proofs/', null=True, blank=True, verbose_name=_('Justificatif'))
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='caisse_transactions_recorded')

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        sign = '+' if self.transaction_type == CaisseTransactionType.ENTREE else '-'
        return f"{self.caisse} {sign}{self.amount} ({self.date})"

    def clean(self):
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
        from django.core.exceptions import ValidationError
        if self.lender_caisse_id and self.borrower_caisse_id and self.lender_caisse_id == self.borrower_caisse_id:
            raise ValidationError(_("La caisse prêteuse et la caisse emprunteuse doivent être différentes."))
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': _('Le montant doit être positif.')})

    @property
    def outstanding_balance(self):
        return self.amount - self.repaid_amount

    @property
    def is_fully_repaid(self):
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
