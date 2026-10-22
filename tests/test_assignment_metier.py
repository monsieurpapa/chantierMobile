"""Corps de métier when assigning personnel to a chantier (2026-10-21).

- The person picker and the chantier's crew show each person's métier.
- The role defaults to the person's métier; another role can be picked
  from the métiers / roles already used, or typed in.
- A role that is a métier fills in an empty métier on the person's file.
- Quick-adding "Jean Mumbere (Maçon)" from the picker records the métier.
"""
import json
from datetime import date

import pytest
from django.urls import reverse

from chantiermobile.constants import Trade
from personnel.models import Personnel, SiteAssignment


@pytest.fixture
def macon(cabinet):
    return Personnel.objects.create(cabinet=cabinet, first_name='Jean', last_name='Mumbere', trade=Trade.MACON, default_daily_rate=15)


@pytest.fixture
def sans_metier(cabinet):
    return Personnel.objects.create(cabinet=cabinet, first_name='Amani', last_name='Kahindo', default_daily_rate=10)


def assign_data(person, site, role=''):
    return {'personnel': person.pk, 'site': site.pk, 'role': role, 'start_date': date.today().isoformat(), 'daily_rate': '15'}


@pytest.mark.django_db
class TestAssignmentForm:
    url = staticmethod(lambda: reverse('personnel:assignment_create'))

    def test_picker_and_role_options_show_metier(self, director_client, macon, site):
        response = director_client.get(self.url() + f'?site={site.pk}')
        content = response.content.decode()
        assert 'Jean Mumbere — Maçon' in content
        assert '<option value="Maçon">Maçon</option>' in content
        info = response.context['form'].personnel_info()
        assert info[str(macon.pk)]['metier'] == 'Maçon'

    def test_role_prefilled_when_person_given(self, director_client, macon):
        response = director_client.get(self.url() + f'?personnel={macon.unique_id}')
        assert response.context['form'].initial['role'] == 'Maçon'

    def test_empty_role_takes_the_metier(self, director_client, macon, site):
        response = director_client.post(self.url(), assign_data(macon, site))
        assert response.status_code == 302
        assert SiteAssignment.objects.get(personnel=macon, site=site).role == 'Maçon'

    def test_typed_role_is_kept(self, director_client, macon, site):
        director_client.post(self.url(), assign_data(macon, site, "Chef d'équipe"))
        assert SiteAssignment.objects.get(personnel=macon, site=site).role == "Chef d'équipe"

    def test_role_required_without_metier(self, director_client, sans_metier, site):
        response = director_client.post(self.url(), assign_data(sans_metier, site))
        assert response.status_code == 200
        assert 'corps de métier' in response.content.decode()

    def test_metier_role_fills_the_persons_file(self, director_client, sans_metier, site):
        director_client.post(self.url(), assign_data(sans_metier, site, 'plombier'))
        sans_metier.refresh_from_db()
        assert sans_metier.trade == Trade.PLOMBIER

    def test_crew_list_shows_metier(self, director_client, macon, site):
        SiteAssignment.objects.create(personnel=macon, site=site, role="Chef d'équipe", start_date=date.today(), daily_rate=15)
        content = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id})).content.decode()
        assert 'Maçon' in content and "Chef d&#x27;équipe" in content


@pytest.mark.django_db
class TestQuickAddWithMetier:
    def test_name_with_trade(self, director_client):
        response = director_client.post(reverse('personnel:personnel_quick_create'),
                                        data=json.dumps({'name': 'Jean Bahati (Carreleur)'}), content_type='application/json')
        body = response.json()
        person = Personnel.objects.get(pk=body['id'])
        assert (person.first_name, person.last_name, person.trade) == ('Jean', 'Bahati', Trade.CARRELEUR)
        assert body['text'] == 'Jean Bahati — Carreleur'
        assert body['metier'] == 'Carreleur'

    def test_brackets_that_are_not_a_trade_stay_in_the_name(self, director_client):
        body = director_client.post(reverse('personnel:personnel_quick_create'),
                                    data=json.dumps({'name': 'Paul (Kivu)'}), content_type='application/json').json()
        person = Personnel.objects.get(pk=body['id'])
        assert person.trade == '' and person.last_name == '(Kivu)'
