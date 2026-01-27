from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Expense, Budget, ExpenseCategory
from chantiermobile.constants import FormPlaceholders, DatePickerConfig, ValidationMessages

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['site', 'category', 'amount', 'description', 'receipt_image']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.EXPENSE_DETAILS}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

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
            raise forms.ValidationError(ValidationMessages.END_DATE_AFTER_START)
        return cleaned_data
