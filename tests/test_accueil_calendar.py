"""Tests for the 2026-10-19 "Accueil et tableau de bord" feature
(meeting-note backlog): the home dashboard now also shows a "Chantiers"
list and a clickable month calendar, each day linking to a day-detail
page listing that day's caisse movements and planning tasks starting
that day. The client's own note left open whether the calendar should
cover only caisse movements or also planning tasks — the default taken
here shows both, with caisse figures gated the same way as the rest of
the dashboard's financial widgets (can_view_financials).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from finance.models import Caisse, CaisseTransaction
from chantiermobile.constants import CaisseTransactionType


@pytest.fixture
def caisse(db, cabinet):
    return Caisse.objects.create(cabinet=cabinet, name='Caisse Principale')


@pytest.mark.django_db
class TestHomeDashboardChantiersList:
    def test_sites_listed_by_name(self, director_client, site):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        assert site.name.encode() in response.content
        assert response.context['calendar_sites'][0]['name'] == site.name


@pytest.mark.django_db
class TestHomeDashboardCalendar:
    def test_calendar_shows_current_month_by_default(self, director_client):
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        assert response.context['calendar_current_month'] == date.today().strftime('%Y-%m')
        assert len(response.context['calendar_weeks']) >= 4

    def test_caisse_net_shown_for_director(self, director_client, site, caisse, user):
        today = date.today()
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('100.00'),
            date=today, site=site, recorded_by=user,
        )
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('30.00'),
            date=today, site=site, recorded_by=user,
        )
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        flat_days = [d for week in response.context['calendar_weeks'] for d in week]
        today_cell = next(d for d in flat_days if d['date'] == today)
        assert today_cell['caisse_net'] == Decimal('70.00')
        assert b'+70' in response.content

    def test_caisse_net_hidden_for_a_non_financial_role(self, engineer_client, site, caisse, user):
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('100.00'),
            date=date.today(), site=site, recorded_by=user,
        )
        response = engineer_client.get(reverse('home'))
        assert response.status_code == 200
        assert response.context['calendar_show_financials'] is False
        assert b'+100' not in response.content

    def test_task_count_shown_for_a_day_with_a_phase_starting(self, director_client, site, phase_factory):
        phase_factory(site, name='Fondation', start_date=date.today())
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        flat_days = [d for week in response.context['calendar_weeks'] for d in week]
        today_cell = next(d for d in flat_days if d['date'] == date.today())
        assert today_cell['task_count'] == 1

    def test_month_navigation_via_query_param(self, director_client):
        next_month_first = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)
        response = director_client.get(reverse('home'), {'month': next_month_first.strftime('%Y-%m')})
        assert response.status_code == 200
        assert response.context['calendar_current_month'] == next_month_first.strftime('%Y-%m')


@pytest.mark.django_db
class TestDayDetailView:
    def test_shows_caisse_movements_and_tasks_for_that_day(self, director_client, site, caisse, user, phase_factory):
        today = date.today()
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('250.00'),
            date=today, site=site, recorded_by=user, description='Avance client',
        )
        phase_factory(site, name='Coffrage', start_date=today)
        response = director_client.get(reverse('home_day_detail', kwargs={'day': today.isoformat()}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Avance client' in content
        assert 'Coffrage' in content

    def test_caisse_section_hidden_for_a_non_financial_role(self, engineer_client, site, caisse, user):
        today = date.today()
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('250.00'),
            date=today, site=site, recorded_by=user, description='Avance confidentielle',
        )
        response = engineer_client.get(reverse('home_day_detail', kwargs={'day': today.isoformat()}))
        assert response.status_code == 200
        assert 'Avance confidentielle' not in response.content.decode()

    def test_invalid_date_returns_404(self, director_client):
        response = director_client.get(reverse('home_day_detail', kwargs={'day': 'not-a-date'}))
        assert response.status_code == 404
