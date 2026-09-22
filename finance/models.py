from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site, ProjectPhase
from chantiermobile.constants import (
    ExpenseStatus, ExpenseNature, FileUploadConfig, CaisseType, CaisseTransactionType,
    PayrollListStatus, AvenantStatus,
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
    recipient = models.CharField(
        max_length=255, blank=True, verbose_name=_('Bénéficiaire'),
        help_text=_("Qui a reçu ce paiement (fournisseur, ouvrier, tiers...) — pour la traçabilité, pas forcément une fiche du système."),
    )
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


# ---------------------------------------------------------------------
# Progressive worker payroll — "l'archi reçoit les demandes de paiements
# venant des ouvriers, analyse dépendamment de l'avancement du projet et
# prépare une sorte de liste de paie à soumettre à la caisse et la caisse
# débourse l'argent aux ouvriers; chaque ouvrier signe pour accusé de
# réception (sur papier)."
# ---------------------------------------------------------------------

class PayrollList(BaseModel):
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
        return self.items.aggregate(t=models.Sum('amount'))['t'] or 0

    def submit(self, user):
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
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != PayrollListStatus.SOUMISE:
            raise ValidationError(_("Seule une liste soumise peut être décaissée."))
        total = self.total_amount
        if total <= 0:
            raise ValidationError(_("Le montant total doit être positif."))
        if total > caisse.balance:
            raise ValidationError(_("Solde de caisse insuffisant."))
        caisse.record(
            CaisseTransactionType.SORTIE, total, user, site=self.site, phase=self.phase,
            description=_("Paiement liste de paie — %(site)s") % {'site': self.site.name},
        )
        self.status = PayrollListStatus.PAYEE
        self.caisse = caisse
        self.paid_at = _tz.now()
        self.paid_by = user
        self.save(update_fields=['status', 'caisse', 'paid_at', 'paid_by', 'updated_at'])


class PayrollListItem(BaseModel):
    payroll_list = models.ForeignKey(PayrollList, on_delete=models.CASCADE, related_name='items')
    personnel = models.ForeignKey('personnel.Personnel', on_delete=models.CASCADE, related_name='payroll_items')
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


# ---------------------------------------------------------------------
# Office/admin monthly salary payments — "enregistrer une sortie liée au
# chargé du bureau / paiement des salaires mensuels pour les ingénieurs
# et agents administratifs". Unlike PayrollList (progressive worker pay,
# always tied to one chantier), this covers Personnel.monthly_salary,
# which is cabinet-level, not site-level — so it draws straight from a
# caisse (typically the caisse de gestion administrative) rather than
# from a specific project's budget.
# ---------------------------------------------------------------------

class SalaryPayment(BaseModel):
    personnel = models.ForeignKey(
        'personnel.Personnel', on_delete=models.CASCADE, related_name='salary_payments',
        verbose_name=_('Agent'),
    )
    period = models.CharField(
        max_length=7, verbose_name=_('Période (AAAA-MM)'),
        help_text=_("Mois concerné par ce paiement, ex : 2026-09"),
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Montant'))
    caisse = models.ForeignKey(Caisse, on_delete=models.PROTECT, related_name='salary_payments', verbose_name=_('Caisse'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='salary_payments_disbursed',
    )

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

    @transaction.atomic
    def disburse(self, user):
        """Record the caisse outflow for this salary payment. Called once,
        right when the payment is created — office salaries are a single
        cabinet-level outflow, not a multi-worker list built up over time
        like PayrollList, so there's no separate draft/submit stage."""
        from django.core.exceptions import ValidationError
        if self.amount > self.caisse.balance:
            raise ValidationError(_("Solde de caisse insuffisant."))
        self.caisse.record(
            CaisseTransactionType.SORTIE, self.amount, user,
            description=_("Salaire %(period)s — %(personnel)s") % {'period': self.period, 'personnel': self.personnel},
        )
        self.paid_by = user
        self.save(update_fields=['paid_by', 'updated_at'])


# ---------------------------------------------------------------------
# Avenant (change order): authorizes spend beyond the initial budget,
# with the resulting overage recorded as client debt.
# ---------------------------------------------------------------------

class Avenant(BaseModel):
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
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
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
        from django.core.exceptions import ValidationError
        from django.utils import timezone as _tz
        if self.status != AvenantStatus.PENDING:
            raise ValidationError(_("Cet avenant a déjà été décidé."))
        self.status = AvenantStatus.REJECTED
        self.decided_by = user
        self.decided_at = _tz.now()
        self.decision_notes = notes
        self.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_notes', 'updated_at'])
