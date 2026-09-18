from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from projects.models import Site
from chantiermobile.constants import PriceItemType, DQEStatus


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


class DQE(BaseModel):
    """
    Détail Quantitatif Estimatif — a bill of quantities built from lines that
    reference the Bibliothèque de Prix, used to estimate the total cost of a
    project (or a phase of it) before it becomes a Devis.
    """
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='dqes')
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, null=True, blank=True, related_name='dqes', verbose_name=_('Chantier'))
    reference = models.CharField(max_length=100, verbose_name=_('Référence'), help_text=_('ex. DQE-2025-001'))
    title = models.CharField(max_length=255, verbose_name=_('Intitulé'))
    status = models.CharField(max_length=20, choices=DQEStatus.choices, default=DQEStatus.DRAFT, verbose_name=_('Statut'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('DQE')
        verbose_name_plural = _('DQE')
        unique_together = ('cabinet', 'reference')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.title}"

    @property
    def total_amount(self):
        from decimal import Decimal
        return sum((line.line_total for line in self.lines.all()), Decimal('0'))

    @property
    def total_lines(self):
        return self.lines.count()


class DQELine(BaseModel):
    """A single quantified line of a DQE, priced from a Bibliothèque de Prix item."""
    dqe = models.ForeignKey(DQE, on_delete=models.CASCADE, related_name='lines')
    price_item = models.ForeignKey(PriceLibraryItem, on_delete=models.PROTECT, related_name='dqe_lines', verbose_name=_('Article'))
    designation = models.CharField(max_length=255, blank=True, verbose_name=_('Désignation'), help_text=_("Laisser vide pour utiliser la désignation du catalogue"))
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Quantité'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('Prix unitaire'), help_text=_("Copié depuis la bibliothèque de prix au moment de l'ajout ; modifiable pour ce DQE"))
    order = models.PositiveIntegerField(default=0, verbose_name=_('Ordre'))

    class Meta:
        verbose_name = _('Ligne de DQE')
        verbose_name_plural = _('Lignes de DQE')
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.quantity} x {self.display_designation}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': _('La quantité doit être un nombre positif.')})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': _('Le prix unitaire ne peut pas être négatif.')})

    @property
    def display_designation(self):
        return self.designation or self.price_item.designation

    @property
    def unit(self):
        return self.price_item.unit

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)
