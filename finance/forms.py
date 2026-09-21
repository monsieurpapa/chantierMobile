from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Expense, Budget, ExpenseCategory
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ValidationMessages, ExpenseNature

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['site', 'category', 'nature', 'personnel', 'amount', 'expense_date', 'description', 'receipt_image']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'nature': forms.Select(attrs={'class': 'form-select', 'id': 'id_expense_nature'}),
            'personnel': forms.Select(attrs={
                'class': 'form-select', 'data-control': 'select2',
                'data-placeholder': _('Rechercher un membre du personnel...'),
            }),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.EXPENSE_DETAILS}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['personnel'].required = False
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
        else:
            self.fields['personnel'].queryset = Personnel.objects.none()

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
