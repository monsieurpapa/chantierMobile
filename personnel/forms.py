"""ModelForms for the `personnel` app. Role/cabinet gating and the
"ENGINEER scoped to their own site" queryset narrowing both live in the
views (personnel/views.py) — these forms handle widgets and the
field-level validation each needs (e.g. Leave's date-range check)."""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Personnel, SiteAssignment, Skill, PersonnelDocument, Leave, Holiday
from projects.models import Site, ProjectPhase
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig
from core.widgets import DynamicSelectWidget, DynamicSelectMultipleWidget

class PersonnelForm(forms.ModelForm):
    """Personnel create/edit form — `payroll_type` must be set
    deliberately here (see ADR 0005); there's no cross-check against
    `personnel_type`/`category`."""
    class Meta:
        model = Personnel
        fields = [
            'first_name', 'last_name', 'personnel_type', 'category', 'trade', 'status', 'payroll_type',
            'skills', 'default_daily_rate', 'monthly_salary', 'user',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.FIRST_NAME}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LAST_NAME}),
            'personnel_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'trade': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payroll_type': forms.Select(attrs={'class': 'form-select'}),
            'skills': DynamicSelectMultipleWidget(
                create_url_name='personnel:skill_quick_create',
                placeholder=_('Sélectionner ou ajouter une compétence...'),
            ),
            'default_daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'monthly_salary': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }


class PersonnelDocumentForm(forms.ModelForm):
    """Uploads one file into a Personnel's dossier (label + file only;
    the `personnel` FK is set by the view, not this form)."""
    class Meta:
        model = PersonnelDocument
        fields = ['label', 'file']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Copie CNI, Diplôme...')}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class LeaveForm(forms.ModelForm):
    """Declares a leave; `personnel`'s queryset is narrowed per-request
    in LeaveCreateView.get_form() (HR_ADMIN_ROLES sees everyone, a plain
    ENGINEER only their own crew)."""
    class Meta:
        model = Leave
        fields = ['personnel', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        """Rejects an end_date before start_date. Note: this is
        form-level only — Leave has no model-level clean() doing the
        same check, so a Leave created or edited outside this form
        (shell, admin, a future API) isn't protected against an inverted
        date range."""
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            raise forms.ValidationError(_("La date de fin doit être postérieure à la date de début."))
        return cleaned


class HolidayForm(forms.ModelForm):
    """Adds a company-wide public holiday; `cabinet` is set by the view,
    not this form."""
    class Meta:
        model = Holiday
        fields = ['name', 'date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Fête de l\'indépendance')}),
            'date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
        }

class SiteAssignmentForm(forms.ModelForm):
    """Assigns a Personnel to a Site; `site`/`personnel` querysets are
    narrowed per-request in SiteAssignmentCreateView.get_form() (a plain
    ENGINEER only sees site(s) they lead)."""
    class Meta:
        model = SiteAssignment
        fields = [
            'personnel', 'site', 'role', 'start_date', 'end_date', 'daily_rate',
            'agreement_document', 'agreement_notes', 'convention_amount',
        ]
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.ROLE_EXAMPLE}),
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
            'daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'agreement_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'agreement_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'convention_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['convention_amount'].required = False
        # `role`/`start_date`/`daily_rate` became model-level optional
        # (blank=True/null=True) on 2026-10-06 so the lighter-weight
        # ConventionForm below (Personnel form's "Chantiers & conventions"
        # section) could skip them — but this is the full, standalone
        # affectation form, where they should stay mandatory as before.
        self.fields['role'].required = True
        self.fields['start_date'].required = True
        self.fields['daily_rate'].required = True


class ConventionForm(forms.ModelForm):
    """One row of the Personnel form's dynamic "Chantiers & conventions"
    section — a lightweight SiteAssignment capturing only `site`, a
    user-given convention `name`, the chantier `phase` (étape) it
    belongs to, and the optional `convention_amount`. `role`/dates/
    `daily_rate` are left unset (all optional at the model level) — a
    convention entered here is not a full affectation, just a payroll-
    facing note of what the person is owed for one task on one site.

    `new_phase_name` is not a model field: when set, the view resolves
    it via get-or-create (case-insensitive, scoped to `site`) instead of
    using `phase`, so the person filling the form can either pick an
    existing étape or name a brand-new one inline — see
    PersonnelCreateView/PersonnelUpdateView.form_valid()."""
    new_phase_name = forms.CharField(
        max_length=255, required=False,
        label=_('Nouvelle étape'),
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': _("Nom de la nouvelle étape, ex : Fondations"),
        }),
    )

    class Meta:
        model = SiteAssignment
        fields = ['site', 'phase', 'name', 'convention_amount']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': _("Nom de la convention, ex : Finition dalle bloc B"),
            }),
            'convention_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
        }

    def __init__(self, *args, cabinet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'].queryset = Site.objects.filter(cabinet=cabinet) if cabinet else Site.objects.none()
        self.fields['phase'].queryset = ProjectPhase.objects.filter(site__cabinet=cabinet) if cabinet else ProjectPhase.objects.none()
        self.fields['phase'].required = False
        self.fields['name'].required = False
        self.fields['convention_amount'].required = False

    def clean(self):
        """A row left entirely untouched (no site chosen) is treated as
        blank by the formset (see `ConventionFormSet`'s
        `can_delete_extra`/empty-form handling in the view) — but a row
        where the user picked a site must also name the convention and
        say which étape it's for, either by picking one or naming a new
        one."""
        cleaned = super().clean()
        site = cleaned.get('site')
        if not site:
            return cleaned
        if not cleaned.get('name'):
            raise forms.ValidationError(_("Donnez un nom à cette convention."))
        if not cleaned.get('phase') and not cleaned.get('new_phase_name'):
            raise forms.ValidationError(_("Choisissez une étape existante ou nommez-en une nouvelle."))
        return cleaned


ConventionFormSet = forms.inlineformset_factory(
    Personnel, SiteAssignment, form=ConventionForm,
    fk_name='personnel', extra=1, can_delete=True,
)


class SkillForm(forms.ModelForm):
    """Adds a Skill to the shared, non-cabinet-scoped catalog."""
    class Meta:
        model = Skill
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SKILL_NAME}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.DESCRIPTION}),
        }
