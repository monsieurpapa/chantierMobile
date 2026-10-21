"""Forms for suppliers, stock items/movements/transfers, purchase orders
(with their line formset), the wire-transfer proof upload, and supplier
credit/repayment."""
from django import forms
from projects.phase_fields import PhaseCatalogFormMixin, enable_phase_catalog
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement, SupplierCredit
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig
from core.widgets import DynamicSelectWidget


class SupplierForm(forms.ModelForm):
    """Create/edit a supplier. `cabinet` is not a form field — it's set
    by the view from the current user's cabinet."""
    class Meta:
        model = Supplier
        fields = ['name', 'contact_name', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SUPPLIER_NAME}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.FIRST_NAME}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': FormHelpTexts.ADDITIONAL_NOTES, 'rows': 3}),
        }


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = ['site', 'material', 'name', 'unit', 'quantity_on_hand', 'reorder_threshold']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'material': DynamicSelectWidget(
                create_url_name='materials:material_quick_create',
                placeholder=_('Sélectionner ou ajouter un matériel...'),
            ),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_NAME}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_UNIT}),
            'quantity_on_hand': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reorder_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Quantity on hand is only editable at creation (initial stock
        # count) — afterwards it must only move through StockMovement so
        # the audit trail stays accurate.
        if self.instance and self.instance.pk:
            self.fields['quantity_on_hand'].disabled = True
            self.fields['quantity_on_hand'].help_text = _('Utilisez un mouvement de stock pour modifier la quantité.')


class PurchaseOrderForm(forms.ModelForm):
    """The order's own fields; its lines are handled separately by
    PurchaseOrderLineFormSet. `status` is intentionally not a form
    field — it only moves through the dedicated send/receive/cancel
    endpoints in procurement/views.py, each of which drives
    PurchaseOrder.clean()'s status state machine."""
    class Meta:
        model = PurchaseOrder
        fields = ['site', 'supplier', 'order_number', 'order_date', 'expected_delivery_date', 'caisse', 'payment_method', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'supplier': DynamicSelectWidget(
                create_url_name='procurement:supplier_quick_create',
                placeholder=_('Sélectionner ou ajouter un fournisseur...'),
            ),
            'order_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.PURCHASE_ORDER_NUMBER}),
            'order_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'expected_delivery_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'caisse': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class PurchaseOrderLineForm(forms.ModelForm):
    """A single order line. `quantity_received` is not a field here — it
    only advances through PurchaseOrder.receive()."""
    class Meta:
        model = PurchaseOrderLine
        fields = ['stock_item', 'quantity', 'unit_price']
        widgets = {
            # stock_item is scoped to the order's own site, chosen once on
            # PurchaseOrderForm (id_site) — same "depends on a field
            # elsewhere on the page" pattern as ExpenseForm.personnel. Without
            # quick-create here, a site with an empty stock catalog was a
            # dead end: no way to add its very first order line.
            'stock_item': DynamicSelectWidget(
                create_url_name='procurement:stock_item_quick_create',
                placeholder=_('Sélectionner ou ajouter un article de stock...'),
                depends_on='id_site', depends_param='site',
            ),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': FormPlaceholders.AMOUNT}),
        }


# No `widgets={...}` kwarg here — see the matching note on
# MaterialRequestItemFormSet in materials/forms.py: passing one would
# silently replace PurchaseOrderLineForm.Meta.widgets wholesale, including
# the DynamicSelectWidget above, for every formset row.
PurchaseOrderLineFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderLine,
    form=PurchaseOrderLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class StockMovementForm(PhaseCatalogFormMixin, forms.ModelForm):
    """A manual, single-item stock movement (entry/exit/adjustment —
    TRANSFER is excluded from the choices below since a transfer must go
    through StockTransferForm/StockItem.transfer_to() instead, so both
    legs of the audit trail are always created together)."""
    class Meta:
        model = StockMovement
        fields = ['movement_type', 'quantity', 'phase', 'motif', 'movement_date', 'notes', 'facture']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'motif': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Raison du mouvement')}),
            'movement_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': FormHelpTexts.ITEM_NOTES, 'rows': 2}),
            'facture': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        stock_item = kwargs.pop('stock_item', None)
        super().__init__(*args, **kwargs)
        self.fields['facture'].required = False
        self.fields['phase'].required = False
        self.fields['motif'].required = False
        # A manual movement here is always single-item — a Transfer must go
        # through StockItem.transfer_to() (a dedicated flow) so both legs of
        # the audit trail are always created together.
        self.fields['movement_type'].choices = [
            c for c in self.fields['movement_type'].choices if c[0] != 'TRANSFER'
        ]
        if stock_item is not None:
            self.fields['phase'].queryset = stock_item.site.phases.all()
        else:
            self.fields['phase'].queryset = self.fields['phase'].queryset.none()
        # Also offer the Catalogue des étapes for the stock item's chantier.
        enable_phase_catalog(self, 'phase', [stock_item.site if stock_item is not None else None])


class StockTransferForm(forms.Form):
    """Move stock from one StockItem to another — typically the same
    material at a different site of the same cabinet."""
    destination_site = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}), label=_('Chantier de destination'))
    quantity = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}), label=_('Quantité'))
    motif = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_('Motif'))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_('Notes'))

    def __init__(self, *args, **kwargs):
        source_site = kwargs.pop('source_site', None)
        super().__init__(*args, **kwargs)
        from projects.models import Site
        qs = Site.objects.filter(cabinet=source_site.cabinet).exclude(pk=source_site.pk) if source_site else Site.objects.none()
        self.fields['destination_site'].queryset = qs


class TransferProofForm(forms.Form):
    """The cashier enters the wire-transfer proof the financier sent her."""
    transfer_proof = forms.FileField(widget=forms.ClearableFileInput(attrs={'class': 'form-control'}), label=_('Preuve de virement'))


class SupplierCreditForm(forms.ModelForm):
    """Register a new achat à crédit. `purchase_order` and `due_date` are
    optional — a credit doesn't have to be tied to a specific order."""
    class Meta:
        model = SupplierCredit
        fields = ['supplier', 'purchase_order', 'amount', 'date', 'due_date', 'notes']
        widgets = {
            'supplier': DynamicSelectWidget(
                create_url_name='procurement:supplier_quick_create',
                placeholder=_('Sélectionner ou ajouter un fournisseur...'),
            ),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_order'].required = False
        self.fields['due_date'].required = False


class SupplierCreditPaymentForm(forms.Form):
    """An installment payment against a SupplierCredit; `caisse` is
    optional since not every repayment comes out of cash on hand."""
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant'))
    caisse = forms.ModelChoiceField(required=False, queryset=None, widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse (optionnel)'))

    def __init__(self, *args, **kwargs):
        cabinet = kwargs.pop('cabinet', None)
        super().__init__(*args, **kwargs)
        from finance.models import Caisse
        self.fields['caisse'].queryset = Caisse.objects.filter(cabinet=cabinet) if cabinet else Caisse.objects.none()


class StockEntryExitForm(PhaseCatalogFormMixin, forms.ModelForm):
    """An entrée or sortie at one chantier, recorded (and later edited) by
    that chantier's Magasinier — 2026-10-21.

    The chantier and the direction are fixed by the view. An entrée names
    a material from the Catalogue des matériaux (searchable, with quick
    add); its article de stock on the chantier is found or created on
    save. A sortie picks one of the chantier's articles de stock. No price
    is asked or shown: a Magasinier deals in quantities only."""
    material = forms.ModelChoiceField(
        queryset=None, required=False, label=_('Matériau'),
        widget=DynamicSelectWidget(
            create_url_name='materials:material_quick_create',
            placeholder=_('Rechercher dans le catalogue ou ajouter…'),
        ),
    )

    class Meta:
        model = StockMovement
        fields = ['stock_item', 'quantity', 'movement_date', 'phase', 'supplier', 'delivery_note_ref',
                  'motif', 'notes', 'facture']
        labels = {'stock_item': _('Article en stock'), 'facture': _('Justificatif (facture, bon de livraison)')}
        widgets = {
            'stock_item': forms.Select(attrs={'class': 'form-select', 'data-control': 'select2',
                                              'data-placeholder': _('Choisir un article en stock…')}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'movement_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'supplier': DynamicSelectWidget(
                create_url_name='procurement:supplier_quick_create',
                placeholder=_('Rechercher ou ajouter un fournisseur…'),
            ),
            'delivery_note_ref': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. BL-2026-0412')}),
            'motif': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'facture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, site, movement_type, **kwargs):
        from django.utils import timezone
        from materials.models import Material
        from chantiermobile.constants import StockMovementType
        super().__init__(*args, **kwargs)
        self.site = site
        self.movement_type = movement_type
        self.instance.movement_type = movement_type
        self.is_entry = movement_type == StockMovementType.IN
        self.fields['material'].queryset = Material.objects.order_by('name')
        self.fields['stock_item'].queryset = StockItem.objects.filter(site=site).order_by('name')
        self.fields['stock_item'].label_from_instance = lambda i: f"{i.name} — {i.quantity_on_hand} {i.unit} en stock"
        self.fields['supplier'].queryset = Supplier.objects.filter(cabinet=site.cabinet)
        self.fields['phase'].queryset = site.phases.all()
        self.fields['phase'].required = False
        self.fields['phase'].label = _('Étape')
        self.fields['quantity'].label = _('Quantité reçue') if self.is_entry else _('Quantité sortie')
        self.fields['movement_date'].label = _('Date de réception') if self.is_entry else _('Date de sortie')
        for name in ('motif', 'notes', 'facture', 'supplier', 'delivery_note_ref'):
            self.fields[name].required = False
        if not self.instance.pk:
            self.initial.setdefault('movement_date', timezone.localdate())
        if self.is_entry:
            self.fields['stock_item'].required = False
            self.fields['stock_item'].widget = forms.HiddenInput()
            if self.instance.pk and self.instance.stock_item.material_id:
                self.initial.setdefault('material', self.instance.stock_item.material_id)
        else:
            self.fields['stock_item'].required = True
            del self.fields['material']
            del self.fields['supplier']
            del self.fields['delivery_note_ref']
            self.fields['motif'].widget.attrs['placeholder'] = _("ex. Coulage dalle niveau 1")
        enable_phase_catalog(self, 'phase', [site])

    def clean(self):
        cleaned = super().clean()
        if self.is_entry:
            material = cleaned.get('material')
            if material is None and not (self.instance.pk and self.instance.stock_item_id):
                self.add_error('material', _('Choisissez le matériau reçu dans le catalogue.'))
        return cleaned

    def _stock_item_for(self, material, create):
        item = (StockItem.objects.filter(site=self.site, material=material).first()
                or StockItem.objects.filter(site=self.site, name__iexact=material.name).first())
        if item is None and create:
            item = StockItem.objects.create(site=self.site, material=material, name=material.name, unit=material.unit)
        elif item is not None and item.material_id is None:
            item.material = material
            item.save(update_fields=['material', 'updated_at'])
        return item

    def _get_validation_exclusions(self):
        # The article of an entrée is resolved from `material` in clean().
        exclude = set(super()._get_validation_exclusions())
        if self.is_entry:
            exclude.add('stock_item')
        return exclude

    def save(self, commit=True):
        movement = super().save(commit=False)
        movement.movement_type = self.movement_type
        if self.is_entry and self.cleaned_data.get('material') is not None:
            movement.stock_item = self._stock_item_for(self.cleaned_data['material'], create=True)
        if commit:
            movement.save_with_stock_update()
        return movement
