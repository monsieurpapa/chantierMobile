from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Personnel, SiteAssignment, Skill
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig

class PersonnelForm(forms.ModelForm):
    class Meta:
        model = Personnel
        fields = ['first_name', 'last_name', 'personnel_type', 'skills', 'default_daily_rate', 'user']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.FIRST_NAME}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LAST_NAME}),
            'personnel_type': forms.Select(attrs={'class': 'form-select'}),
            'skills': forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'multiple': 'multiple'}),
            'default_daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.AMOUNT}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }

class SiteAssignmentForm(forms.ModelForm):
    class Meta:
        model = SiteAssignment
        fields = ['personnel', 'site', 'role', 'start_date', 'end_date', 'daily_rate']
        widgets = {
            'personnel': forms.Select(attrs={'class': 'form-select'}),
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
        }

class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SKILL_NAME}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': FormPlaceholders.DESCRIPTION}),
        }
