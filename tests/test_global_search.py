"""
Tests for item 15 (second half) of the Directors/Engineers audit: the
navbar's search box (templates/includes/navbar-top.html) was a Falcon
theme placeholder with no data source — typing into it did nothing.
core.search.global_search(), surfaced at /recherche/, now searches
cabinet-scoped Sites, Personnel, Contracts and Invoices by name/number.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus


@pytest.mark.django_db
class TestGlobalSearch:
    def test_empty_query_returns_no_results_and_no_error(self, director_client):
        response = director_client.get(reverse('global_search'))
        assert response.status_code == 200
        assert response.context['results'] == []

    def test_short_query_returns_no_results(self, director_client, site):
        response = director_client.get(reverse('global_search'), {'q': 'T'})
        assert response.status_code == 200
        assert response.context['results'] == []

    def test_finds_site_by_name(self, director_client, site_factory):
        site = site_factory(name='Résidence Kinshasa Nord')
        response = director_client.get(reverse('global_search'), {'q': 'Kinshasa'})
        titles = [r['title'] for r in response.context['results']]
        assert 'Résidence Kinshasa Nord' in titles

    def test_finds_personnel_by_name(self, director_client, personnel_factory):
        personnel_factory(first_name='Aimé', last_name='Mbala')
        response = director_client.get(reverse('global_search'), {'q': 'Mbala'})
        titles = [r['title'] for r in response.context['results']]
        assert any('Mbala' in t for t in titles)

    def test_finds_contract_by_client_name(self, director_client, contract_factory):
        contract_factory(client_name='Société Générale du Bâtiment')
        response = director_client.get(reverse('global_search'), {'q': 'Générale'})
        titles = [r['title'] for r in response.context['results']]
        assert any('Générale' in t for t in titles)

    def test_finds_invoice_by_number(self, director_client, invoice_factory):
        invoice_factory(invoice_number='FAC-2026-0042')
        response = director_client.get(reverse('global_search'), {'q': 'FAC-2026-0042'})
        titles = [r['title'] for r in response.context['results']]
        assert 'FAC-2026-0042' in titles

    def test_results_scoped_to_own_cabinet(self, director_client, site_factory):
        other_cabinet = Cabinet.objects.create(name='Cabinet Voisin')
        other_site = site_factory(cabinet=other_cabinet, name='Chantier Voisin Unique')
        response = director_client.get(reverse('global_search'), {'q': 'Voisin Unique'})
        titles = [r['title'] for r in response.context['results']]
        assert 'Chantier Voisin Unique' not in titles

    def test_worker_can_search_their_own_cabinet(self, client, cabinet, django_user_model, site_factory):
        site_factory(name='Chantier Ouvrier Visible')
        worker = django_user_model.objects.create_user(username='worker_search', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        client.login(username='worker_search', password='testpass123')

        response = client.get(reverse('global_search'), {'q': 'Ouvrier Visible'})
        titles = [r['title'] for r in response.context['results']]
        assert 'Chantier Ouvrier Visible' in titles
