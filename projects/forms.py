from django import forms
from .models import Site, ProjectPhase, SiteProgress

class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ['name', 'location', 'status', 'start_date', 'expected_end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Site Name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location / Address'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'expected_end_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
        }

class ProjectPhaseForm(forms.ModelForm):
    class Meta:
        model = ProjectPhase
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phase Name (e.g. Foundation)'}),
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

class SiteProgressForm(forms.ModelForm):
    class Meta:
        model = SiteProgress
        fields = ['report_date', 'percentage_complete', 'description']
        widgets = {
            'report_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker',
                'placeholder': 'YYYY-MM-DD',
                'data-options': '{"dateFormat":"Y-m-d","disableMobile":true}'
            }),
            'percentage_complete': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': '3', 'placeholder': 'What was accomplished today?'}),
        }
