from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem, DQE, DQELine


class PriceLibraryItemForm(forms.ModelForm):
    class Meta:
        model = PriceLibraryItem
        fields = ['code', 'designation', 'item_type', 'unit', 'unit_price', 'is_active', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. MO-001')}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Désignation de l\'article')}),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. m², m³, kg, forfait, jour')}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is not None and unit_price < 0:
            raise forms.ValidationError(_('Le prix unitaire ne peut pas être négatif.'))
        return unit_price


class DQEForm(forms.ModelForm):
    class Meta:
        model = DQE
        fields = ['site', 'reference', 'title', 'status', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. DQE-2025-001')}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Intitulé du DQE')}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class DQELineForm(forms.ModelForm):
    class Meta:
        model = DQELine
        fields = ['price_item', 'designation', 'quantity', 'unit_price']
        widgets = {
            'price_item': forms.Select(attrs={'class': 'form-select'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _("Laisser vide pour utiliser la désignation du catalogue")}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price_item'].queryset = PriceLibraryItem.objects.filter(is_active=True).order_by('item_type', 'code')


DQELineFormSet = inlineformset_factory(
    DQE,
    DQELine,
    form=DQELineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
