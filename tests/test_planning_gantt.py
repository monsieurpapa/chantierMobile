"""Tests for the 2026-10-19 "Planification des travaux" / Gantt view
(meeting-note backlog): a simple week-grid Gantt built directly from the
existing ProjectPhase étape/sous-étape structure — no new model or
fields. A row is a sous-étape ("tâche") when the top-level phase has
any, otherwise the top-level phase itself; a task's "budget matériaux"
is the sum of the devis global/DQE lines (DQELine) already pointing at
that same phase, not a duplicated amount.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from pricing.models import PriceLibraryItem, DQE, DQELine
from chantiermobile.constants import PriceItemType, DQEStatus


@pytest.fixture
def sub_phase_factory(db, phase_factory):
    def create_sub_phase(site, parent, **kwargs):
        defaults = {'name': 'Sous-étape'}
        defaults.update(kwargs)
        return phase_factory(site, parent_phase=parent, **defaults)
    return create_sub_phase


@pytest.fixture
def work_item(db, cabinet):
    return PriceLibraryItem.objects.create(
        cabinet=cabinet, code='OUV-TEST', designation='Ouvrage test',
        item_type=PriceItemType.MATERIAL, unit='u', unit_price=Decimal('10.00'),
    )


@pytest.fixture
def dqe(db, cabinet, site):
    return DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-GANTT-001', title='Devis global test', status=DQEStatus.DRAFT)


@pytest.mark.django_db
class TestSiteGanttView:
    def test_empty_site_shows_no_phases_message(self, director_client, site):
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert 'Aucune étape définie'.encode() in response.content

    def test_top_level_phase_without_subphases_is_its_own_task_row(self, director_client, site, phase_factory):
        phase_factory(site, name='F - Couverture', start_date=date(2026, 1, 5))
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'F - Couverture' in content
        assert content.count('F - Couverture') == 2  # phase header row + task row

    def test_subphases_appear_as_task_rows_under_their_phase(self, director_client, site, phase_factory, sub_phase_factory):
        phase = phase_factory(site, name='B - Fondation', start_date=date(2026, 1, 5))
        sub_phase_factory(site, phase, name='Implantation et travaux préliminaires', start_date=date(2026, 1, 5), end_date=date(2026, 1, 11))
        sub_phase_factory(site, phase, name='Béton de propreté', start_date=date(2026, 1, 12), end_date=date(2026, 1, 18))
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Implantation et travaux préliminaires' in content
        assert 'Béton de propreté' in content
        # S1/S2 week headers should be present for a 2-week span.
        assert '>S1<' in content.replace(' ', '')

    def test_task_budget_is_sum_of_linked_dqe_lines_not_duplicated(
        self, director_client, site, phase_factory, sub_phase_factory, dqe, work_item,
    ):
        phase = phase_factory(site, name='B - Fondation', start_date=date(2026, 1, 5))
        task = sub_phase_factory(site, phase, name='Semelles', start_date=date(2026, 1, 5), end_date=date(2026, 1, 11))
        DQELine.objects.create(dqe=dqe, price_item=work_item, phase=task, quantity=Decimal('10'), unit_price=Decimal('60.00'))
        DQELine.objects.create(dqe=dqe, price_item=work_item, phase=task, quantity=Decimal('1'), unit_price=Decimal('5.54'))
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert response.context['grand_total_budget'] == Decimal('605.54')
        content = response.content.decode()
        # The site's locale (fr) renders floatformat with a comma decimal
        # separator, same convention as the rest of the app's money
        # displays (see CURRENCY_SYMBOL usage elsewhere) — assert on the
        # context value above for the exact figure, and only check here
        # that the digits made it into the page at all.
        assert '605' in content

    def test_task_without_start_date_shows_unplanned_placeholder(self, director_client, site, phase_factory, sub_phase_factory):
        phase = phase_factory(site, name='C - RDC', start_date=date(2026, 1, 5))
        sub_phase_factory(site, phase, name='Non daté', start_date=None)
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}))
        assert response.status_code == 200
        assert 'Non planifié'.encode() in response.content

    def test_grid_range_falls_back_to_default_weeks_when_no_dates_at_all(self, director_client, site_factory, phase_factory):
        undated_site = site_factory(name='Chantier sans dates', start_date=None, expected_end_date=None)
        phase_factory(undated_site, name='A - Installation', start_date=None)
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': undated_site.unique_id}))
        assert response.status_code == 200
        assert response.context['total_weeks'] == 16

    def test_grid_is_capped_at_max_weeks_for_a_very_long_site(self, director_client, site_factory):
        long_site = site_factory(
            name='Chantier long', start_date=date(2026, 1, 1),
            expected_end_date=date(2026, 1, 1) + timedelta(weeks=200),
        )
        response = director_client.get(reverse('projects:site_gantt', kwargs={'unique_id': long_site.unique_id}))
        assert response.status_code == 200
        assert response.context['total_weeks'] == 52
