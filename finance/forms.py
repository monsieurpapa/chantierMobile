from django import forms
from .models import Expense, Budget, ExpenseCategory

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['site', 'category', 'amount', 'description', 'receipt_image']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Expense details...'}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['site', 'total_amount', 'start_date', 'end_date']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError(_("End date must be after start date."))
        return cleaned_data
