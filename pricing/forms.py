from django import forms
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem


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
