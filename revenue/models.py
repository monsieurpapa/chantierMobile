from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from projects.models import Site
from chantiermobile.constants import InvoiceStatus, PaymentMethod, DevisStatus, SituationStatus

class Contract(BaseModel):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='contract')
    client_name = models.CharField(max_length=255)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, help_text=_("Total contract value"))
    signed_date = models.DateField()
    avenant_debt = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        verbose_name=_('Dette avenants'),
        help_text=_("Dépenses au-delà du budget initial, autorisées par avenant : dette du client en plus du prix du contrat."),
    )

    def __str__(self):
        return f"Contract for {self.site.name} - {self.client_name}"

    @property
    def source_devis(self):
        """The accepted Devis this contract was created from, if any."""
        return self.site.devis_set.filter(status=DevisStatus.ACCEPTE).first()

    @property
    def total_paid(self):
        """Sum of all payments received across this contract's invoices."""
        return Payment.objects.filter(invoice__contract=self).aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    @property
    def client_balance(self):
        """What the client still owes: contract value (plus any avenant
        debt from budget overages the client authorized) minus what
        they've paid so far. Surfaced next to the site's (expense) budget
        so the cashier/director can see both sides — money owed by the
        client and money spent on the site — at a glance."""
        from decimal import Decimal
        return self.total_value + Decimal(self.avenant_debt) - Decimal(self.total_paid)

class Invoice(BaseModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    issued_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    
    def clean(self):
        """Validate invoice data and status transitions."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        # Validate dates
        if self.issued_date and self.due_date and self.due_date < self.issued_date:
            raise ValidationError({
                'due_date': 'Due date must be after issued date.'
            })
        
        # Validate amount is positive
        if self.amount <= 0:
            raise ValidationError({
                'amount': 'Amount must be positive.'
            })
        
        # Validate status transitions
        if self.pk:  # Only for updates
            original = Invoice.objects.get(pk=self.pk)
            
            valid_transitions = {
                InvoiceStatus.DRAFT: [InvoiceStatus.SENT, InvoiceStatus.CANCELLED],
                InvoiceStatus.SENT: [InvoiceStatus.PAID, InvoiceStatus.OVERDUE],
                InvoiceStatus.PAID: [],  # Final state
                InvoiceStatus.OVERDUE: [InvoiceStatus.PAID],
                InvoiceStatus.CANCELLED: [],  # Final state
            }
            
            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': f'Cannot transition invoice from {original.status} to {self.status}.'
                    })

    def check_and_mark_paid(self, changed_by=None):
        """Auto-transition SENT/OVERDUE → PAID once total payments cover the invoice amount.

        Called from Payment.save() so this fires regardless of entry point
        (view, admin, shell, management command) — not just the payment form.
        """
        if self.status not in [InvoiceStatus.SENT, InvoiceStatus.OVERDUE]:
            return
        total_paid = self.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        if total_paid >= self.amount:
            from core.models import StatusChangeLog
            old_status = self.status
            self.status = InvoiceStatus.PAID
            self.full_clean()
            self.save()
            StatusChangeLog.log(
                self,
                changed_by=changed_by,
                old_status=old_status,
                new_status=InvoiceStatus.PAID,
                note='Auto-marked PAID — full payment received.',
            )

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.status})"

class Payment(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=100, blank=True, help_text=_("Transaction ID or Check Number"))
    proof_of_payment = models.FileField(
        upload_to='payments/proofs/', blank=True, null=True,
        verbose_name=_('Preuve de paiement'),
        help_text=_('Reçu, capture de virement ou autre justificatif — facultatif'),
    )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.invoice.check_and_mark_paid()

    def __str__(self):
        return f"Payment of {self.amount} for {self.invoice.invoice_number}"


class Devis(BaseModel):
    """A quote/estimate sent to a client before work begins on a Site.

    A Site can have several Devis (revisions, or competing drafts) but only
    one may ever be accepted — accepting one creates the Site's Contract
    (which is a OneToOneField), so a second acceptance is blocked in clean().
    """
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='devis_set')
    devis_number = models.CharField(max_length=50, unique=True, verbose_name=_('Numéro de devis'))
    client_name = models.CharField(max_length=255, verbose_name=_('Client'))
    issue_date = models.DateField(verbose_name=_('Date d\'émission'))
    validity_date = models.DateField(null=True, blank=True, verbose_name=_('Valable jusqu\'au'))
    status = models.CharField(max_length=20, choices=DevisStatus.choices, default=DevisStatus.BROUILLON)
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    photo = models.ImageField(
        upload_to='devis/photos/', blank=True, null=True,
        verbose_name=_('Photo du devis'),
        help_text=_("Photo/scan d'un devis papier — alternative à la saisie manuelle des lignes ci-dessous"),
    )

    class Meta:
        verbose_name = _('Devis')
        verbose_name_plural = _('Devis')
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f"{self.devis_number} - {self.client_name} ({self.get_status_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.validity_date and self.issue_date and self.validity_date < self.issue_date:
            raise ValidationError({
                'validity_date': _('La date de validité doit être postérieure à la date d\'émission.')
            })

        if self.pk:
            original = Devis.objects.get(pk=self.pk)

            valid_transitions = {
                DevisStatus.BROUILLON: [DevisStatus.ENVOYE, DevisStatus.REFUSE],
                DevisStatus.ENVOYE: [DevisStatus.ACCEPTE, DevisStatus.REFUSE, DevisStatus.EXPIRE],
                DevisStatus.ACCEPTE: [],
                DevisStatus.REFUSE: [],
                DevisStatus.EXPIRE: [],
            }

            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': _('Impossible de passer le devis de %(old)s à %(new)s.') % {
                            'old': original.get_status_display(),
                            'new': self.get_status_display(),
                        }
                    })

    @property
    def total_ht(self):
        return self.lines.aggregate(total=models.Sum(
            models.F('quantity') * models.F('unit_price_ht'),
            output_field=models.DecimalField(max_digits=14, decimal_places=2)
        ))['total'] or 0

    @property
    def total_items(self):
        return self.lines.count()

    def accept_and_create_contract(self, changed_by=None):
        """Accept this Devis and create the Site's Contract from its total.

        Only valid from ENVOYE, and only if the Site has no Contract yet
        (Contract.site is a OneToOneField). Mirrors the audit-trail pattern
        used by Expense.approve()/Invoice.check_and_mark_paid().
        """
        from django.core.exceptions import ValidationError
        from core.models import StatusChangeLog
        from django.utils import timezone

        if self.status != DevisStatus.ENVOYE:
            raise ValidationError(_('Seul un devis envoyé peut être accepté.'))
        # Query fresh rather than trust self.site's cached reverse relation,
        # which can go stale within a single long-lived process/test run.
        if Contract.objects.filter(site_id=self.site_id).exists():
            raise ValidationError(_('Ce chantier possède déjà un contrat.'))

        contract = Contract.objects.create(
            site=self.site,
            client_name=self.client_name,
            total_value=self.total_ht,
            signed_date=timezone.localdate(),
        )

        old_status = self.status
        self.status = DevisStatus.ACCEPTE
        self.full_clean()
        self.save()
        StatusChangeLog.log(
            self,
            changed_by=changed_by,
            old_status=old_status,
            new_status=DevisStatus.ACCEPTE,
            note=_('Devis accepté — contrat créé automatiquement.'),
        )
        return contract


class DevisLine(BaseModel):
    """A single priced line item on a Devis (freeform, self-contained —
    mirrors DQELine's designation/unit/quantity/unit_price shape)."""
    devis = models.ForeignKey(Devis, on_delete=models.CASCADE, related_name='lines')
    order = models.PositiveIntegerField(default=0, verbose_name=_('Ordre'))
    designation = models.CharField(max_length=255, verbose_name=_('Désignation'))
    unit = models.CharField(max_length=20, verbose_name=_('Unité'))
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Quantité'))
    unit_price_ht = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Prix unitaire HT'))

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.designation} ({self.quantity} {self.unit})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': _('La quantité doit être positive.')})
        if self.unit_price_ht is not None and self.unit_price_ht < 0:
            raise ValidationError({'unit_price_ht': _('Le prix unitaire ne peut pas être négatif.')})

    @property
    def total_ht(self):
        if self.quantity is None or self.unit_price_ht is None:
            return 0
        return self.quantity * self.unit_price_ht


class SituationTravaux(BaseModel):
    """A periodic progress-billing statement (situation de travaux):
    tracks cumulative % completion per DevisLine on a signed Contract,
    and can generate an Invoice for the amount due this period."""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='situations')
    numero = models.PositiveIntegerField(verbose_name=_('N° de situation'))
    period_end_date = models.DateField(verbose_name=_('Arrêtée au'))
    status = models.CharField(max_length=20, choices=SituationStatus.choices, default=SituationStatus.BROUILLON)
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    invoice = models.OneToOneField(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='situation')

    class Meta:
        verbose_name = _('Situation de travaux')
        verbose_name_plural = _('Situations de travaux')
        unique_together = [('contract', 'numero')]
        ordering = ['contract', 'numero']

    def __str__(self):
        return f"Situation n°{self.numero} - {self.contract.site.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.pk:
            original = SituationTravaux.objects.get(pk=self.pk)

            valid_transitions = {
                SituationStatus.BROUILLON: [SituationStatus.VALIDEE],
                SituationStatus.VALIDEE: [SituationStatus.FACTUREE],
                SituationStatus.FACTUREE: [],
            }

            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': _('Impossible de passer la situation de %(old)s à %(new)s.') % {
                            'old': original.get_status_display(),
                            'new': self.get_status_display(),
                        }
                    })

    @property
    def total_ht_cumulative(self):
        return sum((line.cumulative_amount_ht for line in self.lines.all()), 0)

    @property
    def total_ht_period(self):
        return sum((line.period_amount_ht for line in self.lines.all()), 0)

    def generate_invoice(self, changed_by=None, due_in_days=30):
        """Validate this situation and generate the Invoice for the amount
        due this period. Mirrors Invoice.check_and_mark_paid()'s use of
        StatusChangeLog for the audit trail."""
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        from datetime import timedelta
        from core.models import StatusChangeLog

        if self.status != SituationStatus.VALIDEE:
            raise ValidationError(_('Seule une situation validée peut être facturée.'))

        amount = self.total_ht_period
        if amount <= 0:
            raise ValidationError(_('Le montant de la situation doit être positif pour générer une facture.'))

        today = timezone.localdate()
        invoice = Invoice.objects.create(
            contract=self.contract,
            invoice_number=f"SIT-{self.contract_id}-{self.numero}",
            amount=amount,
            issued_date=today,
            due_date=today + timedelta(days=due_in_days),
            status=InvoiceStatus.DRAFT,
        )

        old_status = self.status
        self.status = SituationStatus.FACTUREE
        self.invoice = invoice
        self.full_clean()
        self.save()
        StatusChangeLog.log(
            self,
            changed_by=changed_by,
            old_status=old_status,
            new_status=SituationStatus.FACTUREE,
            note=_('Facture %(num)s générée automatiquement.') % {'num': invoice.invoice_number},
        )
        return invoice


class SituationLine(BaseModel):
    """One DevisLine's cumulative advancement % on a given SituationTravaux."""
    situation = models.ForeignKey(SituationTravaux, on_delete=models.CASCADE, related_name='lines')
    devis_line = models.ForeignKey(DevisLine, on_delete=models.PROTECT, related_name='situation_lines')
    cumulative_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name=_('% cumulé d\'avancement')
    )

    class Meta:
        unique_together = [('situation', 'devis_line')]
        ordering = ['devis_line__order', 'id']

    def __str__(self):
        return f"{self.devis_line.designation} - {self.cumulative_percentage}%"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.cumulative_percentage is None:
            return
        if self.cumulative_percentage < 0 or self.cumulative_percentage > 100:
            raise ValidationError({
                'cumulative_percentage': _('Le pourcentage doit être compris entre 0 et 100.')
            })
        previous = self.previous_cumulative_percentage
        if self.cumulative_percentage < previous:
            raise ValidationError({
                'cumulative_percentage': _(
                    'Le pourcentage cumulé (%(new)s%%) ne peut pas être inférieur au précédent (%(old)s%%).'
                ) % {'new': self.cumulative_percentage, 'old': previous}
            })

    @property
    def previous_cumulative_percentage(self):
        """Most recent cumulative % recorded for this DevisLine on an
        earlier SituationTravaux of the same contract."""
        if not self.situation_id or not self.devis_line_id:
            return 0
        earlier = SituationLine.objects.filter(
            devis_line=self.devis_line,
            situation__contract_id=self.situation.contract_id,
            situation__numero__lt=self.situation.numero,
        ).order_by('-situation__numero').first()
        return earlier.cumulative_percentage if earlier else 0

    @property
    def period_percentage(self):
        return self.cumulative_percentage - self.previous_cumulative_percentage

    @property
    def cumulative_amount_ht(self):
        return self.devis_line.total_ht * (self.cumulative_percentage / 100)

    @property
    def period_amount_ht(self):
        return self.devis_line.total_ht * (self.period_percentage / 100)
