from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site
from chantiermobile.constants import MaterialRequestStatus

class Material(BaseModel):
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, help_text="e.g. kg, m3, liters")
    estimated_cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.unit})"

class MaterialRequest(BaseModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='material_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_requests')
    status = models.CharField(max_length=20, choices=MaterialRequestStatus.choices, default=MaterialRequestStatus.PENDING)
    notes = models.TextField(blank=True, null=True, help_text="Additional notes or instructions for this request")
    
    # Optional link to an expense if approved and purchased (aggregated)
    expense = models.OneToOneField('finance.Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='material_request')

    def __str__(self):
        item_count = self.items.count()
        return f"Request #{self.id} - {item_count} item{'s' if item_count != 1 else ''} for {self.site.name}"
    
    @property
    def total_items(self):
        """Get total number of material items in this request"""
        return self.items.count()
    
    @property
    def total_estimated_cost(self):
        """Calculate total estimated cost for all items"""
        from django.db.models import F, Sum
        result = self.items.aggregate(
            total=Sum(F('material__estimated_cost_per_unit') * F('quantity'), 
                     output_field=models.DecimalField())
        )
        return result['total'] or 0


class MaterialRequestItem(BaseModel):
    """Represents a single material item within a request"""
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='request_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True, help_text="Notes specific to this material item")

    class Meta:
        verbose_name = "Material Request Item"
        verbose_name_plural = "Material Request Items"
        unique_together = ('request', 'material')  # Prevent duplicate materials in same request

    def __str__(self):
        return f"{self.quantity} {self.material.unit} of {self.material.name}"
    
    @property
    def estimated_cost(self):
        """Calculate estimated cost for this item"""
        if self.material.estimated_cost_per_unit:
            return self.material.estimated_cost_per_unit * self.quantity
        return 0
