"""
Pricing: the Bibliothèque de Prix (a cabinet's reusable unit-price
catalog) and the DQE (Détail Quantitatif Estimatif) built from it to
estimate a project's cost before it becomes a Devis (see revenue).

A DQELine copies its price_item's unit_price at the time it's added
(`unit_price` is stored on the line, not derived live), so a later edit
to the catalog price never silently reprices an existing DQE — the line
can still be adjusted by hand for that estimate.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from projects.models import Site, ProjectPhase
from materials.models import Material
from chantiermobile.constants import PriceItemType, DQEStatus, WorkCategory


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
    work_category = models.CharField(
        max_length=20, choices=WorkCategory.choices, blank=True, verbose_name=_('Catégorie d\'ouvrage'),
        help_text=_(
            "Obligatoire pour un article de type « Ouvrage (composite) » — indique à quelle "
            "nomenclature de ratios (ciment, acier, sable...) ce poste doit être rattaché pour "
            "l'explosion en matériaux élémentaires."
        ),
    )
    material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_library_items',
        verbose_name=_('Matériau'),
        help_text=_(
            "Pour un article de type « Matériau » : le matériau élémentaire correspondant, "
            "utilisé pour comparer directement ce poste du DQE aux demandes de matériaux "
            "(sans passer par une explosion de ratios)."
        ),
    )
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
        """Unit price must not be negative — zero is allowed (e.g. a
        "fourni par le client" line priced at 0). A WORK_ITEM must carry a
        work_category (needed to look up its MaterialConsumptionRatio
        rows); a non-WORK_ITEM shouldn't carry one, to avoid a stale
        category lingering after the type is changed."""
        from django.core.exceptions import ValidationError
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': _('Le prix unitaire ne peut pas être négatif.')})
        if self.item_type == PriceItemType.WORK_ITEM and not self.work_category:
            raise ValidationError({'work_category': _(
                "La catégorie d'ouvrage est obligatoire pour un article de type « Ouvrage (composite) »."
            )})
        if self.item_type != PriceItemType.WORK_ITEM and self.work_category:
            raise ValidationError({'work_category': _(
                "La catégorie d'ouvrage ne s'applique qu'aux articles de type « Ouvrage (composite) »."
            )})


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
        """Sums `line.line_total` in Python rather than a DB aggregate,
        since line_total itself is a property (quantity × unit_price),
        not a stored/annotatable column."""
        from decimal import Decimal
        return sum((line.line_total for line in self.lines.all()), Decimal('0'))

    @property
    def total_lines(self):
        """Number of DQELine rows on this DQE."""
        return self.lines.count()


class DQELine(BaseModel):
    """A single quantified line of a DQE, priced from a Bibliothèque de Prix item."""
    dqe = models.ForeignKey(DQE, on_delete=models.CASCADE, related_name='lines')
    price_item = models.ForeignKey(PriceLibraryItem, on_delete=models.PROTECT, related_name='dqe_lines', verbose_name=_('Article'))
    phase = models.ForeignKey(
        ProjectPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name='dqe_lines',
        verbose_name=_('Étape'),
        help_text=_(
            "L'étape (ou sous-étape) du chantier concernée par cette ligne — nécessaire pour "
            "comparer les demandes de matériaux à ce poste du devis étape par étape."
        ),
    )
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
        """Positive quantity, non-negative unit price — note `unit_price`
        is this line's own stored copy, not re-validated against (or kept
        in sync with) the referenced price_item's current price. A chosen
        phase must belong to the same site as the parent DQE, when both
        are known."""
        from django.core.exceptions import ValidationError
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': _('La quantité doit être un nombre positif.')})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': _('Le prix unitaire ne peut pas être négatif.')})
        if self.phase_id and self.dqe_id and self.dqe.site_id and self.phase.site_id != self.dqe.site_id:
            raise ValidationError({'phase': _("L'étape sélectionnée n'appartient pas au chantier de ce DQE.")})

    @property
    def display_designation(self):
        """This line's own designation override, falling back to the
        catalog item's."""
        return self.designation or self.price_item.designation

    @property
    def unit(self):
        """Always the catalog item's unit — a DQE line has no unit
        override of its own (unlike designation/unit_price)."""
        return self.price_item.unit

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)

    def exploded_requirements(self):
        """Returns this line's quantity expressed as elementary material
        requirements, as a dict {material_id: Decimal quantity}.

        - A MATERIAL-type price_item with a `material` set contributes its
          own quantity directly for that material (no ratio lookup).
        - A WORK_ITEM-type price_item explodes its quantity through
          MaterialConsumptionRatio rows matching its `work_category`,
          preferring a cabinet-specific override over the global default
          (cabinet=None) for the same (work_category, material) pair.
        - Anything else (e.g. a labor/service item with no material and no
          work_category) contributes nothing — it simply isn't part of the
          material-consumption picture.
        """
        from decimal import Decimal
        item = self.price_item
        quantity = self.quantity or Decimal('0')
        result = {}
        if item.item_type == PriceItemType.MATERIAL and item.material_id:
            result[item.material_id] = result.get(item.material_id, Decimal('0')) + quantity
            return result
        if item.item_type == PriceItemType.WORK_ITEM and item.work_category:
            cabinet_id = self.dqe.cabinet_id
            ratios = MaterialConsumptionRatio.objects.filter(
                work_category=item.work_category,
            ).filter(
                models.Q(cabinet_id=cabinet_id) | models.Q(cabinet__isnull=True)
            ).select_related('material')
            # Prefer a cabinet-specific override over the global default
            # when both exist for the same material.
            by_material = {}
            for ratio in ratios:
                existing = by_material.get(ratio.material_id)
                if existing is None or (existing.cabinet_id is None and ratio.cabinet_id is not None):
                    by_material[ratio.material_id] = ratio
            for material_id, ratio in by_material.items():
                result[material_id] = result.get(material_id, Decimal('0')) + quantity * ratio.ratio
        return result


class MaterialConsumptionRatio(BaseModel):
    """How much of an elementary material one unit of a WORK_ITEM work
    category consumes (e.g. 1 m³ of BETON ⇒ 7 sacs de ciment) — the
    "explosion" catalog used by DQELine.exploded_requirements() to turn a
    composite ouvrage quantity into comparable material quantities.

    `cabinet=None` is a global default ratio (seeded from standard BTP
    practice); a cabinet may add its own row for the same
    (work_category, material) pair to override that default for itself —
    see exploded_requirements()'s override-preference logic."""
    cabinet = models.ForeignKey(
        Cabinet, on_delete=models.CASCADE, null=True, blank=True, related_name='material_consumption_ratios',
        verbose_name=_('Cabinet'),
        help_text=_("Laisser vide pour un ratio par défaut (applicable à tous les cabinets, sauf override)."),
    )
    work_category = models.CharField(max_length=20, choices=WorkCategory.choices, verbose_name=_("Catégorie d'ouvrage"))
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='consumption_ratios', verbose_name=_('Matériau'))
    ratio = models.DecimalField(max_digits=12, decimal_places=4, verbose_name=_('Ratio'), help_text=_("Quantité du matériau par unité de l'ouvrage, ex. 7 (sacs de ciment) par m³ de béton"))
    ratio_unit = models.CharField(max_length=50, verbose_name=_('Unité du ratio'), help_text=_("ex. sacs/m³, kg/m³"))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Ratio de consommation matière')
        verbose_name_plural = _('Ratios de consommation matière')
        unique_together = ('cabinet', 'work_category', 'material')
        ordering = ['work_category', 'material__name']

    def __str__(self):
        scope = self.cabinet.name if self.cabinet_id else _('Défaut global')
        return f"{self.get_work_category_display()} → {self.material.name} ({self.ratio} {self.ratio_unit}) [{scope}]"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.ratio is not None and self.ratio <= 0:
            raise ValidationError({'ratio': _('Le ratio doit être un nombre positif.')})
