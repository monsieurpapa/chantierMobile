from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from projects.models import Site

class Contract(BaseModel):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name='contract')
    client_name = models.CharField(max_length=255)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, help_text="Total contract value")
    signed_date = models.DateField()
    
    def __str__(self):
        return f"Contract for {self.site.name} - {self.client_name}"

class Invoice(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Brouillon')
        SENT = 'SENT', _('Envoyé')
        PAID = 'PAID', _('Payé')
        OVERDUE = 'OVERDUE', _('En retard')

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    issued_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.status})"

class Payment(BaseModel):
    class Method(models.TextChoices):
        BANK_TRANSFER = 'BANK_TRANSFER', _('Virement bancaire')
        CHECK = 'CHECK', _('Chèque')
        CASH = 'CASH', _('Espèces')
        MOBILE_MONEY = 'MOBILE_MONEY', _('Mobile Money')

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    method = models.CharField(max_length=50, choices=Method.choices)
    reference = models.CharField(max_length=100, blank=True, help_text="Transaction ID or Check Number")
    
    def __str__(self):
        return f"Payment of {self.amount} for {self.invoice.invoice_number}"
