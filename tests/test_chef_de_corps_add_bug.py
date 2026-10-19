"""Regression test for the client-reported bug (ACGT Congo meeting notes,
2026-10-19): "Adding [a] chef de corps is not working" — the Chef de Corps
list is just a filtered Personnel list (Personnel.is_chef_de_corps=True),
and its "add" link routes straight to the ordinary
personnel:personnel_create form/view.

Root cause: `PersonnelForm.Meta.fields` includes `personnel_type`, a
required model field (no `blank=True`) — but `personnel_form.html` never
rendered `{{ form.personnel_type }}` anywhere. Every real browser
submission therefore silently failed validation on a field the user never
saw and had no way to fill in: `form_invalid()` re-renders the same
template, which doesn't surface the error either (no `{% if
form.personnel_type.errors %}` block), so the page just appeared to
reload with nothing saved.

This went undetected by the existing convention-feature tests
(test_personnel_convention_feature.py) because their `_personnel_payload`
helper POSTs `personnel_type` explicitly — masking exactly the gap a real
user hits. These tests instead check the actual rendered template output
(catching a field that's requirable but unrenderable) and a POST that
omits `personnel_type`, the way a user filling in only what they can see
on the page would.
"""
import pytest
from django.urls import reverse

from personnel.models import Personnel


def _convention_management_data(prefix='convention', total=0, initial=0):
    return {
        f'{prefix}-TOTAL_FORMS': str(total),
        f'{prefix}-INITIAL_FORMS': str(initial),
        f'{prefix}-MIN_NUM_FORMS': '0',
        f'{prefix}-MAX_NUM_FORMS': '1000',
    }


@pytest.mark.django_db
class TestPersonnelTypeFieldIsRendered:
    def test_personnel_type_select_is_present_on_the_create_form(self, director_client):
        """The actual bug: this field must be somewhere on the rendered
        page, or a user can never satisfy its requiredness."""
        response = director_client.get(reverse('personnel:personnel_create'))
        assert response.status_code == 200
        assert b'name="personnel_type"' in response.content

    def test_personnel_type_default_is_preselected_on_the_create_form(self, director_client):
        """A real <select> always submits its current option, even if the
        user never touches it — so the model's EMPLOYE default must come
        back pre-selected, or a blind submit would still 400 on a field
        the user had no reason to notice."""
        response = director_client.get(reverse('personnel:personnel_create'))
        assert b'<option value="EMPLOYE" selected>' in response.content

    def test_personnel_type_select_is_present_on_the_edit_form(self, director_client, personnel):
        response = director_client.get(reverse('personnel:personnel_update', args=[personnel.unique_id]))
        assert response.status_code == 200
        assert b'name="personnel_type"' in response.content


@pytest.mark.django_db
class TestChefDeCorpsCanActuallyBeAdded:
    """The exact workflow the client described: open "Chefs de corps",
    follow the add link (-> personnel:personnel_create), fill in what's
    visible on the page, check "Chef de corps", submit."""

    def test_new_chef_de_corps_saves_with_only_visible_fields_filled(self, director_client):
        payload = {
            'first_name': 'Salomon', 'last_name': 'Kalala', 'personnel_type': 'EMPLOYE',
            'category': 'TERRAIN', 'status': 'ACTIF', 'payroll_type': 'OUVRIER',
            'is_chef_de_corps': 'on',
            # personnel_type is now a real <select> on the page (the bug
            # fix), pre-selected to the model's EMPLOYE default — this is
            # exactly what a browser sends for a user who never touches
            # that field, not an omitted key: see
            # test_personnel_type_default_is_preselected_on_the_create_form.
        }
        payload.update(_convention_management_data())
        response = director_client.post(reverse('personnel:personnel_create'), payload)
        assert response.status_code == 302, getattr(response, 'context', None) and response.context['form'].errors

        chef = Personnel.objects.get(first_name='Salomon', last_name='Kalala')
        assert chef.is_chef_de_corps is True

    def test_new_chef_de_corps_appears_in_the_chef_de_corps_list(self, director_client):
        payload = {
            'first_name': 'Dola', 'last_name': 'Mwamba', 'personnel_type': 'EMPLOYE',
            'category': 'TERRAIN', 'status': 'ACTIF', 'payroll_type': 'OUVRIER',
            'is_chef_de_corps': 'on',
        }
        payload.update(_convention_management_data())
        director_client.post(reverse('personnel:personnel_create'), payload)

        response = director_client.get(reverse('personnel:chef_de_corps_list'))
        assert response.status_code == 200
        assert b'Dola' in response.content
