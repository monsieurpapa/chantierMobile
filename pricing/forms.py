"""Forms for the price library (Bibliothèque de Prix) and DQE (with its
line formset)."""
from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem, DQE, DQELine, MaterialConsumptionRatio


class PriceLibraryItemForm(forms.ModelForm):
    """Create/edit a price library item. `cabinet` is not a form field —
    it's set by the view. `work_category` and `material` are each only
    meaningful for one `item_type` (WORK_ITEM / MATERIAL respectively —
    see PriceLibraryItem.clean()); both are rendered as plain fields here
    and toggled client-side by price_item_form.html's JS based on the
    selected item_type, rather than hidden/shown with separate forms."""
    class Meta:
        model = PriceLibraryItem
        fields = ['code', 'designation', 'item_type', 'work_category', 'material', 'unit', 'unit_price', 'is_active', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. MO-001')}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Désignation de l\'article')}),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'work_category': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. m², m³, kg, forfait, jour')}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['work_category'].required = False
        self.fields['material'].required = False

    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is not None and unit_price < 0:
            raise forms.ValidationError(_('Le prix unitaire ne peut pas être négatif.'))
        return unit_price


class DQEForm(forms.ModelForm):
    """The DQE's own fields; its lines are handled separately by
    DQELineFormSet. `status` is a plain form field here — there is no
    model-level state machine for it (contrast MaterialRequest/
    PurchaseOrder), so DQEUpdateView can set it to any value."""
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
    """A single DQE line. `price_item` choices are restricted to active
    catalog items (__init__ below); `unit_price` defaults from the
    catalog client-side but is a plain editable field here, so it can be
    adjusted per-estimate without touching the catalog price. `phase`
    starts with an empty queryset (same reasoning as ExpenseForm's own
    phase field) — dqe_form.html loads it live via finance:site_phases_data
    once a site is picked."""
    class Meta:
        model = DQELine
        fields = ['price_item', 'phase', 'designation', 'quantity', 'unit_price']
        widgets = {
            'price_item': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.Select(attrs={'class': 'form-select dqe-line-phase'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _("Laisser vide pour utiliser la désignation du catalogue")}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price_item'].queryset = PriceLibraryItem.objects.filter(is_active=True).order_by('item_type', 'code')
        self.fields['phase'].required = False
        # On a POST, rebuild the queryset from the submitted parent `site`
        # (row forms share the parent's unprefixed data) so a phase picked
        # on a brand-new DQE isn't rejected as an invalid choice.
        from projects.models import ProjectPhase, Site
        site = None
        if self.data.get('site'):
            site = Site.objects.filter(pk=self.data.get('site')).first()
        elif self.instance and self.instance.pk and self.instance.dqe_id:
            site = self.instance.dqe.site
        if site is not None:
            self.fields['phase'].queryset = ProjectPhase.objects.filter(site=site).order_by('start_date')
        else:
            self.fields['phase'].queryset = ProjectPhase.objects.none()


DQELineFormSet = inlineformset_factory(
    DQE,
    DQELine,
    form=DQELineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class MaterialConsumptionRatioForm(forms.ModelForm):
    """Create/edit a cabinet-specific override of a global-default ratio
    (or a brand-new cabinet-specific ratio). `cabinet` is not a form field
    — the view always sets it to the acting user's own cabinet, since this
    form is only ever reached from a cabinet-scoped, director-tier-gated
    view (a cabinet can't edit the global defaults, cabinet=None, through
    this form — those are seed-migration-only)."""
    class Meta:
        model = MaterialConsumptionRatio
        fields = ['work_category', 'material', 'ratio', 'ratio_unit', 'notes']
        widgets = {
            'work_category': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
            'ratio': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.0000', 'step': '0.0001'}),
            'ratio_unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('ex. sacs/m³, kg/m³')}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class CabinetMaterialThresholdForm(forms.ModelForm):
    """Director-tier-editable cabinet-wide thresholds for the material
    variance comparison badges (orange/red bands, as a % of the devis/DQE
    baseline quantity)."""
    class Meta:
        from accounts.models import Cabinet
        model = Cabinet
        fields = ['material_variance_orange_threshold_pct', 'material_variance_red_threshold_pct']
        widgets = {
            'material_variance_orange_threshold_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
            'material_variance_red_threshold_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
        }
