"""The chantier's budget DQE for the état de besoin comparison (2026-10-20).

- The approved DQE is the budget when there is no accepted devis.
- An accepted devis's source DQE still wins when there is one.
- A sous-étape with no budget of its own is compared at its parent étape
  when the budget is priced per étape (e.g. the CCLK "synthèse par étape").
"""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from chantiermobile.constants import DevisStatus, DQEStatus, MaterialRequestStatus, MaterialVarianceStatus
from materials.models import MaterialRequestItem
from pricing.models import DQE, DQELine
from pricing.services import budget_dqe_for_site, compare_material_usage
from revenue.models import Devis
# Shared fixtures from the original comparison test module.
from tests.test_devis_material_comparison import ciment, material_item_ciment  # noqa: F401


def _dqe(cabinet, site, reference, status):
    return DQE.objects.create(cabinet=cabinet, site=site, reference=reference, title=reference, status=status)


@pytest.mark.django_db
class TestBudgetDqeForSite:
    def test_none_without_approved_dqe_or_accepted_devis(self, cabinet, site):
        _dqe(cabinet, site, 'DQE-DRAFT', DQEStatus.DRAFT)
        assert budget_dqe_for_site(site) is None

    def test_approved_dqe_is_the_budget(self, cabinet, site):
        approved = _dqe(cabinet, site, 'DQE-OK', DQEStatus.APPROUVE)
        assert budget_dqe_for_site(site) == approved

    def test_accepted_devis_source_dqe_wins(self, cabinet, site):
        _dqe(cabinet, site, 'DQE-OK', DQEStatus.APPROUVE)
        sold = _dqe(cabinet, site, 'DQE-SOLD', DQEStatus.DRAFT)
        Devis.objects.create(site=site, source_dqe=sold, devis_number='DEV-B1', client_name='Client',
                             issue_date=date.today(), status=DevisStatus.ACCEPTE)
        assert budget_dqe_for_site(site) == sold

    def test_other_chantier_dqe_ignored(self, cabinet, site, site_factory):
        other = site_factory(name='Autre chantier')
        _dqe(cabinet, other, 'DQE-OTHER', DQEStatus.APPROUVE)
        assert budget_dqe_for_site(site) is None


@pytest.mark.django_db
class TestComparisonAgainstApprovedDqe:
    def test_approved_dqe_budgets_the_comparison(self, cabinet, site, phase, ciment, material_item_ciment, material_request_factory):
        dqe = _dqe(cabinet, site, 'DQE-OK', DQEStatus.APPROUVE)
        DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('100'), unit_price=Decimal('8'))
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=phase, quantity=Decimal('110'))
        result = compare_material_usage(site, phase, ciment)
        assert result['baseline'] == Decimal('100')
        assert result['status'] == MaterialVarianceStatus.ORANGE

    def test_sub_etape_is_compared_at_its_parent_etape(self, cabinet, site, phase, phase_factory, ciment, material_item_ciment, material_request_factory):
        """Budget priced on the étape, request filed on one of its sous-étapes."""
        sub = phase_factory(site, name='Semelles', parent_phase=phase)
        dqe = _dqe(cabinet, site, 'DQE-SYN', DQEStatus.APPROUVE)
        DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('100'), unit_price=Decimal('8'))
        req = material_request_factory(status=MaterialRequestStatus.PENDING)
        MaterialRequestItem.objects.create(request=req, material=ciment, phase=sub, quantity=Decimal('130'))
        result = compare_material_usage(site, sub, ciment)
        assert result['phase'] == phase
        assert result['baseline'] == Decimal('100')
        assert result['cumulative_requested'] == Decimal('130')
        assert result['status'] == MaterialVarianceStatus.RED

    def test_sub_etape_with_its_own_budget_stays_at_sub_etape(self, cabinet, site, phase, phase_factory, ciment, material_item_ciment):
        sub = phase_factory(site, name='Semelles', parent_phase=phase)
        dqe = _dqe(cabinet, site, 'DQE-DET', DQEStatus.APPROUVE)
        DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('100'), unit_price=Decimal('8'))
        DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=sub, quantity=Decimal('40'), unit_price=Decimal('8'))
        result = compare_material_usage(site, sub, ciment)
        assert result['phase'] == sub
        assert result['baseline'] == Decimal('40')

    def test_compliance_report_uses_approved_dqe(self, director_client, cabinet, site, phase, material_item_ciment):
        dqe = _dqe(cabinet, site, 'DQE-RPT', DQEStatus.APPROUVE)
        DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('100'), unit_price=Decimal('8'))
        response = director_client.get(reverse('pricing:devis_compliance_report', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert response.context['budget_dqe'] == dqe
        assert b'DQE-RPT' in response.content
        assert len(response.context['rows']) >= 1
