"""ModelForms for the `personnel` app. Role/cabinet gating and the
"ENGINEER scoped to their own site" queryset narrowing both live in the
views (personnel/views.py) — these forms handle widgets and the
field-level validation each needs (e.g. Leave's date-range check)."""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Personnel, SiteAssignment, Skill, PersonnelDocument, Leave, Holiday, ConventionAvenant, PersonnelEvaluation
from projects.models import Site, ProjectPhase
from projects.phase_fields import PhaseCatalogFormMixin, enable_phase_catalog
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig, ConventionScope
from core.widgets import DynamicSelectWidget, DynamicSelectMultipleWidget

class PersonnelForm(forms.ModelForm):
    """Personnel create/edit form — `payroll_type` must be set
    deliberately here (see ADR 0005); there's no cross-check against
    `personnel_type`/`category`."""
    class Meta:
        model = Personnel
        fields = [
            'first_name', 'last_name', 'phone_number', 'whatsapp_opt_in', 'personnel_type', 'category', 'trade', 'status', 'payroll_type',
            'is_chef_de_corps', 'skills', 'experience_notes', 'default_daily_rate', 'monthly_salary', 'user',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.FIRST_NAME}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LAST_NAME}),
            'whatsapp_opt_in': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'personnel_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'trade': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payroll_type': forms.Select(attrs={'class': 'form-select'}),
            'is_chef_de_corps': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'skills': DynamicSelectMultipleWidget(
                create_url_name='personnel:skill_quick_create',
                placeholder=_('Sélectionner ou ajouter une compétence...'),
            ),
            'experience_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("Compétences, diplômes, expérience professionnelle...")}),
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
        # `role` may be left empty: it then takes the person's corps de
        # métier (clean_role below).
        self.fields['role'].required = False
        self.fields['start_date'].required = True
        self.fields['daily_rate'].required = True
        # 2026-10-21: the picker shows each person's corps de métier.
        self.fields['personnel'].label_from_instance = lambda p: p.name_with_metier
        self.fields['role'].label = _('Rôle sur le chantier')
        self.fields['role'].widget = forms.Select(attrs={
            'class': 'form-select', 'data-control': 'select2', 'data-tags': 'true',
            'data-placeholder': _("Corps de métier ou rôle (ex. Chef d'équipe)"),
            'data-create-label': _('Ajouter le rôle'),
        })

    def role_choices(self):
        """The corps de métier, then roles already used on this cabinet's
        chantiers, then whatever is set now — the role picker's options;
        anything else can be typed in."""
        from chantiermobile.constants import Trade
        seen, choices = set(), [('', '')]

        def add(label):
            label = (label or '').strip()
            if label and label.lower() not in seen:
                seen.add(label.lower())
                choices.append((label, label))

        for _value, label in Trade.choices:
            add(str(label))
        sites = self.fields['site'].queryset
        for role in (SiteAssignment.objects.filter(site__in=sites).exclude(role='')
                     .values_list('role', flat=True).distinct().order_by('role')[:200]):
            add(role)
        add(self.data.get(self.add_prefix('role')) if self.is_bound else self.initial.get('role') or self.instance.role)
        return choices

    def personnel_info(self):
        """{pk: {"metier", "rate"}} for the page's script, which fills the
        role (and an empty daily rate) as soon as a person is picked."""
        return {
            str(p.pk): {'metier': p.metier, 'rate': str(p.default_daily_rate) if p.default_daily_rate is not None else ''}
            for p in self.fields['personnel'].queryset.only('pk', 'trade', 'default_daily_rate')
        }

    def clean_role(self):
        role = (self.cleaned_data.get('role') or '').strip()
        if not role:
            person = self.cleaned_data.get('personnel')
            if person is not None and person.metier:
                return person.metier
            raise forms.ValidationError(_("Indiquez son rôle sur le chantier (ou renseignez son corps de métier sur sa fiche)."))
        return role

    def clean(self):
        cleaned = super().clean()
        # clean_role runs before `personnel` is known when the field order
        # puts it first; settle an empty role here too.
        if not cleaned.get('role') and cleaned.get('personnel') is not None and cleaned['personnel'].metier:
            cleaned['role'] = cleaned['personnel'].metier
            self.errors.pop('role', None)
        return cleaned

    def save(self, commit=True):
        assignment = super().save(commit=commit)
        # A role that is one of the corps de métier fills in the person's
        # own métier when their file has none yet.
        from chantiermobile.constants import Trade
        person = assignment.personnel
        if commit and person is not None and not person.trade:
            by_label = {str(label).lower(): value for value, label in Trade.choices}
            trade = by_label.get((assignment.role or '').strip().lower())
            if trade:
                person.trade = trade
                person.save(update_fields=['trade', 'updated_at'])
        return assignment


class ConventionForm(PhaseCatalogFormMixin, forms.ModelForm):
    """One row of the Personnel form's dynamic "Chantiers & conventions"
    section — a lightweight SiteAssignment capturing only `site`, a
    user-given convention `name`, its `scope` (par étape / chantier
    entier — added 2026-10-19), the chantier `phase` (étape) it belongs
    to when scoped par étape, and the optional `convention_amount`.
    `role`/dates/`daily_rate` are left unset (all optional at the model
    level) — a convention entered here is not a full affectation, just a
    payroll-facing note of what the person is owed for one task (or the
    whole chantier) on one site.

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
        fields = ['site', 'scope', 'phase', 'name', 'convention_amount']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'scope': forms.Select(attrs={'class': 'form-select convention-scope'}),
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
        # Also offer the Catalogue des étapes for this row's chantier (the
        # submitted one, else the convention's own) — always one of the
        # cabinet's sites, like the `site` field itself.
        row_site_id = self.data.get(self.add_prefix('site')) if self.is_bound else None
        if not row_site_id and self.instance and self.instance.site_id:
            row_site_id = self.instance.site_id
        row_site = None
        if cabinet and row_site_id and str(row_site_id).isdigit():
            row_site = Site.objects.filter(cabinet=cabinet, pk=row_site_id).first()
        enable_phase_catalog(self, 'phase', [row_site])
        self.fields['name'].required = False
        self.fields['convention_amount'].required = False
        self.fields['scope'].required = False
        # Matches the form's pre-existing behavior (phase required by
        # default) for a brand-new row — the person can still switch it
        # to "chantier entier" before submitting.
        if not self.initial.get('scope') and not (self.instance and self.instance.pk):
            self.initial['scope'] = ConventionScope.PAR_ETAPE

    def clean(self):
        """A row left entirely untouched (no site chosen) is treated as
        blank by the formset (see `ConventionFormSet`'s
        `can_delete_extra`/empty-form handling in the view) — but a row
        where the user picked a site must also name the convention, and
        — only when scoped par étape (the default) — say which étape
        it's for, either by picking one or naming a new one. A
        "chantier entier" convention skips the étape requirement
        entirely and clears any phase/new_phase_name the user had
        picked before switching scope, so the two stay consistent (see
        SiteAssignment.clean())."""
        cleaned = super().clean()
        site = cleaned.get('site')
        if not site:
            return cleaned
        if not cleaned.get('name'):
            raise forms.ValidationError(_("Donnez un nom à cette convention."))
        scope = cleaned.get('scope') or ConventionScope.PAR_ETAPE
        cleaned['scope'] = scope
        if scope == ConventionScope.CHANTIER_ENTIER:
            cleaned['phase'] = None
            cleaned['new_phase_name'] = ''
        elif not cleaned.get('phase') and not cleaned.get('new_phase_name'):
            raise forms.ValidationError(_("Choisissez une étape existante ou nommez-en une nouvelle."))
        return cleaned


ConventionFormSet = forms.inlineformset_factory(
    Personnel, SiteAssignment, form=ConventionForm,
    fk_name='personnel', extra=1, can_delete=True,
)


class ConventionAvenantForm(forms.Form):
    """Records one avenant on an existing convention (SiteAssignment) —
    backs ConventionAvenantCreateView. A plain Form, not a ModelForm:
    `assignment`/`previous_amount`/`recorded_by` are supplied by the view
    (from the URL and the logged-in user), not typed by the caissière —
    see ConventionAvenant.record()."""
    date = forms.DateField(
        label=_("Date de l'avenant"),
        widget=forms.DateInput(attrs={
            'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
            'data-options': DatePickerConfig.OPTIONS,
        }),
    )
    new_amount = forms.DecimalField(
        label=_('Nouveau montant de la convention'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
    )
    reason = forms.CharField(
        label=_('Motif'),
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': _("Ex : surplus de travail annoncé par le chef technique..."),
        }),
    )

    def clean_new_amount(self):
        amount = self.cleaned_data['new_amount']
        if amount < 0:
            raise forms.ValidationError(_('Le montant ne peut pas être négatif.'))
        return amount


class PersonnelEvaluationForm(PhaseCatalogFormMixin, forms.ModelForm):
    """One cotation entered from a Personnel's detail page — `personnel`
    and `evaluated_by` are set by the view, not this form. `phase`'s
    queryset is narrowed to the evaluator's own cabinet, same pattern as
    ConventionForm.phase.

    GOTCHA (same timing issue already fixed once for ConventionForm /
    SiteAssignment.clean() — see that model's docstring): a CreateView
    only assigns `form.instance.personnel` in `form_valid()`, *after*
    `is_valid()` has already run the model's own `clean()` — so by the
    time PersonnelEvaluation.clean()'s site-history check would run,
    `personnel_id` is still None and the check silently no-ops. The
    `personnel` kwarg here lets this form do that same check itself,
    with the right data, at the right time."""
    class Meta:
        model = PersonnelEvaluation
        fields = ['phase', 'note_chiffree', 'mention_qualitative', 'observation']
        widgets = {
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'note_chiffree': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 20, 'placeholder': _('ex : 15')}),
            'mention_qualitative': forms.Select(attrs={'class': 'form-select'}),
            'observation': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("Observation sur la prestation à cette étape...")}),
        }

    def __init__(self, *args, cabinet=None, personnel=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._personnel = personnel
        self.fields['phase'].queryset = ProjectPhase.objects.filter(site__cabinet=cabinet) if cabinet else ProjectPhase.objects.none()
        # Also offer the Catalogue des étapes, for each chantier this person
        # is assigned to (the only chantiers clean() accepts anyway).
        catalog_sites = []
        if cabinet and personnel is not None:
            catalog_sites = list(Site.objects.filter(
                cabinet=cabinet, pk__in=personnel.assignments.values('site_id'),
            ).order_by('name'))
        enable_phase_catalog(self, 'phase', catalog_sites)
        self.fields['note_chiffree'].required = False
        self.fields['mention_qualitative'].required = False

    def clean(self):
        """At-least-one-rating-dimension rule (mirrors
        PersonnelEvaluation.clean(), which still applies this same rule
        for any non-form creation path) plus the site-history check —
        see the class docstring for why that one has to live here
        rather than only on the model."""
        cleaned = super().clean()
        if cleaned.get('note_chiffree') is None and not cleaned.get('mention_qualitative'):
            raise forms.ValidationError(_("Donnez au moins une note chiffrée ou une mention qualitative."))
        phase = cleaned.get('phase')
        if self._personnel and phase and phase.site_id:
            if not self._personnel.assignments.filter(site_id=phase.site_id).exists():
                self.add_error('phase', _("Cette personne n'a aucune affectation connue sur le chantier de cette étape."))
        return cleaned


class SkillForm(forms.ModelForm):
    """Adds a Skill to the shared, non-cabinet-scoped catalog."""
    class Meta:
        model = Skill
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SKILL_NAME}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.DESCRIPTION}),
        }
