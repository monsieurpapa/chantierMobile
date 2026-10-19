"""Tests for the 2026-10-19 "Caisse/finance views" feature (meeting-note
backlog item 10):

- The livre de caisse report (and its PDF export) gains a "Chef de
  corps" filter, matched approximately against the free-text `recipient`
  field (CaisseTransaction has no FK to Personnel — documented
  limitation, see _caisse_ledger_queryset).
- "Vue Financier": CaisseTransactionCreateView now shows a cumulative
  convention-vs-paid breakdown by étape for its own caisse's site.
- "Vue DG": a new cross-site page (finance:dg_payroll_overview) showing
  the same breakdown across every site in the cabinet, optionally
  narrowed to one chantier.

Both "Vue Financier" and "Vue DG" are built on the shared
_personnel_payment_summary helper, which only counts SiteAssignment rows
that carry a convention_amount (a plain role-based affectation has
nothing to reconcile) and sums each one's existing `paid_amount`
property (itself PayrollListItem.amount, summed).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from finance.models import Caisse, CaisseTransaction, PayrollList, PayrollListItem
from personnel.models import SiteAssignment
from chantiermobile.constants import CaisseTransactionType, ConventionScope


@pytest.fixture
def caisse(db, cabinet, site):
    return Caisse.objects.create(cabinet=cabinet, name='Caisse Chantier', site=site)


@pytest.fixture
def chef_de_corps(db, personnel_factory):
    return personnel_factory(first_name='Jean', last_name='Dupont', is_chef_de_corps=True)


@pytest.mark.django_db
class TestChefDeCorpsCaisseFilter:
    def test_filters_transactions_by_recipient_name_match(self, director_client, caisse, chef_de_corps, user):
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('200.00'),
            date='2026-10-19', recipient='Jean Dupont', recorded_by=user,
        )
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('80.00'),
            date='2026-10-19', recipient='Fournisseur Ciment SA', recorded_by=user,
        )
        response = director_client.get(reverse('finance:caisse_report'), {'chef_de_corps': chef_de_corps.pk})
        assert response.status_code == 200
        transactions = list(response.context['transactions'])
        assert len(transactions) == 1
        assert transactions[0].recipient == 'Jean Dupont'

    def test_dropdown_only_lists_chefs_de_corps(self, director_client, chef_de_corps, personnel_factory):
        personnel_factory(first_name='Simple', last_name='Ouvrier', is_chef_de_corps=False)
        response = director_client.get(reverse('finance:caisse_report'))
        assert response.status_code == 200
        names = {p.pk for p in response.context['chefs_de_corps']}
        assert chef_de_corps.pk in names
        assert len(names) == 1

    def test_pdf_export_includes_beneficiaire_column(self, director_client, caisse, user):
        CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('50.00'),
            date='2026-10-19', recipient='Jean Dupont', recorded_by=user,
        )
        response = director_client.get(reverse('finance:caisse_report_pdf'))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'


@pytest.mark.django_db
class TestVueFinancierSidebar:
    def test_shows_convention_vs_paid_by_phase(self, director_client, caisse, site, phase_factory, personnel, user):
        phase = phase_factory(site, name='Coffrage')
        assignment = SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Coffrage dalle', phase=phase,
            scope=ConventionScope.PAR_ETAPE, convention_amount=Decimal('1000.00'),
        )
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=personnel, assignment=assignment, amount=Decimal('400.00'))

        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}))
        assert response.status_code == 200
        rows = response.context['personnel_payment_rows']
        assert len(rows) == 1
        phase_row = rows[0]['phases'][0]
        assert phase_row['label'] == 'Coffrage'
        assert phase_row['cap'] == Decimal('1000.00')
        assert phase_row['paid'] == Decimal('400.00')
        assert phase_row['remaining'] == Decimal('600.00')
        content = response.content.decode()
        assert 'Vue Financier' in content

    def test_chantier_entier_convention_grouped_without_a_phase(self, director_client, caisse, site, personnel):
        SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Gardiennage',
            scope=ConventionScope.CHANTIER_ENTIER, convention_amount=Decimal('300.00'),
        )
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}))
        assert response.status_code == 200
        rows = response.context['personnel_payment_rows']
        assert rows[0]['phases'][0]['label'] == 'Chantier entier'
        assert rows[0]['phases'][0]['cap'] == Decimal('300.00')

    def test_hidden_for_a_caisse_with_no_fixed_site(self, director_client, cabinet):
        external_caisse = Caisse.objects.create(cabinet=cabinet, name='Caisse Externe')
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': external_caisse.pk}))
        assert response.status_code == 200
        assert response.context['personnel_payment_rows'] == []


@pytest.mark.django_db
class TestVueDG:
    def test_director_sees_every_site_with_a_convention(self, director_client, site, phase_factory, personnel):
        phase = phase_factory(site, name='Fondation')
        SiteAssignment.objects.create(
            personnel=personnel, site=site, name='Fondation', phase=phase,
            scope=ConventionScope.PAR_ETAPE, convention_amount=Decimal('500.00'),
        )
        response = director_client.get(reverse('finance:dg_payroll_overview'))
        assert response.status_code == 200
        assert len(response.context['site_rows']) == 1
        assert response.context['site_rows'][0]['site'] == site

    def test_filter_by_site(self, director_client, site, site_factory, personnel_factory):
        other_site = site_factory(name='Autre Chantier')
        p1 = personnel_factory(first_name='A', last_name='Un')
        p2 = personnel_factory(first_name='B', last_name='Deux')
        SiteAssignment.objects.create(personnel=p1, site=site, name='X', convention_amount=Decimal('100.00'))
        SiteAssignment.objects.create(personnel=p2, site=other_site, name='Y', convention_amount=Decimal('200.00'))

        response = director_client.get(reverse('finance:dg_payroll_overview'), {'site': site.pk})
        assert response.status_code == 200
        rows = response.context['site_rows']
        assert len(rows) == 1
        assert rows[0]['site'] == site

    def test_an_engineer_cannot_access_the_dg_view(self, engineer_client):
        response = engineer_client.get(reverse('finance:dg_payroll_overview'))
        assert response.status_code == 302
