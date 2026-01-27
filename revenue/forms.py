from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Contract, Invoice, Payment
from chantiermobile.constants import FormPlaceholders, DatePickerConfig

class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['site', 'client_name', 'total_value', 'signed_date']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.CLIENT_NAME}),
            'total_value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'signed_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
        }

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['contract', 'invoice_number', 'amount', 'issued_date', 'due_date', 'status']
        widgets = {
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.INVOICE_NUMBER}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'issued_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['invoice', 'amount', 'payment_date', 'method', 'reference']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.TRANSACTION_REFERENCE}),
        }
