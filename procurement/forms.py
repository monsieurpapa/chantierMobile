from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement, SupplierCredit
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig


class SupplierForm(forms.ModelForm):
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
            'material': forms.Select(attrs={'class': 'form-select'}),
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
    class Meta:
        model = PurchaseOrder
        fields = ['site', 'supplier', 'order_number', 'order_date', 'expected_delivery_date', 'caisse', 'payment_method', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
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
    class Meta:
        model = PurchaseOrderLine
        fields = ['stock_item', 'quantity', 'unit_price']
        widgets = {
            'stock_item': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': FormPlaceholders.AMOUNT}),
        }


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
    class Meta:
        model = StockMovement
        fields = ['movement_type', 'quantity', 'movement_date', 'notes', 'facture']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'movement_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'placeholder': FormHelpTexts.ITEM_NOTES, 'rows': 2}),
            'facture': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['facture'].required = False


class TransferProofForm(forms.Form):
    """The cashier enters the wire-transfer proof the financier sent her."""
    transfer_proof = forms.FileField(widget=forms.ClearableFileInput(attrs={'class': 'form-control'}), label=_('Preuve de virement'))


class SupplierCreditForm(forms.ModelForm):
    class Meta:
        model = SupplierCredit
        fields = ['supplier', 'purchase_order', 'amount', 'date', 'due_date', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
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
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant'))
    caisse = forms.ModelChoiceField(required=False, queryset=None, widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse (optionnel)'))

    def __init__(self, *args, **kwargs):
        cabinet = kwargs.pop('cabinet', None)
        super().__init__(*args, **kwargs)
        from finance.models import Caisse
        self.fields['caisse'].queryset = Caisse.objects.filter(cabinet=cabinet) if cabinet else Caisse.objects.none()
