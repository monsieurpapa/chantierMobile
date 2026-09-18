from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Contract, Invoice, Payment, Devis, DevisLine, SituationTravaux, SituationLine
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


class DevisForm(forms.ModelForm):
    class Meta:
        model = Devis
        fields = ['site', 'devis_number', 'client_name', 'issue_date', 'validity_date', 'notes']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'devis_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.DEVIS_NUMBER}),
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.CLIENT_NAME}),
            'issue_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'validity_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class DevisLineForm(forms.ModelForm):
    class Meta:
        model = DevisLine
        fields = ['designation', 'unit', 'quantity', 'unit_price_ht', 'order']
        widgets = {
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.DESIGNATION}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.MATERIAL_UNIT}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': FormPlaceholders.AMOUNT}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


DevisLineFormSet = inlineformset_factory(
    Devis,
    DevisLine,
    form=DevisLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class SituationTravauxForm(forms.ModelForm):
    class Meta:
        model = SituationTravaux
        fields = ['contract', 'numero', 'period_end_date', 'notes']
        widgets = {
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'numero': forms.NumberInput(attrs={'class': 'form-control'}),
            'period_end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SituationLineForm(forms.ModelForm):
    class Meta:
        model = SituationLine
        fields = ['devis_line', 'cumulative_percentage']
        widgets = {
            'devis_line': forms.Select(attrs={'class': 'form-select'}),
            'cumulative_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
        }


SituationLineFormSet = inlineformset_factory(
    SituationTravaux,
    SituationLine,
    form=SituationLineForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
