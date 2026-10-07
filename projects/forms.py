"""ModelForms for the `projects` app. Role/cabinet gating lives in the
views (see projects/views.py) — these forms only handle field widgets
and the one piece of field-level validation each needs (e.g. an
optional lead_engineer/phase)."""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Site, ProjectPhase, SiteProgress, PlanningSubmission
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ContractMode

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
    it still defaults new sites to ContractMode.CLE_EN_MAIN either way."""
    class Meta:
        model = Site
        fields = ['name', 'location', 'status', 'contract_mode', 'start_date', 'expected_end_date', 'lead_engineer']
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lead_engineer'].required = False
        self.fields['contract_mode'].required = False

    def clean_contract_mode(self):
        value = self.cleaned_data.get('contract_mode')
        if not value:
            if self.instance and self.instance.pk and self.instance.contract_mode:
                return self.instance.contract_mode
            return ContractMode.CLE_EN_MAIN
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
