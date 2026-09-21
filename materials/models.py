from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from core.models import BaseModel
from projects.models import Site
from chantiermobile.constants import MaterialRequestStatus

class Material(BaseModel):
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, help_text=_("e.g. kg, m3, liters"))
    estimated_cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.unit})"

class MaterialRequest(BaseModel):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='material_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='material_requests')
    status = models.CharField(max_length=20, choices=MaterialRequestStatus.choices, default=MaterialRequestStatus.PENDING)
    notes = models.TextField(blank=True, null=True, help_text=_("Additional notes or instructions for this request"))
    
    # Optional link to an expense if approved and purchased (aggregated)
    expense = models.OneToOneField('finance.Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='material_request')

    def __str__(self):
        item_count = self.items.count()
        return f"Request #{self.id} - {item_count} item{'s' if item_count != 1 else ''} for {self.site.name}"
    
    def clean(self):
        """Validate material request data."""
        from django.core.exceptions import ValidationError
        
        # Validate that request has items
        if self.pk and self.items.count() == 0:
            raise ValidationError('Material request must have at least one item.')
    
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
    """Represents a single material item within a request.

    `material` links to the catalog when the item is already registered
    there. When it isn't (a one-off or not-yet-catalogued item), the
    requester can instead type a name directly into `material_name` —
    exactly one of the two must be set (see clean())."""
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='request_items', null=True, blank=True)
    material_name = models.CharField(
        max_length=255, blank=True,
        verbose_name=_('Nom du matériel'),
        help_text=_("À utiliser si le matériel n'est pas dans le catalogue"),
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True, help_text=_("Notes specific to this material item"))

    class Meta:
        verbose_name = "Material Request Item"
        verbose_name_plural = "Material Request Items"
        # NULL is never equal to NULL in a SQL unique constraint, so this
        # only blocks adding the *same catalog material* twice to a
        # request — free-text rows (material IS NULL) are never affected.
        unique_together = ('request', 'material')

    def __str__(self):
        return f"{self.quantity} of {self.display_name}"

    @property
    def display_name(self):
        return self.material.name if self.material_id else self.material_name

    def clean(self):
        """Validate material request item."""
        from django.core.exceptions import ValidationError

        if not self.material_id and not self.material_name:
            raise ValidationError(_("Sélectionnez un matériel du catalogue ou indiquez son nom."))
        if self.material_id and self.material_name:
            raise ValidationError(_("Choisissez soit un matériel du catalogue, soit un nom libre — pas les deux."))

        # Validate quantity is positive
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({
                'quantity': 'Quantity must be a positive number.'
            })

    @property
    def estimated_cost(self):
        """Calculate estimated cost for this item (free-text items have no
        catalog price, so this is always 0 for them)."""
        if self.material_id and self.material.estimated_cost_per_unit:
            return self.material.estimated_cost_per_unit * self.quantity
        return 0
