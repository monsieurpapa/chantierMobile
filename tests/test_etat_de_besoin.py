"""État de besoin naming and its catalogue picker (2026-10-21).

- One name ("État de besoin") and one numbering ("EB-12") everywhere.
- Every line's material picker is fed by the Catalogue des matériaux,
  including lines added with "+" (cloned from the formset's empty form).
- Quick-adding "Nom (unité)" from the picker creates the material with
  that unit, reuses an existing catalogue entry, and returns the unit and
  cost so the line updates without a reload.
"""
import json
from decimal import Decimal

import pytest
from django.urls import reverse

from materials.models import Material, MaterialRequest, MaterialRequestItem


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


@pytest.mark.django_db
class TestNaming:
    def test_reference_and_str(self, site, user):
        req = MaterialRequest.objects.create(site=site, requested_by=user)
        assert req.reference == f'EB-{req.pk}'
        assert str(req).startswith(f'État de besoin EB-{req.pk}')
        assert MaterialRequest._meta.verbose_name == 'État de besoin'

    def test_list_page_uses_new_name(self, director_client):
        response = director_client.get(reverse('materials:request_list'), HTTP_ACCEPT_LANGUAGE='fr')
        content = response.content.decode()
        assert 'États de besoin' in content
        assert 'Demandes de matériaux' not in content


@pytest.mark.django_db
class TestCataloguePicker:
    @pytest.fixture
    def lead_client(self, engineer_client, engineer_user, site):
        site.lead_engineer = engineer_user
        site.save(update_fields=['lead_engineer'])
        return engineer_client

    def test_added_line_template_carries_full_catalogue(self, lead_client):
        Material.objects.create(name='Ciment', unit='sac', estimated_cost_per_unit=Decimal('12'))
        Material.objects.create(name='Fer à béton 12', unit='barre')
        response = lead_client.get(reverse('materials:request_create'))
        assert response.status_code == 200
        content = response.content.decode()
        template = content[content.index('id="material-row-template"'):]
        template = template[:template.index('</template>')]
        assert 'name="items-__prefix__-material"' in template
        assert 'data-control="select2"' in template
        assert reverse('materials:material_quick_create') in template
        assert 'Ciment (sac)' in template
        assert 'Fer à béton 12 (barre)' in template

    def test_submit_with_catalogue_and_quick_added_material(self, lead_client, site):
        ciment = Material.objects.create(name='Ciment', unit='sac')
        created = post_json(lead_client, reverse('materials:material_quick_create'), {'name': 'Gravier 5/15 (m3)'}).json()
        data = {
            'site': site.pk, 'notes': '',
            'items-TOTAL_FORMS': '2', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-material': ciment.pk, 'items-0-quantity': '10',
            'items-1-material': created['id'], 'items-1-quantity': '3',
        }
        response = lead_client.post(reverse('materials:request_create'), data)
        assert response.status_code == 302
        req = MaterialRequest.objects.get(site=site)
        lines = {i.material.name: i.quantity for i in MaterialRequestItem.objects.filter(request=req)}
        assert lines == {'Ciment': Decimal('10'), 'Gravier 5/15': Decimal('3')}


@pytest.mark.django_db
class TestMaterialQuickAdd:
    url = staticmethod(lambda: reverse('materials:material_quick_create'))

    def test_parses_unit_suffix(self, director_client):
        body = post_json(director_client, self.url(), {'name': 'Treillis soudé 15x15 (rouleau)'}).json()
        material = Material.objects.get(pk=body['id'])
        assert (material.name, material.unit) == ('Treillis soudé 15x15', 'rouleau')
        assert body['text'] == 'Treillis soudé 15x15 (rouleau)'
        assert body['unit'] == 'rouleau'
        assert body['cost_per_unit'] == 0

    def test_reuses_existing_catalogue_entry(self, director_client):
        existing = Material.objects.create(name='Ciment gris CPJ', unit='sac', estimated_cost_per_unit=Decimal('12.50'))
        body = post_json(director_client, self.url(), {'name': 'ciment gris cpj (SAC)'}).json()
        assert body['id'] == existing.pk
        assert body['cost_per_unit'] == 12.5
        assert Material.objects.filter(name__iexact='ciment gris cpj').count() == 1

    def test_plain_name_keeps_default_unit(self, director_client):
        body = post_json(director_client, self.url(), {'name': 'Gravier'}).json()
        assert Material.objects.get(pk=body['id']).name == 'Gravier'
        assert body['unit']
