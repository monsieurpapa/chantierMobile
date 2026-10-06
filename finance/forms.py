"""Forms for the finance app. Most of these are thin ModelForms whose real
validation lives in the model's own clean() (per the project-wide rule) —
the form-level `clean()` overrides here exist mainly to surface a budget/
amount error against the right field before a full_clean() round-trip, or
to scope a dynamic queryset (e.g. "which personnel can be picked here")
tighter than the bare model allows.
"""
import json

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Expense, Budget, ExpenseCategory, Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseLoan,
    PayrollList, PayrollListItem, SalaryPaymentList, SalaryPaymentItem, Avenant,
)
from chantiermobile.constants import (
    FormPlaceholders, DatePickerConfig, ValidationMessages, ExpenseNature,
    PersonnelPayrollType, PersonnelStatus,
)
from core.widgets import DynamicSelectWidget

class ExpenseForm(forms.ModelForm):
    """Expense submission form. Rebuilds the `personnel`/`phase` dropdown
    querysets from the submitted `site` (see __init__) so a POST validates
    against the right site even though the empty GET render had no site
    picked yet; `clean()` duplicates Expense.clean()'s budget check purely
    to raise it as a form-level error instead of waiting for
    instance.full_clean() on save."""
    class Meta:
        model = Expense
        fields = ['site', 'phase', 'category', 'nature', 'personnel', 'recipient', 'amount', 'expense_date', 'description', 'receipt_image']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'nature': forms.Select(attrs={'class': 'form-select', 'id': 'id_expense_nature'}),
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Rechercher un membre du personnel...'),
                depends_on='id_site', depends_param='site',
            ),
            'recipient': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _("Ex: Quincaillerie Kivu, Jean Mukendi..."),
            }),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.EXPENSE_DETAILS}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['personnel'].required = False
        self.fields['phase'].required = False
        # Not required: falls back to the model's MATERIEL default so
        # existing callers that don't send 'nature' keep working.
        self.fields['nature'].required = False
        # The personnel dropdown is scoped to "who's assigned to this site" —
        # populated client-side via the site_personnel_data endpoint once a
        # site is picked (see expense_form.html). To validate a POST (rather
        # than reject a legitimate choice because the queryset built for the
        # empty initial GET render didn't include it), rebuild the queryset
        # from whichever site was actually submitted/selected.
        from personnel.models import Personnel
        from projects.models import ProjectPhase
        site = None
        if self.data.get('site'):
            from projects.models import Site
            site = Site.objects.filter(pk=self.data.get('site')).first()
        elif self.instance and self.instance.pk:
            site = self.instance.site
        if site:
            self.fields['personnel'].queryset = Personnel.objects.filter(
                assignments__site=site
            ).distinct().order_by('first_name', 'last_name')
            self.fields['phase'].queryset = ProjectPhase.objects.filter(site=site).order_by('start_date')
        else:
            self.fields['personnel'].queryset = Personnel.objects.none()
            self.fields['phase'].queryset = ProjectPhase.objects.none()

    def clean_nature(self):
        # Not required (see __init__) — fall back to the model default
        # rather than saving an empty string when the caller omits it.
        return self.cleaned_data.get('nature') or ExpenseNature.MATERIEL

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        site = cleaned_data.get('site')
        nature = cleaned_data.get('nature')
        personnel = cleaned_data.get('personnel')

        # Validate positive amount
        if amount is not None and amount <= 0:
            raise forms.ValidationError({'amount': 'Amount must be a positive number.'})

        if nature == ExpenseNature.MAIN_DOEUVRE and not personnel:
            self.add_error('personnel', _("Sélectionnez le membre du personnel concerné par cette dépense de main d'œuvre."))

        # Check budget if site has one (only when amount is present and valid)
        if site and amount is not None and hasattr(site, 'budget'):
            budget = site.budget
            if budget.is_budget_exceeded(amount):
                remaining = budget.get_remaining_amount()
                raise forms.ValidationError(
                    f'Budget exceeded. Remaining budget: {remaining}. Requested amount: {amount}.'
                )

        return cleaned_data

class ExpensePayForm(forms.Form):
    """Picks which Caisse an approved expense is paid from (Expense.pay()).
    The queryset is set by the view to the expense's own cabinet's
    caisses."""
    caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse de décaissement'))


class BudgetForm(forms.ModelForm):
    """Budget create/edit form; clean() only checks end_date > start_date —
    the amount itself has no cap or minimum beyond the field's own
    DecimalField validation."""
    class Meta:
        model = Budget
        fields = ['site', 'total_amount', 'start_date', 'end_date']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
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

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError({'end_date': ValidationMessages.END_DATE_AFTER_START})
        return cleaned_data


class CaisseForm(forms.ModelForm):
    """Caisse create/edit form. `site` is optional (a caisse need not be
    tied to a single chantier). `responsible_cashier` (added 2026-10-06,
    permission table update) is optional too — a caisse with none set
    simply has no per-caisse modification restriction beyond
    CAISSE_MANAGE_ROLES/recorded_by; its queryset is narrowed to CASHIER/
    ACCOUNTANT holders of the owning cabinet by the view (CaisseCreateView/
    CaisseUpdateView.get_form()), since the form itself isn't handed the
    cabinet at construction time."""
    class Meta:
        model = Caisse
        fields = ['name', 'caisse_type', 'site', 'is_administrative', 'manual_site_entry', 'responsible_cashier']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Caisse principale')}),
            'caisse_type': forms.Select(attrs={'class': 'form-select'}),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'is_administrative': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'manual_site_entry': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'responsible_cashier': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'].required = False
        self.fields['responsible_cashier'].required = False


class CaisseTransactionForm(forms.ModelForm):
    """Manual ledger-entry form for one Caisse (passed in as the `caisse`
    kwarg). Swaps the `site` field for a free-text `external_site_label`
    when the caisse has manual_site_entry set (e.g. a bétonnière caisse
    serving external clients) — see __init__."""
    class Meta:
        model = CaisseTransaction
        fields = [
            'transaction_type', 'amount', 'date', 'description', 'site', 'external_site_label',
            'phase', 'recipient', 'category', 'proof',
        ]
        widgets = {
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'external_site_label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Chantier ou client externe')}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'recipient': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Qui a reçu / remis ce montant')}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'proof': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.caisse = kwargs.pop('caisse', None)
        super().__init__(*args, **kwargs)
        self.fields['site'].required = False
        self.fields['phase'].required = False
        self.fields['external_site_label'].required = False
        self.fields['category'].required = False
        self.fields['category'].queryset = CaisseTransactionCategory.objects.all()
        # Bétonnière-style caisses (manual_site_entry) serve external clients
        # who aren't in the system as a Site — show the free-text field
        # instead of forcing an internal chantier link. Regular caisses keep
        # the Site dropdown and never see the free-text field.
        if self.caisse and self.caisse.manual_site_entry:
            del self.fields['site']
            del self.fields['phase']
        else:
            del self.fields['external_site_label']
        from projects.models import ProjectPhase
        site = None
        if self.data.get('site'):
            from projects.models import Site
            site = Site.objects.filter(pk=self.data.get('site')).first()
        if 'phase' in self.fields:
            if site:
                self.fields['phase'].queryset = ProjectPhase.objects.filter(site=site).order_by('start_date')
            else:
                self.fields['phase'].queryset = ProjectPhase.objects.none()


class CaisseTransferForm(forms.Form):
    """Daily-remittance transfer form (Caisse.transfer_to()); the view
    additionally checks `amount <= caisse.balance` before calling
    transfer_to(), since this form has no access to the source caisse to
    validate that itself."""
    target_caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Vers'))
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant'))
    description = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_('Description'))


class CaisseLoanForm(forms.ModelForm):
    """CaisseLoan creation form; clean() duplicates the model's
    same-caisse check as a form-level error, ahead of full_clean()."""
    class Meta:
        model = CaisseLoan
        fields = ['lender_caisse', 'borrower_caisse', 'amount', 'date', 'notes']
        widgets = {
            'lender_caisse': forms.Select(attrs={'class': 'form-select'}),
            'borrower_caisse': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        lender, borrower = cleaned.get('lender_caisse'), cleaned.get('borrower_caisse')
        if lender and borrower and lender.pk == borrower.pk:
            raise forms.ValidationError(_("La caisse prêteuse et la caisse emprunteuse doivent être différentes."))
        return cleaned


class CaisseLoanRepayForm(forms.Form):
    """Partial-or-full repayment amount for CaisseLoan.repay(), which does
    its own "doesn't exceed what's owed" check."""
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant remboursé'))


class PayrollListForm(forms.ModelForm):
    """Creates the BROUILLON PayrollList shell (site + optional phase +
    notes) — items are added afterwards via PayrollListItemForm/
    PayrollListAllocateView."""
    class Meta:
        model = PayrollList
        fields = ['site', 'phase', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("Analyse de l'avancement du projet...")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phase'].required = False
        from projects.models import ProjectPhase
        site = None
        if self.data.get('site'):
            from projects.models import Site
            site = Site.objects.filter(pk=self.data.get('site')).first()
        elif self.instance and self.instance.pk:
            site = self.instance.site
        self.fields['phase'].queryset = ProjectPhase.objects.filter(site=site) if site else ProjectPhase.objects.none()


class PayrollListItemForm(forms.ModelForm):
    """Single-item add form for a PayrollList, scoped (via the `site`
    kwarg) to OUVRIER personnel assigned to that site — mirrors
    PayrollListItem.clean()'s payroll_type guard at the UI level."""
    class Meta:
        model = PayrollListItem
        fields = ['personnel', 'amount', 'progress_note', 'signed_receipt']
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'progress_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'signed_receipt': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        site = kwargs.pop('site', None)
        super().__init__(*args, **kwargs)
        self.fields['signed_receipt'].required = False
        from personnel.models import Personnel
        if site:
            # Liste de paie (chantier) is Main d'œuvre only — Ingénieurs &
            # Staff ne doivent pas apparaître ici, voir PayrollListItem.clean().
            self.fields['personnel'].queryset = Personnel.objects.filter(
                assignments__site=site, payroll_type=PersonnelPayrollType.OUVRIER,
            ).distinct()
            # This form has no "site" field of its own to depend on — the
            # site comes in as a fixed constructor kwarg — so bake it in as
            # a static extra param instead (see DynamicSelectWidget.create_extra).
            self.fields['personnel'].widget.attrs['data-create-extra'] = json.dumps({'site': site.pk})


class PayrollDisburseForm(forms.Form):
    """Picks which Caisse to disburse a PayrollList or SalaryPaymentList
    from (shared by both disburse() flows)."""
    caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse de décaissement'))


class SalaryPaymentListForm(forms.ModelForm):
    """"Ingénieurs & Staff" tab — creates the draft (brouillon) list itself;
    agents are added to it afterwards via SalaryPaymentItemForm, mirroring
    PayrollListForm/PayrollListItemForm."""
    class Meta:
        model = SalaryPaymentList
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _("Notes...")}),
        }


class SalaryPaymentItemForm(forms.ModelForm):
    """Single-item add form for a SalaryPaymentList, scoped (via the
    `cabinet` kwarg) to active INGENIEUR personnel in that cabinet —
    mirrors SalaryPaymentItem.clean()'s payroll_type guard."""
    class Meta:
        model = SalaryPaymentItem
        fields = ['personnel', 'period', 'amount', 'notes']
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ingénieur / membre du staff...'),
                # Fixed extra param sent on every quick-create from this
                # picker: without it, PersonnelQuickCreateView would fall
                # back to its default (Ouvrier) — see build_instance() —
                # which would immediately fail SalaryPaymentItem.clean()'s
                # Ingénieur-only guard for a name typed here.
                create_extra={'payroll_type': PersonnelPayrollType.INGENIEUR},
                attrs={'id': 'id_salary_personnel'},
            ),
            'period': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'AAAA-MM'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        cabinet = kwargs.pop('cabinet', None)
        super().__init__(*args, **kwargs)
        from personnel.models import Personnel
        # Paie du personnel is Ingénieurs & Staff only — Ouvriers belong on
        # the chantier-scoped Liste de paie instead, see SalaryPaymentItem.clean().
        personnel_qs = Personnel.objects.filter(
            payroll_type=PersonnelPayrollType.INGENIEUR, status=PersonnelStatus.ACTIF,
        ).order_by('last_name', 'first_name')
        if cabinet:
            personnel_qs = personnel_qs.filter(cabinet=cabinet)
        self.fields['personnel'].queryset = personnel_qs
        # Embedded so the template can auto-fill "amount" from
        # Personnel.monthly_salary when a name is picked (pure UX nicety —
        # the field stays editable, this just saves re-typing the usual figure).
        self.fields['personnel'].widget.attrs['data-monthly-salaries'] = json.dumps({
            str(p.pk): str(p.monthly_salary) for p in personnel_qs if p.monthly_salary is not None
        })


class AvenantForm(forms.ModelForm):
    """Avenant request form (site + amount + justification); the decision
    itself (approve/reject) is a separate AvenantDecisionForm, not this
    one."""
    class Meta:
        model = Avenant
        fields = ['site', 'amount', 'justification']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'justification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class AvenantDecisionForm(forms.Form):
    """Optional notes attached to an avenant approve/reject decision
    (Avenant.approve()/reject()'s `notes` argument)."""
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_('Notes'))
