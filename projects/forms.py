"""ModelForms for the `projects` app. Role/cabinet gating lives in the
views (see projects/views.py) — these forms only handle field widgets
and the one piece of field-level validation each needs (e.g. an
optional lead_engineer/phase)."""
from django import forms
from django.forms import modelformset_factory
from django.utils.translation import gettext_lazy as _
from .models import Site, ProjectPhase, SiteProgress, PlanningSubmission, SiteLevel
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ContractMode, StructureType

class SiteForm(forms.ModelForm):
    """Site create/edit form. `lead_engineer`'s queryset is further
    narrowed per-request in projects/views.py's
    `_scope_lead_engineer_queryset` — not here, since that needs the
    request's cabinet.

    `contract_mode` is pre-established at creation (2026-10-07 client
    spec) and always rendered with a selected value in the real form, but
    is made non-required here — with a fallback in clean_contract_mode()
    — purely so a POST that omits it (e.g. a caller only updating another
    field) doesn't blank out an existing site's mode or fail validation;
    it still defaults new sites to ContractMode.CLE_EN_MAIN either way.

    `floor_count`/`basement_count`/`structure_type` (2026-10-08) get the
    same non-required + fallback treatment, for the same reason — a POST
    missing one of them (an older cached form page, a script only
    patching another field) must not silently reset a site's floor count
    to 0 and wipe out its levels via sync_levels(). Note the fallback
    checks `is None`, not falsiness, for the two integer fields: 0 is a
    meaningful, explicitly-submitted floor/basement count, not "omitted"."""
    class Meta:
        model = Site
        fields = [
            'name', 'location', 'status', 'contract_mode', 'start_date', 'expected_end_date', 'lead_engineer',
            'floor_count', 'basement_count', 'footprint_area_m2', 'structure_type',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SITE_NAME}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LOCATION}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'contract_mode': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'expected_end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'lead_engineer': forms.Select(attrs={'class': 'form-select'}),
            'floor_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
            'basement_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
            'footprint_area_m2': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01', 'placeholder': '0.00'}),
            'structure_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lead_engineer'].required = False
        self.fields['contract_mode'].required = False
        self.fields['floor_count'].required = False
        self.fields['basement_count'].required = False
        self.fields['structure_type'].required = False

    def clean_contract_mode(self):
        value = self.cleaned_data.get('contract_mode')
        if not value:
            if self.instance and self.instance.pk and self.instance.contract_mode:
                return self.instance.contract_mode
            return ContractMode.CLE_EN_MAIN
        return value

    def clean_floor_count(self):
        value = self.cleaned_data.get('floor_count')
        if value is None:
            if self.instance and self.instance.pk:
                return self.instance.floor_count
            return 0
        return value

    def clean_basement_count(self):
        value = self.cleaned_data.get('basement_count')
        if value is None:
            if self.instance and self.instance.pk:
                return self.instance.basement_count
            return 0
        return value

    def clean_structure_type(self):
        value = self.cleaned_data.get('structure_type')
        if not value:
            if self.instance and self.instance.pk and self.instance.structure_type:
                return self.instance.structure_type
            return StructureType.POTEAUX_POUTRES
        return value

class ProjectPhaseForm(forms.ModelForm):
    """Phase create/edit form — name, optional parent (sous-étape) and
    dates; status transitions go through ProjectPhase.close(), not this
    form.

    `parent_phase` (added 2026-10-07) is optional and scoped to the
    target site's own **top-level** phases only — pass `site=` to
    `__init__` (the create/update views do). A phase that already has its
    own sous-étapes is excluded from being selectable as anyone's child in
    turn (mirrors the model's own `clean()` guard against a 2nd nesting
    level, from the other direction), and a phase being edited never
    offers itself as its own parent."""
    class Meta:
        model = ProjectPhase
        fields = ['name', 'parent_phase', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.PHASE_NAME}),
            'parent_phase': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
        }

    def __init__(self, *args, site=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent_phase'].required = False
        self.fields['parent_phase'].empty_label = _("Aucune — étape principale")
        site = site or getattr(self.instance, 'site', None)
        qs = ProjectPhase.objects.none()
        if site is not None:
            qs = ProjectPhase.objects.filter(site=site, parent_phase__isnull=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
                if self.instance.sub_phases.exists():
                    # This phase is itself a parent already; letting it
                    # become someone else's child would create a 2nd
                    # nesting level — see ProjectPhase.clean().
                    qs = ProjectPhase.objects.none()
        self.fields['parent_phase'].queryset = qs

class PlanningSubmissionForm(forms.ModelForm):
    """Drafts a planning submission; `phase` is optional (a submission
    can cover the whole site rather than one phase) and its queryset is
    narrowed to the target site's own phases in
    PlanningSubmissionCreateView.get_form()."""
    class Meta:
        model = PlanningSubmission
        fields = ['phase', 'description']
        widgets = {
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': _('Décrivez la planification à soumettre...')}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phase'].required = False


class SiteLevelForm(forms.ModelForm):
    """One SiteLevel's structural detail fields. There is no create/delete
    through this form — rows are server-managed by Site.sync_levels() —
    so `level_index` and `site` never appear here, only the engineering
    detail an avant-métré needs."""
    class Meta:
        model = SiteLevel
        fields = [
            'height_m', 'floor_area_m2', 'wall_length_m', 'opening_area_m2',
            'beam_count', 'beam_section_width_m', 'beam_section_height_m', 'beam_total_length_m',
            'column_count', 'column_section_width_m', 'column_section_depth_m',
            'slab_thickness_m', 'notes',
        ]
        widgets = {
            'height_m': forms.NumberInput(attrs={'class': 'form-control level-height', 'step': '0.01', 'placeholder': '3.00'}),
            'floor_area_m2': forms.NumberInput(attrs={'class': 'form-control level-floor-area', 'step': '0.01', 'placeholder': _('Emprise au sol du chantier')}),
            'wall_length_m': forms.NumberInput(attrs={'class': 'form-control level-wall-length', 'step': '0.01'}),
            'opening_area_m2': forms.NumberInput(attrs={'class': 'form-control level-opening-area', 'step': '0.01'}),
            'beam_count': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0'}),
            'beam_section_width_m': forms.NumberInput(attrs={'class': 'form-control level-beam-w', 'step': '0.01'}),
            'beam_section_height_m': forms.NumberInput(attrs={'class': 'form-control level-beam-h', 'step': '0.01'}),
            'beam_total_length_m': forms.NumberInput(attrs={'class': 'form-control level-beam-len', 'step': '0.01'}),
            'column_count': forms.NumberInput(attrs={'class': 'form-control level-col-count', 'step': '1', 'min': '0'}),
            'column_section_width_m': forms.NumberInput(attrs={'class': 'form-control level-col-w', 'step': '0.01'}),
            'column_section_depth_m': forms.NumberInput(attrs={'class': 'form-control level-col-d', 'step': '0.01'}),
            'slab_thickness_m': forms.NumberInput(attrs={'class': 'form-control level-slab-t', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


# No `extra` (rows come only from Site.sync_levels(), one per existing
# SiteLevel) and no `can_delete` (removing a level means lowering
# floor_count/basement_count on the Site form, not deleting a row here).
SiteLevelFormSet = modelformset_factory(SiteLevel, form=SiteLevelForm, extra=0, can_delete=False)


class SiteProgressForm(forms.ModelForm):
    """Progress-report form; photos are handled separately as plain
    multi-file uploads (see SiteProgressCreateView.form_valid), not a
    form field here."""
    class Meta:
        model = SiteProgress
        fields = ['report_date', 'percentage_complete', 'description']
        widgets = {
            'report_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'percentage_complete': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': '3', 'placeholder': FormPlaceholders.PROGRESS_DESCRIPTION}),
        }
