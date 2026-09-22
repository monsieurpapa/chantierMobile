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
    
    def magasinier_validate(self, user, notes=''):
        """First stage of the two-step approval (état de besoin): the
        magasinier checks the request against what's actually needed/
        available before it goes up for final authorization."""
        from django.core.exceptions import ValidationError
        from core.models import StatusChangeLog
        if self.status != MaterialRequestStatus.PENDING:
            raise ValidationError(_('Seule une demande en attente peut être validée par le magasinier.'))
        old_status = self.status
        self.status = MaterialRequestStatus.VALIDATED
        self.save(update_fields=['status', 'updated_at'])
        StatusChangeLog.log(self, changed_by=user, old_status=old_status, new_status=self.status, note=notes)

    def authorize(self, user, notes=''):
        """Second/final stage: Directeur Technique, Directeur Général (or
        Directeur de Cabinet) gives the final authorization once the
        magasinier has validated the request.

        This is also where "exécuter une sortie financière venant d'un état
        de besoin, validée, liée à un projet" happens: authorizing the
        request creates the matching Expense (already APPROVED, since the
        two-stage état de besoin approval IS the approval — it only remains
        for the cashier to pay it) and links it back via `self.expense`, so
        the promised amount is no longer a number that only lives on this
        request."""
        from django.db import transaction
        from django.core.exceptions import ValidationError
        from core.models import StatusChangeLog
        if self.status != MaterialRequestStatus.VALIDATED:
            raise ValidationError(_("Seule une demande validée par le magasinier peut être autorisée."))
        with transaction.atomic():
            old_status = self.status
            self.status = MaterialRequestStatus.APPROVED
            self.save(update_fields=['status', 'updated_at'])
            StatusChangeLog.log(self, changed_by=user, old_status=old_status, new_status=self.status, note=notes)
            if not self.expense_id and self.total_estimated_cost and self.total_estimated_cost > 0:
                self._create_linked_expense(user)

    def _create_linked_expense(self, user):
        """Create the Expense this material request's authorization
        promises, pre-approved, and link it via the expense OneToOne.
        Only called when there's a positive estimated cost to charge —
        a request made up entirely of free-text (hors catalogue) items
        with no catalog price has nothing to attach yet, so it's left
        for whoever pays to record that expense manually instead."""
        from decimal import Decimal, ROUND_HALF_UP
        from django.utils import timezone
        from finance.models import Expense, ExpenseApproval, ExpenseCategory
        from chantiermobile.constants import ExpenseStatus, ExpenseNature
        category, _created = ExpenseCategory.objects.get_or_create(name='Matériaux de Construction')
        item_names = ', '.join(self.items.values_list('material__name', flat=True)[:3]) or \
            ', '.join(self.items.values_list('material_name', flat=True)[:3])
        # The catalog's cost-per-unit × a fractional quantity can carry more
        # than 2 decimal places — round to cents so it always fits
        # Expense.amount's DecimalField(max_digits=12, decimal_places=2)
        # instead of tripping full_clean()'s DecimalValidator below.
        amount = Decimal(self.total_estimated_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        expense = Expense(
            site=self.site,
            requester=self.requested_by or user,
            category=category,
            nature=ExpenseNature.MATERIEL,
            amount=amount,
            expense_date=timezone.localdate(),
            description=_("État de besoin #%(id)s autorisé — %(items)s") % {'id': self.pk, 'items': item_names or _('matériaux')},
            status=ExpenseStatus.APPROVED,
        )
        expense.full_clean()
        expense.save()
        ExpenseApproval.objects.create(
            expense=expense, approver=user, status=ExpenseApproval.Status.APPROVED,
            comments=_("Approuvé automatiquement via l'autorisation de l'état de besoin #%(id)s.") % {'id': self.pk},
        )
        self.expense = expense
        self.save(update_fields=['expense', 'updated_at'])

    def reject(self, user, notes=''):
        """Either stage may reject the request."""
        from django.core.exceptions import ValidationError
        from core.models import StatusChangeLog
        if self.status not in (MaterialRequestStatus.PENDING, MaterialRequestStatus.VALIDATED):
            raise ValidationError(_('Cette demande ne peut plus être rejetée.'))
        old_status = self.status
        self.status = MaterialRequestStatus.REJECTED
        self.save(update_fields=['status', 'updated_at'])
        StatusChangeLog.log(self, changed_by=user, old_status=old_status, new_status=self.status, note=notes)

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
