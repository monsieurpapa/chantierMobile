"""Regression tests for the production QA pass of 2026-10-20 — see
docs/history/qa-report-production-2026-10-20.md (finding numbers below)."""
from decimal import Decimal

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestFinding4NoDollarNone:
    """A worker without a default daily rate showed "$None"."""

    def test_personnel_list(self, director_client, personnel_factory):
        personnel_factory(first_name='Sans', last_name='Tarif', default_daily_rate=None)
        response = director_client.get(reverse('personnel:personnel_list'))
        assert response.status_code == 200
        assert b'$None' not in response.content

    def test_personnel_detail(self, director_client, personnel_factory):
        person = personnel_factory(first_name='Sans', last_name='Tarif', default_daily_rate=None)
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}))
        assert response.status_code == 200
        assert b'$None' not in response.content

    def test_rate_is_formatted_when_set(self, director_client, personnel_factory):
        person = personnel_factory(first_name='Avec', last_name='Tarif', default_daily_rate=Decimal('1500'))
        response = director_client.get(reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}))
        assert '1\xa0500,00'.encode() in response.content or '1 500,00'.encode() in response.content


@pytest.mark.django_db
class TestFinding5NoDeadButtons:
    def test_site_list_has_no_dead_filter_export_buttons(self, director_client, site):
        response = director_client.get(reverse('projects:site_list'))
        assert response.status_code == 200
        assert b'>Filter</button>' not in response.content
        assert b'>Export</button>' not in response.content


class TestFinding6MoneyFilter:
    def test_negative_sign_goes_before_the_symbol(self):
        from core.templatetags.money import money
        assert money(Decimal('-200')) in ('-$200,00', '-$200.00')

    def test_thousands_are_grouped(self):
        from django.utils import translation
        from core.templatetags.money import money
        with translation.override('fr'):
            assert money(Decimal('30000')).replace('\xa0', ' ').replace(' ', ' ') == '$30 000,00'

    def test_empty_value(self):
        from core.templatetags.money import money
        assert money(None) == '—'


@pytest.mark.django_db
class TestFinding6GroupedAmounts:
    def test_budget_list_groups_thousands(self, director_client, site):
        from datetime import date, timedelta
        from finance.models import Budget
        Budget.objects.create(site=site, total_amount=Decimal('30000'), start_date=date.today(),
                              end_date=date.today() + timedelta(days=365))
        response = director_client.get(reverse('finance:budget_list'), HTTP_ACCEPT_LANGUAGE='fr')
        content = response.content.decode().replace('\xa0', ' ').replace(' ', ' ')
        assert response.status_code == 200
        assert '30000,00' not in content
        assert '30 000,00' in content


@pytest.mark.django_db
class TestFinding7FrenchTitles:
    @pytest.mark.parametrize('url_name,title', [
        ('finance:expense_list', 'Dépenses'),
        ('materials:request_list', 'Demandes de matériaux'),
        ('materials:material_list', 'Catalogue des matériaux'),
        ('revenue:contract_list', 'Contrats'),
        ('revenue:payment_list', 'Paiements'),
    ])
    def test_page_title_is_french(self, director_client, url_name, title):
        response = director_client.get(reverse(url_name), HTTP_ACCEPT_LANGUAGE='fr')
        assert response.status_code == 200
        assert f'<title>{title} - ChantierMobile'.encode() in response.content
