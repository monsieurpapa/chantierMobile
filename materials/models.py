from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site

class Material(BaseModel):
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, help_text="e.g. kg, m3, liters")
    estimated_cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.unit})"

class MaterialRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        ORDERED = 'ORDERED', _('Ordered')
        DELIVERED = 'DELIVERED', _('Delivered')

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='material_requests')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='requests')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_requests')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Optional link to an expense if approved and purchased
    expense = models.OneToOneField('finance.Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='material_request')

    def __str__(self):
        return f"{self.quantity} {self.material.unit} of {self.material.name} for {self.site.name}"
