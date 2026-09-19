from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from accounts.models import Cabinet
from projects.models import Site
from materials.models import Material
from chantiermobile.constants import PurchaseOrderStatus, StockMovementType


class Supplier(BaseModel):
    """A materials/equipment supplier (fournisseur) used on purchase orders."""
    cabinet = models.ForeignKey(Cabinet, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=255, verbose_name=_('Nom'))
    contact_name = models.CharField(max_length=255, blank=True, verbose_name=_('Personne de contact'))
    phone = models.CharField(max_length=50, blank=True, verbose_name=_('Téléphone'))
    email = models.EmailField(blank=True, verbose_name=_('E-mail'))
    address = models.TextField(blank=True, verbose_name=_('Adresse'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Fournisseur')
        verbose_name_plural = _('Fournisseurs')
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_orders(self):
        return self.purchase_orders.count()


class StockItem(BaseModel):
    """A tracked inventory item at a Site: a running quantity_on_hand that
    is only ever changed through StockMovement (received POs, manual
    entries/exits, or corrections) so there is always an audit trail."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='stock_items')
    material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_items',
        help_text=_('Article du catalogue de matériaux (facultatif)'),
    )
    name = models.CharField(max_length=255, verbose_name=_("Désignation"))
    unit = models.CharField(max_length=50, verbose_name=_('Unité'), help_text=_('e.g. kg, m3, liters'))
    quantity_on_hand = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Quantité en stock'))
    reorder_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_('Seuil de réapprovisionnement'),
    )

    class Meta:
        verbose_name = _('Article de stock')
        verbose_name_plural = _('Articles de stock')
        unique_together = [('site', 'name')]
        ordering = ['site', 'name']

    def __str__(self):
        return f"{self.name} @ {self.site.name} ({self.quantity_on_hand} {self.unit})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.reorder_threshold is not None and self.reorder_threshold < 0:
            raise ValidationError({'reorder_threshold': _('Le seuil de réapprovisionnement ne peut pas être négatif.')})

    @property
    def is_below_reorder_threshold(self):
        if self.reorder_threshold is None:
            return False
        return self.quantity_on_hand <= self.reorder_threshold


class PurchaseOrder(BaseModel):
    """A bon de commande (purchase order) raised against a Supplier for a Site."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    order_number = models.CharField(max_length=50, unique=True, verbose_name=_('N° de commande'))
    order_date = models.DateField(verbose_name=_('Date de commande'))
    expected_delivery_date = models.DateField(null=True, blank=True, verbose_name=_('Livraison prévue'))
    status = models.CharField(max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.BROUILLON)
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Bon de commande')
        verbose_name_plural = _('Bons de commande')
        ordering = ['-order_date', '-id']

    def __str__(self):
        return f"{self.order_number} - {self.supplier.name} ({self.get_status_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.expected_delivery_date and self.order_date and self.expected_delivery_date < self.order_date:
            raise ValidationError({
                'expected_delivery_date': _('La date de livraison prévue doit être postérieure à la date de commande.')
            })

        if self.pk:
            original = PurchaseOrder.objects.get(pk=self.pk)

            valid_transitions = {
                PurchaseOrderStatus.BROUILLON: [PurchaseOrderStatus.ENVOYEE, PurchaseOrderStatus.ANNULEE],
                PurchaseOrderStatus.ENVOYEE: [PurchaseOrderStatus.RECUE_PARTIELLE, PurchaseOrderStatus.RECUE, PurchaseOrderStatus.ANNULEE],
                PurchaseOrderStatus.RECUE_PARTIELLE: [PurchaseOrderStatus.RECUE, PurchaseOrderStatus.ANNULEE],
                PurchaseOrderStatus.RECUE: [],
                PurchaseOrderStatus.ANNULEE: [],
            }

            if original.status != self.status and original.status in valid_transitions:
                if self.status not in valid_transitions[original.status]:
                    raise ValidationError({
                        'status': _('Impossible de passer la commande de %(old)s à %(new)s.') % {
                            'old': original.get_status_display(),
                            'new': self.get_status_display(),
                        }
                    })

    @property
    def total_ht(self):
        return self.lines.aggregate(total=models.Sum(
            models.F('quantity') * models.F('unit_price'),
            output_field=models.DecimalField(max_digits=14, decimal_places=2)
        ))['total'] or 0

    @property
    def total_items(self):
        return self.lines.count()

    @property
    def is_fully_received(self):
        lines = list(self.lines.all())
        return bool(lines) and all(line.quantity_received >= line.quantity for line in lines)

    def receive(self, changed_by=None, lines_received=None):
        """Receive delivered quantities: creates an IN StockMovement per
        line (which bumps StockItem.quantity_on_hand) and transitions the
        order to RECUE or RECUE_PARTIELLE.

        lines_received: optional {line_id: quantity} map of quantities
        being received on this delivery. If omitted, every line still
        outstanding is received in full (single-delivery orders).
        """
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        from core.models import StatusChangeLog

        if self.status not in [PurchaseOrderStatus.ENVOYEE, PurchaseOrderStatus.RECUE_PARTIELLE]:
            raise ValidationError(_('Seule une commande envoyée peut être réceptionnée.'))

        lines = list(self.lines.select_related('stock_item'))
        if not lines:
            raise ValidationError(_('Cette commande ne comporte aucune ligne.'))

        today = timezone.localdate()
        any_received = False
        for line in lines:
            remaining = line.quantity - line.quantity_received
            if remaining <= 0:
                continue
            qty = remaining if lines_received is None else min(remaining, lines_received.get(line.id, 0) or 0)
            if qty and qty > 0:
                StockMovement.objects.create(
                    stock_item=line.stock_item,
                    movement_type=StockMovementType.IN,
                    quantity=qty,
                    purchase_order_line=line,
                    moved_by=changed_by,
                    movement_date=today,
                    notes=_('Réception de la commande %(num)s') % {'num': self.order_number},
                )
                line.quantity_received = line.quantity_received + qty
                line.save(update_fields=['quantity_received', 'updated_at'])
                any_received = True

        if not any_received:
            raise ValidationError(_('Aucune quantité à réceptionner.'))

        old_status = self.status
        self.status = PurchaseOrderStatus.RECUE if self.is_fully_received else PurchaseOrderStatus.RECUE_PARTIELLE
        self.full_clean()
        self.save()
        StatusChangeLog.log(
            self,
            changed_by=changed_by,
            old_status=old_status,
            new_status=self.status,
            note=_('Réception enregistrée.'),
        )


class PurchaseOrderLine(BaseModel):
    """A single line item on a PurchaseOrder, tied to the StockItem it
    will replenish once received."""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    stock_item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='purchase_order_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Quantité commandée'))
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('Quantité reçue'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Prix unitaire'))

    class Meta:
        verbose_name = _('Ligne de commande')
        verbose_name_plural = _('Lignes de commande')
        ordering = ['id']

    def __str__(self):
        return f"{self.quantity} {self.stock_item.unit} of {self.stock_item.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': _('La quantité doit être positive.')})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': _('Le prix unitaire ne peut pas être négatif.')})
        if self.quantity is not None and self.quantity_received is not None and self.quantity_received > self.quantity:
            raise ValidationError({'quantity_received': _('La quantité reçue ne peut pas dépasser la quantité commandée.')})
        if self.stock_item_id and self.purchase_order_id and self.stock_item.site_id != self.purchase_order.site_id:
            raise ValidationError({'stock_item': _("L'article de stock doit appartenir au même chantier que la commande.")})

    @property
    def line_total(self):
        if self.quantity is None or self.unit_price is None:
            return 0
        return self.quantity * self.unit_price

    @property
    def remaining_quantity(self):
        return self.quantity - self.quantity_received


class StockMovement(BaseModel):
    """An audit-trailed change to a StockItem's quantity_on_hand: a
    receipt from a PurchaseOrder (IN), a manual withdrawal (OUT), or a
    manual correction (ADJUSTMENT, signed)."""
    stock_item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=StockMovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('Quantité'))
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    movement_date = models.DateField(verbose_name=_('Date du mouvement'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))

    class Meta:
        verbose_name = _('Mouvement de stock')
        verbose_name_plural = _('Mouvements de stock')
        ordering = ['-movement_date', '-id']

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} {self.stock_item.unit} - {self.stock_item.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.movement_type in (StockMovementType.IN, StockMovementType.OUT):
            if self.quantity is None or self.quantity <= 0:
                raise ValidationError({'quantity': _('La quantité doit être positive pour une entrée ou une sortie.')})
        elif self.movement_type == StockMovementType.ADJUSTMENT:
            if not self.quantity:
                raise ValidationError({'quantity': _("La quantité d'ajustement ne peut pas être nulle.")})

        if self.stock_item_id and self.quantity:
            delta = self._signed_delta()
            if self.stock_item.quantity_on_hand + delta < 0:
                raise ValidationError({'quantity': _('Cette opération rendrait le stock négatif.')})

    def _signed_delta(self):
        if self.movement_type == StockMovementType.OUT:
            return -self.quantity
        return self.quantity

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        delta = self._signed_delta() if is_new else None
        if is_new:
            self.stock_item.refresh_from_db(fields=['quantity_on_hand'])
            if self.stock_item.quantity_on_hand + delta < 0:
                from django.core.exceptions import ValidationError
                raise ValidationError(_('Stock insuffisant pour cette opération.'))
        super().save(*args, **kwargs)
        if is_new:
            StockItem.objects.filter(pk=self.stock_item_id).update(
                quantity_on_hand=models.F('quantity_on_hand') + delta
            )
            self.stock_item.refresh_from_db(fields=['quantity_on_hand'])
