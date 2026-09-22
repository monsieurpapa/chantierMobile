"""
Tests for the generic "select or add new" quick-create endpoints
(core.quickcreate.QuickCreateView and its per-app subclasses) that back
DynamicSelectWidget fields — the picker used wherever a form lets someone
pick or, if it doesn't exist yet, create a worker/material/supplier/skill
on the spot instead of routing through that record's own create screen.
"""
import json
from decimal import Decimal

import pytest
from django.urls import reverse

from personnel.models import Personnel, Skill, SiteAssignment
from materials.models import Material
from procurement.models import Supplier


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


@pytest.mark.django_db
class TestPersonnelQuickCreate:
    def test_creates_personnel_with_typed_name(self, director_client, cabinet):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': 'Jean Mukendi'})
        assert response.status_code == 200
        body = response.json()
        person = Personnel.objects.get(pk=body['id'])
        assert person.first_name == 'Jean'
        assert person.last_name == 'Mukendi'
        assert person.cabinet == cabinet
        assert person.default_daily_rate == Decimal('0.00')
        assert body['text'] == person.get_full_name()

    def test_single_word_name_leaves_last_name_blank(self, director_client):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': 'Kabila'})
        assert response.status_code == 200
        person = Personnel.objects.get(pk=response.json()['id'])
        assert person.first_name == 'Kabila'
        assert person.last_name == ''

    def test_with_site_context_creates_assignment(self, director_client, site):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': 'Alice Tshisekedi', 'site': site.pk})
        assert response.status_code == 200
        person = Personnel.objects.get(pk=response.json()['id'])
        assert SiteAssignment.objects.filter(personnel=person, site=site).exists()

    def test_without_site_context_no_assignment_created(self, director_client):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': 'Bob Kanku'})
        assert response.status_code == 200
        person = Personnel.objects.get(pk=response.json()['id'])
        assert not SiteAssignment.objects.filter(personnel=person).exists()

    def test_blank_name_rejected(self, director_client):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': '   '})
        assert response.status_code == 400
        assert 'error' in response.json()

    def test_requires_login(self, client):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(client, url, {'name': 'Nobody'})
        assert response.status_code in (302, 403)

    def test_scoped_to_requesting_users_cabinet(self, director_client, cabinet):
        url = reverse('personnel:personnel_quick_create')
        response = post_json(director_client, url, {'name': 'Chantal Ilunga'})
        person = Personnel.objects.get(pk=response.json()['id'])
        assert person.cabinet_id == cabinet.id


@pytest.mark.django_db
class TestSkillQuickCreate:
    def test_creates_skill_not_cabinet_scoped(self, director_client):
        url = reverse('personnel:skill_quick_create')
        response = post_json(director_client, url, {'name': 'Ferraillage'})
        assert response.status_code == 200
        skill = Skill.objects.get(pk=response.json()['id'])
        assert skill.name == 'Ferraillage'


@pytest.mark.django_db
class TestMaterialQuickCreate:
    def test_creates_material_with_default_unit(self, director_client):
        url = reverse('materials:material_quick_create')
        response = post_json(director_client, url, {'name': 'Gravier'})
        assert response.status_code == 200
        material = Material.objects.get(pk=response.json()['id'])
        assert material.name == 'Gravier'
        assert material.unit  # a placeholder unit was set, not blank

    def test_creates_material_with_given_unit(self, director_client):
        url = reverse('materials:material_quick_create')
        response = post_json(director_client, url, {'name': 'Sable', 'unit': 'm3'})
        material = Material.objects.get(pk=response.json()['id'])
        assert material.unit == 'm3'


@pytest.mark.django_db
class TestSupplierQuickCreate:
    def test_creates_supplier_scoped_to_cabinet(self, director_client, cabinet):
        url = reverse('procurement:supplier_quick_create')
        response = post_json(director_client, url, {'name': 'Quincaillerie Kivu'})
        assert response.status_code == 200
        supplier = Supplier.objects.get(pk=response.json()['id'])
        assert supplier.name == 'Quincaillerie Kivu'
        assert supplier.cabinet == cabinet
        assert response.json()['text'] == supplier.name
