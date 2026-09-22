from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Task
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig
from core.widgets import DynamicSelectWidget


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['site', 'phase', 'title', 'description', 'priority', 'due_date', 'assigned_to']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.TASK_TITLE}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.DESCRIPTION, 'rows': 3}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'assigned_to': DynamicSelectWidget(
                create_url_name='personnel:personnel_quick_create',
                placeholder=_('Sélectionner ou ajouter un ouvrier...'),
            ),
        }
