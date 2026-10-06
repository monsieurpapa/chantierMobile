"""Forms for the revenue app: contracts, invoices, payments, and the two
inline-formset-backed line-item editors (Devis/DevisLine,
SituationTravaux/SituationLine)."""
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory
from .models import Contract, Invoice, Payment, Devis, DevisLine, SituationTravaux, SituationLine
from chantiermobile.constants import FormPlaceholders, DatePickerConfig

class ContractForm(forms.ModelForm):
    """Contract create/edit form (site, client, value, signed date)."""
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
    # 'status' is deliberately NOT an editable field here — every other
    # status-driven workflow in this app (Devis, SituationTravaux,
    # MaterialRequest, Expense...) changes status only through a dedicated
    # action endpoint (see invoice_send/invoice_cancel below), never via a
    # raw dropdown on the create/edit form. An invoice always starts DRAFT
    # (the model's own default) and moves on from there via those actions.
    class Meta:
        model = Invoice
        fields = ['contract', 'invoice_number', 'amount', 'issued_date', 'due_date']
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
        }

class PaymentForm(forms.ModelForm):
    """Records a Payment against an invoice; saving it (outside this form,
    via Payment.save()) auto-marks the invoice PAID once fully covered."""
    class Meta:
        model = Payment
        fields = ['invoice', 'amount', 'payment_date', 'method', 'reference', 'proof_of_payment']
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
            'proof_of_payment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proof_of_payment'].required = False


class DevisForm(forms.ModelForm):
    """Devis header form (site/client/dates/photo/notes); line items are
    edited separately via DevisLineFormSet."""
    class Meta:
        model = Devis
        fields = ['site', 'devis_number', 'client_name', 'issue_date', 'validity_date', 'photo', 'notes']
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
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required = False


class DevisLineForm(forms.ModelForm):
    """One priced line on a Devis; used as the form for DevisLineFormSet."""
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


# min_num/validate_min=True by default here — the create/update views
# (DevisCreateView/DevisUpdateView) override both to 0/False at runtime
# when the devis has a photo attached instead of typed-in lines.
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
    """Situation header form (contract/numero/period_end_date/notes); lines
    are edited separately via SituationLineFormSet, scoped to the
    contract's source Devis lines by the view."""
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
    """One DevisLine's cumulative % on a SituationTravaux; used as the form
    for SituationLineFormSet."""
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
