from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from projects.models import Site
from chantiermobile.constants import InvoiceStatus, PaymentMethod

class Contract(BaseModel):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='contract')
    client_name = models.CharField(max_length=255)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, help_text=_("Total contract value"))
    signed_date = models.DateField()
    
    def __str__(self):
        return f"Contract for {self.site.name} - {self.client_name}"

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

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            self.invoice.check_and_mark_paid()

    def __str__(self):
        return f"Payment of {self.amount} for {self.invoice.invoice_number}"
