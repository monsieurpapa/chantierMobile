from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Expense, Budget, ExpenseCategory
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ValidationMessages

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['site', 'category', 'amount', 'expense_date', 'description', 'receipt_image']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'expense_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.EXPENSE_DETAILS}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        site = cleaned_data.get('site')
        
        # Validate positive amount
        if amount is not None and amount <= 0:
            raise forms.ValidationError({'amount': 'Amount must be a positive number.'})
        
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
