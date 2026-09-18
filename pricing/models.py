from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from chantiermobile.constants import PriceItemType


class PriceLibraryItem(BaseModel):
    """
    Bibliothèque de Prix — a reusable catalog of unit prices (labor, materials,
    equipment, services, composite work items) that a cabinet maintains and
    reuses across DQEs and Devis instead of re-pricing every project from
    scratch.
    """
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='price_library_items')
    code = models.CharField(max_length=30, verbose_name=_('Code'), help_text=_('Identifiant court, ex. MO-001, MAT-012'))
    designation = models.CharField(max_length=255, verbose_name=_('Désignation'))
    item_type = models.CharField(max_length=20, choices=PriceItemType.choices, default=PriceItemType.WORK_ITEM, verbose_name=_('Type'))
    unit = models.CharField(max_length=50, verbose_name=_('Unité'), help_text=_('ex. m², m³, kg, forfait, jour'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Prix unitaire'))
    is_active = models.BooleanField(default=True, verbose_name=_('Actif'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Article de la bibliothèque de prix')
        verbose_name_plural = _('Bibliothèque de prix')
        unique_together = ('cabinet', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.designation} ({self.unit_price}/{self.unit})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': _('Le prix unitaire ne peut pas être négatif.')})
