from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Material, MaterialRequest, MaterialRequestItem
from chantiermobile.constants import FormPlaceholders, FormHelpTexts

class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ['name', 'unit', 'estimated_cost_per_unit']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_NAME}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_UNIT}),
            'estimated_cost_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
        }

class MaterialRequestForm(forms.ModelForm):
    class Meta:
        model = MaterialRequest
        fields = ['site', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': FormHelpTexts.ADDITIONAL_NOTES,
                'rows': 3
            }),
        }

class MaterialRequestItemForm(forms.ModelForm):
    """Form for individual material items in a request. Either `material`
    (catalog) or `material_name` (free text) must be filled — not both;
    enforced by MaterialRequestItem.clean()."""
    class Meta:
        model = MaterialRequestItem
        fields = ['material', 'material_name', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select', 'data-control': 'select2'}),
            'material_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _("Ou écrire le nom du matériel..."),
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': FormHelpTexts.ITEM_NOTES,
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].required = False
        self.fields['material_name'].required = False

# Formset for handling multiple materials per request
MaterialRequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    MaterialRequestItem,
    form=MaterialRequestItemForm,
    extra=1,  # Start with 1 empty form
    min_num=1,  # Require at least 1 material
    validate_min=True,
    can_delete=True,
    widgets={
        'material': forms.Select(attrs={'class': 'form-select'}),
        'material_name': forms.TextInput(attrs={'class': 'form-control'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    }
)
