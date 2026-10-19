"""Tests for the 2026-10-19 UI/UX pass: the finance app's Caisse/Listes-de-
paie/Avenants screens render through PageHeaderMixin (templates/includes/
page_header.html), which has always supported a breadcrumb trail
(`breadcrumb_items`) — the same convention already used across personnel,
projects, pricing, procurement, revenue and accounts — but it was never
wired up anywhere in finance/views.py. This fills that gap for every
PageHeaderMixin view in the module except the top-of-section list views
(CaisseListView, PayrollListListView, AvenantListView, ExpenseListView,
BudgetListView), which — matching the existing convention elsewhere, e.g.
PersonnelListView/SiteListView — don't carry a breadcrumb of their own
since nothing in-app sits above them.

Only a representative sample is checked here (one per section), rather
than all ~18 new get_breadcrumb_items() overrides, since they all share
the same rendering path (page_header.html) and the same
PageHeaderMixin.get_context_data() plumbing already covered by every
other view in the app.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from finance.models import Caisse, CaisseTransaction, PayrollList
from chantiermobile.constants import CaisseTransactionType


@pytest.fixture
def caisse(db, cabinet, site):
    return Caisse.objects.create(cabinet=cabinet, name='Caisse Chantier', site=site)


@pytest.mark.django_db
class TestCaisseBreadcrumbs:
    def test_caisse_detail_breadcrumb(self, director_client, caisse):
        response = director_client.get(reverse('finance:caisse_detail', kwargs={'pk': caisse.pk}))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items == [
            {'title': 'Caisses', 'url': reverse('finance:caisse_list')},
            {'title': caisse.name, 'url': None},
        ]
        content = response.content.decode()
        assert 'breadcrumb' in content
        assert caisse.name in content

    def test_caisse_transaction_create_breadcrumb(self, director_client, caisse):
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert [i['title'] for i in items] == ['Caisses', caisse.name, 'Nouveau mouvement']
        assert items[-1]['url'] is None

    def test_caisse_transaction_detail_breadcrumb(self, director_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('10.00'),
            date='2026-10-19', recorded_by=user,
        )
        response = director_client.get(reverse('finance:caisse_transaction_detail', kwargs={'pk': tx.pk}))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items[0] == {'title': 'Caisses', 'url': reverse('finance:caisse_list')}
        assert items[1]['title'] == caisse.name
        assert items[-1]['url'] is None

    def test_dg_payroll_overview_breadcrumb(self, director_client):
        response = director_client.get(reverse('finance:dg_payroll_overview'))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items[-1] == {'title': 'Vue DG — paiements personnel', 'url': None}

    def test_top_level_caisse_list_has_no_breadcrumb(self, director_client):
        """Matches the established convention (PersonnelListView,
        SiteListView, ...): a section's own top list carries no
        breadcrumb since nothing in-app sits above it."""
        response = director_client.get(reverse('finance:caisse_list'))
        assert response.status_code == 200
        assert response.context['breadcrumb_items'] == []


@pytest.mark.django_db
class TestPayrollAndAvenantBreadcrumbs:
    def test_payroll_detail_breadcrumb(self, director_client, site, user):
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        response = director_client.get(reverse('finance:payroll_detail', kwargs={'pk': pl.pk}))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items[0] == {'title': 'Listes de paie', 'url': reverse('finance:payroll_list')}
        assert items[-1]['url'] is None

    def test_salary_payment_list_tab_breadcrumb(self, director_client):
        response = director_client.get(reverse('finance:salary_payment_list'))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items == [
            {'title': 'Listes de paie', 'url': reverse('finance:payroll_list')},
            {'title': 'Ingénieurs & Staff', 'url': None},
        ]

    def test_avenant_create_breadcrumb(self, director_client):
        response = director_client.get(reverse('finance:avenant_create'))
        assert response.status_code == 200
        items = response.context['breadcrumb_items']
        assert items == [
            {'title': 'Avenants', 'url': reverse('finance:avenant_list')},
            {'title': 'Nouvel avenant', 'url': None},
        ]
