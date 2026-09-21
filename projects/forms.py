from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Site, ProjectPhase, SiteProgress, PlanningSubmission
from chantiermobile.constants import FormPlaceholders, DatePickerConfig

class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ['name', 'location', 'status', 'start_date', 'expected_end_date', 'lead_engineer']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.SITE_NAME}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.LOCATION}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'expected_end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'lead_engineer': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lead_engineer'].required = False

class ProjectPhaseForm(forms.ModelForm):
    class Meta:
        model = ProjectPhase
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': FormPlaceholders.PHASE_NAME}),
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

class PlanningSubmissionForm(forms.ModelForm):
    class Meta:
        model = PlanningSubmission
        fields = ['phase', 'description']
        widgets = {
            'phase': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': _('Décrivez la planification à soumettre...')}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phase'].required = False


class SiteProgressForm(forms.ModelForm):
    class Meta:
        model = SiteProgress
        fields = ['report_date', 'percentage_complete', 'description']
        widgets = {
            'report_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': DatePickerConfig.DATE_FORMAT,
                'data-options': DatePickerConfig.OPTIONS
            }),
            'percentage_complete': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': '3', 'placeholder': FormPlaceholders.PROGRESS_DESCRIPTION}),
        }
