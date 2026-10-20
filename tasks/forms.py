"""ModelForm for the `tasks` app. Cabinet-scoping of the `site`/`phase`/
`assigned_to` querysets happens per-request in the view
(tasks/views.py's `_scope_form_querysets`), not here."""
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Task
from chantiermobile.constants import FormPlaceholders, FormHelpTexts, DatePickerConfig
from core.widgets import DynamicSelectWidget
from projects.phase_fields import PhaseCatalogFormMixin, enable_phase_catalog


class TaskForm(PhaseCatalogFormMixin, forms.ModelForm):
    """Task create/edit form. Status isn't a field here — transitions go
    through Task.start/complete/block/reopen, not a form save."""
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

    def offer_phase_catalog(self, site_qs):
        """Adds the Catalogue des étapes to the `phase` select for the
        task's chantier: the submitted one on a POST, else the task's own
        or the ?site= initial one. Limited to `site_qs` (the requester's
        cabinet-scoped sites), so a catalog étape can only ever be created
        on a chantier the user may already pick."""
        site_id = self.data.get(self.add_prefix('site')) if self.is_bound else None
        if not site_id:
            if self.instance and self.instance.site_id:
                site_id = self.instance.site_id
            else:
                initial_site = self.initial.get('site')
                site_id = getattr(initial_site, 'pk', initial_site)
        site = site_qs.filter(pk=site_id).first() if site_id and str(site_id).isdigit() else None
        enable_phase_catalog(self, 'phase', [site])
