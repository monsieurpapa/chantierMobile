from django import forms
from .models import Personnel, SiteAssignment, Skill

class PersonnelForm(forms.ModelForm):
    class Meta:
        model = Personnel
        fields = ['first_name', 'last_name', 'skills', 'default_daily_rate', 'user']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'skills': forms.SelectMultiple(attrs={'class': 'form-select js-choice', 'multiple': 'multiple'}),
            'default_daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }

class SiteAssignmentForm(forms.ModelForm):
    class Meta:
        model = SiteAssignment
        fields = ['personnel', 'site', 'role', 'start_date', 'end_date', 'daily_rate']
        widgets = {
            'personnel': forms.Select(attrs={'class': 'form-select'}),
            'site': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "e.g. Chef d'équipe"}),
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
            'daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
        }

class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Skill Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Description...'}),
        }
