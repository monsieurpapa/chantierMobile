from django import forms
from .models import Material, MaterialRequest

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
        fields = ['site', 'material', 'quantity']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
        }
