from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Personnel, SiteAssignment, Skill, PersonnelDocument, Leave, Holiday
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig
from core.widgets import DynamicSelectWidget, DynamicSelectMultipleWidget

class PersonnelForm(forms.ModelForm):
    class Meta:
        model = Personnel
        fields = [
            'first_name', 'last_name', 'personnel_type', 'category', 'trade', 'status',
            'skills', 'default_daily_rate', 'monthly_salary', 'user',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.FIRST_NAME}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LAST_NAME}),
            'personnel_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'trade': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'skills': DynamicSelectMultipleWidget(
                create_url_name='personnel:skill_quick_create',
                placeholder=_('Sélectionner ou ajouter une compétence...'),
            ),
            'default_daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'monthly_salary': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }


class PersonnelDocumentForm(forms.ModelForm):
    class Meta:
        model = PersonnelDocument
        fields = ['label', 'file']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Copie CNI, Diplôme...')}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class LeaveForm(forms.ModelForm):
    class Meta:
        model = Leave
        fields = ['personnel', 'leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            raise forms.ValidationError(_("La date de fin doit être postérieure à la date de début."))
        return cleaned


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ['name', 'date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex: Fête de l\'indépendance')}),
            'date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker', 'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS,
            }),
        }

class SiteAssignmentForm(forms.ModelForm):
    class Meta:
        model = SiteAssignment
        fields = [
            'personnel', 'site', 'role', 'start_date', 'end_date', 'daily_rate',
            'agreement_document', 'agreement_notes',
        ]
        widgets = {
            'personnel': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.ROLE_EXAMPLE}),
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
            'daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'agreement_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'agreement_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SKILL_NAME}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.DESCRIPTION}),
        }
