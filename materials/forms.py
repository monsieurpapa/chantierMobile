from django import forms
from django.forms import inlineformset_factory
from .models import Material, MaterialRequest, MaterialRequestItem

class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ['name', 'unit', 'estimated_cost_per_unit']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Material Name'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. kg, m3, liters'}),
            'estimated_cost_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
        }

class MaterialRequestForm(forms.ModelForm):
    class Meta:
        model = MaterialRequest
        fields = ['site', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Additional notes or special instructions...',
                'rows': 3
            }),
        }

class MaterialRequestItemForm(forms.ModelForm):
    """Form for individual material items in a request"""
    class Meta:
        model = MaterialRequestItem
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select', 'data-control': 'select2'}),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Notes for this item (optional)',
                'rows': 2
            }),
        }

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
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    }
)
