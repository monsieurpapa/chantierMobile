from django import forms
from .models import Contract, Invoice, Payment

class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['site', 'client_name', 'total_value', 'signed_date']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client Name'}),
            'total_value': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'signed_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
        }

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['contract', 'invoice_number', 'amount', 'issued_date', 'due_date', 'status']
        widgets = {
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'INV-000'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'issued_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['invoice', 'amount', 'payment_date', 'method', 'reference']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Transaction Reference'}),
        }
