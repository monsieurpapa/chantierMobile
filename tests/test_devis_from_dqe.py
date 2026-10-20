""""Créer un devis depuis ce DQE" (2026-10-20)."""
from decimal import Decimal

import pytest
from django.urls import reverse

from chantiermobile.constants import DevisStatus, DQEStatus
from pricing.models import DQE, DQELine
from revenue.models import Devis
from revenue.services import create_devis_from_dqe, next_devis_number
from tests.test_devis_material_comparison import ciment, material_item_ciment  # noqa: F401


@pytest.fixture
def dqe_with_lines(db, cabinet, site, phase, material_item_ciment):
    dqe = DQE.objects.create(cabinet=cabinet, site=site, reference='DQE-SRC', title='Source', status=DQEStatus.APPROUVE)
    DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('180.10'), unit_price=Decimal('12.00'), order=0)
    DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=None, designation='Transport', quantity=Decimal('1'), unit_price=Decimal('20.00'), order=1)
    return dqe


@pytest.mark.django_db
class TestCreateDevisFromDqe:
    def test_copies_lines_with_margin_and_links_dqe(self, dqe_with_lines, phase):
        devis = create_devis_from_dqe(dqe_with_lines, client_name='CCLK', margin_pct=Decimal('10'))
        assert devis.status == DevisStatus.BROUILLON
        assert devis.source_dqe == dqe_with_lines
        assert devis.site == dqe_with_lines.site
        lines = list(devis.lines.order_by('order'))
        assert len(lines) == 2
        assert lines[0].phase == phase
        assert lines[0].designation == 'Ciment'
        assert lines[0].unit == 'sac'
        assert lines[0].quantity == Decimal('180.10')
        assert lines[0].unit_price_ht == Decimal('13.20')
        assert lines[1].designation == 'Transport'
        assert lines[1].unit_price_ht == Decimal('22.00')

    def test_zero_margin_keeps_prices(self, dqe_with_lines):
        devis = create_devis_from_dqe(dqe_with_lines, client_name='CCLK')
        assert sum(l.total_ht for l in devis.lines.all()) == dqe_with_lines.total_amount

    def test_numbers_are_unique_and_sequential(self, dqe_with_lines):
        first = create_devis_from_dqe(dqe_with_lines, client_name='A')
        second = create_devis_from_dqe(dqe_with_lines, client_name='B')
        assert first.devis_number != second.devis_number
        assert first.devis_number.startswith('DEV-') and second.devis_number.startswith('DEV-')

    def test_dqe_without_chantier_is_refused(self, cabinet):
        dqe = DQE.objects.create(cabinet=cabinet, site=None, reference='DQE-NOSITE', title='x')
        with pytest.raises(ValueError):
            create_devis_from_dqe(dqe, client_name='X')


@pytest.mark.django_db
class TestDevisFromDqeView:
    def test_director_creates_devis(self, director_client, dqe_with_lines):
        response = director_client.post(reverse('revenue:devis_create_from_dqe', args=[dqe_with_lines.pk]),
                                         {'client_name': 'CCLK', 'margin_pct': '15', 'validity_days': '30'})
        devis = Devis.objects.get(source_dqe=dqe_with_lines)
        assert response.status_code == 302
        assert response.url == reverse('revenue:devis_detail', args=[devis.pk])
        assert devis.lines.count() == 2

    def test_engineer_cannot(self, engineer_client, dqe_with_lines):
        engineer_client.post(reverse('revenue:devis_create_from_dqe', args=[dqe_with_lines.pk]), {'client_name': 'CCLK'})
        assert not Devis.objects.filter(source_dqe=dqe_with_lines).exists()

    def test_client_is_required(self, director_client, dqe_with_lines):
        director_client.post(reverse('revenue:devis_create_from_dqe', args=[dqe_with_lines.pk]), {'client_name': ' '})
        assert not Devis.objects.filter(source_dqe=dqe_with_lines).exists()

    def test_dqe_page_shows_the_form(self, director_client, dqe_with_lines):
        response = director_client.get(reverse('pricing:dqe_detail', args=[dqe_with_lines.pk]))
        assert response.status_code == 200
        assert reverse('revenue:devis_create_from_dqe', args=[dqe_with_lines.pk]).encode() in response.content
