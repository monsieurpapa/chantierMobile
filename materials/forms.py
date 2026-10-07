"""Forms for the Material catalog and the material-request workflow,
including the inline formset that lets a request be submitted with
several items (catalog-linked or free-text) in one POST."""
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Material, MaterialRequest, MaterialRequestItem
from chantiermobile.constants import FormPlaceholders, FormHelpTexts
from core.widgets import DynamicSelectWidget

class MaterialForm(forms.ModelForm):
    """Create/edit a shared catalog entry."""
    class Meta:
        model = Material
        fields = ['name', 'unit', 'estimated_cost_per_unit']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_NAME}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_UNIT}),
            'estimated_cost_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
        }

class MaterialRequestForm(forms.ModelForm):
    """The request's own fields (site + notes) — its items are handled
    separately by MaterialRequestItemFormSet."""
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
        fields = ['material', 'material_name', 'phase', 'quantity', 'notes']
        widgets = {
            'material': DynamicSelectWidget(
                create_url_name='materials:material_quick_create',
                placeholder=_('Sélectionner ou ajouter un matériel...'),
            ),
            'material_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _("Ou écrire le nom du matériel..."),
            }),
            'phase': forms.Select(attrs={'class': 'form-select material-item-phase'}),
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
        self.fields['phase'].required = False
        # Empty on a fresh GET (mirrors ExpenseForm's own phase field) —
        # the request_form.html template loads the real options live via
        # finance:site_phases_data once a site is picked, and repopulates
        # this on an edit via the preselected id baked into the template.
        from projects.models import ProjectPhase
        site = None
        if self.instance and self.instance.pk and self.instance.request_id:
            site = self.instance.request.site
        elif 'initial' in kwargs and kwargs.get('initial', {}).get('site'):
            site = kwargs['initial']['site']
        if site is not None:
            self.fields['phase'].queryset = ProjectPhase.objects.filter(site=site).order_by('start_date')
        else:
            self.fields['phase'].queryset = ProjectPhase.objects.none()

# Formset for handling multiple materials per request.
#
# IMPORTANT: no `widgets={...}` kwarg here. inlineformset_factory() builds a
# brand-new Meta class for each row form via modelform_factory(); when a
# `widgets` dict is passed, Django sets it as `Meta.widgets` outright rather
# than merging it with the base form's Meta.widgets, so it silently replaces
# EVERY widget declared on MaterialRequestItemForm.Meta.widgets above, including
# the 'material' field's DynamicSelectWidget (quick-create picker), downgrading
# every formset row back to a dead-end plain <select>. MaterialRequestItemForm
# already declares the right widget for all four fields, so nothing needs to
# be repeated here.
MaterialRequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    MaterialRequestItem,
    form=MaterialRequestItemForm,
    extra=1,  # Start with 1 empty form
    min_num=1,  # Require at least 1 material
    validate_min=True,
    can_delete=True,
)
