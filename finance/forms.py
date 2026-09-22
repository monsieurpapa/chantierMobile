import json

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Expense, Budget, ExpenseCategory, Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseLoan,
    PayrollList, PayrollListItem, Avenant,
)
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ValidationMessages, ExpenseNature
from core.widgets import DynamicSelectWidget

class ExpenseForm(forms.ModelForm):
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
    caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse de décaissement'))


class BudgetForm(forms.ModelForm):
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
    class Meta:
        model = Caisse
        fields = ['name', 'caisse_type', 'site', 'is_administrative', 'manual_site_entry']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Caisse principale')}),
            'caisse_type': forms.Select(attrs={'class': 'form-select'}),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'is_administrative': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'manual_site_entry': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'].required = False


class CaisseTransactionForm(forms.ModelForm):
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
    target_caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Vers'))
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant'))
    description = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_('Description'))


class CaisseLoanForm(forms.ModelForm):
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
    amount = forms.DecimalField(min_value=0.01, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control'}), label=_('Montant remboursé'))


class PayrollListForm(forms.ModelForm):
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
            self.fields['personnel'].queryset = Personnel.objects.filter(assignments__site=site).distinct()
            # This form has no "site" field of its own to depend on — the
            # site comes in as a fixed constructor kwarg — so bake it in as
            # a static extra param instead (see DynamicSelectWidget.create_extra).
            self.fields['personnel'].widget.attrs['data-create-extra'] = json.dumps({'site': site.pk})


class PayrollDisburseForm(forms.Form):
    caisse = forms.ModelChoiceField(queryset=Caisse.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}), label=_('Caisse de décaissement'))


# NOTE: SalaryPaymentForm removed along with the "Salaires du bureau" UI —
# see finance.models.SalaryPayment's DEPRECATED docstring. The model stays
# for historical data but is no longer reachable from any form/view.


class AvenantForm(forms.ModelForm):
    class Meta:
        model = Avenant
        fields = ['site', 'amount', 'justification']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'justification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class AvenantDecisionForm(forms.Form):
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_('Notes'))
