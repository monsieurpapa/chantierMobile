"""Forms for suppliers, stock items/movements/transfers, purchase orders
(with their line formset), the wire-transfer proof upload, and supplier
credit/repayment."""
from django import forms
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


class StockMovementForm(forms.ModelForm):
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
