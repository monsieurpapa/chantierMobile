"""
Tests for the two remaining "small" gaps flagged by the feature-vs-proposal
audit:

1. Personnel eligibility ("non éligible") was recorded but never enforced —
   SiteAssignment, PayrollListItem, Expense (main d'œuvre) and SalaryPayment
   now all reject an ineligible Personnel via model-level clean().
2. The expense report's filters were weaker than the caisse report's (no
   day/year presets, no phase filter) — both are now added.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.core.exceptions import ValidationError

from personnel.models import SiteAssignment
from finance.models import Expense, PayrollList, PayrollListItem, SalaryPayment, Caisse
from chantiermobile.constants import (
    PersonnelStatus, ExpenseStatus, ExpenseNature, CaisseType, CaisseTransactionType,
)


@pytest.fixture
def ineligible_personnel(personnel_factory):
    return personnel_factory(status=PersonnelStatus.NON_ELIGIBLE, monthly_salary=Decimal('300.00'))


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.fixture
def caisse(caisse_factory, user):
    c = caisse_factory()
    c.record(CaisseTransactionType.ENTREE, Decimal('5000.00'), user)
    return c


@pytest.mark.django_db
class TestPersonnelEligibilityEnforcement:
    def test_site_assignment_rejects_ineligible_personnel(self, site, ineligible_personnel):
        assignment = SiteAssignment(
            personnel=ineligible_personnel, site=site, role='Ouvrier',
            start_date=date.today(), daily_rate=Decimal('20.00'),
        )
        with pytest.raises(ValidationError):
            assignment.full_clean()

    def test_site_assignment_allows_active_personnel(self, site, personnel_factory):
        p = personnel_factory()  # defaults to ACTIF
        assignment = SiteAssignment(
            personnel=p, site=site, role='Ouvrier',
            start_date=date.today(), daily_rate=Decimal('20.00'),
        )
        assignment.full_clean()  # should not raise

    def test_site_assignment_view_rejects_ineligible_personnel(self, director_client, site, ineligible_personnel):
        url = reverse('personnel:assignment_create')
        response = director_client.post(url, {
            'personnel': ineligible_personnel.pk, 'site': site.pk, 'role': 'Ouvrier',
            'start_date': date.today().isoformat(), 'daily_rate': '20.00',
        })
        assert response.status_code == 200  # form re-rendered, not redirected
        assert not SiteAssignment.objects.filter(personnel=ineligible_personnel, site=site).exists()

    def test_payroll_list_item_rejects_ineligible_personnel(self, site, ineligible_personnel, user):
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        item = PayrollListItem(payroll_list=pl, personnel=ineligible_personnel, amount=Decimal('50.00'))
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_expense_rejects_ineligible_personnel_for_main_doeuvre(self, site, expense_category, user, ineligible_personnel):
        # .objects.create() bypasses clean()/full_clean() (Django never
        # validates automatically on save()), so this sets up the
        # "already-assigned, now ineligible" fixture state directly —
        # mirrors someone assigned while active, later marked non éligible.
        SiteAssignment.objects.create(
            personnel=ineligible_personnel, site=site, role='Ouvrier',
            start_date=date.today(), daily_rate=Decimal('20.00'),
        )
        expense = Expense(
            site=site, requester=user, category=expense_category,
            nature=ExpenseNature.MAIN_DOEUVRE, personnel=ineligible_personnel,
            amount=Decimal('50.00'), expense_date=date.today(),
            description='Paiement journalier', status=ExpenseStatus.PENDING,
        )
        with pytest.raises(ValidationError):
            expense.full_clean()

    def test_salary_payment_rejects_ineligible_personnel(self, ineligible_personnel, caisse):
        sp = SalaryPayment(personnel=ineligible_personnel, period='2026-09', amount=Decimal('300.00'), caisse=caisse)
        with pytest.raises(ValidationError):
            sp.full_clean()

    def test_salary_payment_create_view_rejects_ineligible_personnel(self, director_client, ineligible_personnel, caisse):
        # Not offered in the dropdown at all (queryset only filters by
        # monthly_salary though, not eligibility — status can still change
        # after the page loaded), so post directly to prove the model-level
        # guard is what actually blocks it, defense in depth.
        response = director_client.post(reverse('finance:salary_payment_create'), {
            'personnel': ineligible_personnel.pk, 'period': '2026-09', 'amount': '300.00',
            'caisse': caisse.pk, 'notes': '',
        })
        assert response.status_code == 200
        assert not SalaryPayment.objects.filter(personnel=ineligible_personnel).exists()


@pytest.fixture
def phase_a(site, phase_factory):
    return phase_factory(site, name='Fondations')


@pytest.fixture
def phase_b(site, phase_factory):
    return phase_factory(site, name='Toiture')


@pytest.mark.django_db
class TestExpenseReportFilterParity:
    def test_day_and_year_presets_available(self, director_client, site, expense_category, user):
        today = date.today()
        old = Expense.objects.create(
            site=site, requester=user, category=expense_category,
            amount=Decimal('10'), expense_date=today.replace(month=1, day=1) - timedelta(days=400),
            description='Vieille dépense', status=ExpenseStatus.PENDING,
        )
        recent = Expense.objects.create(
            site=site, requester=user, category=expense_category,
            amount=Decimal('20'), expense_date=today,
            description="Dépense d'aujourd'hui", status=ExpenseStatus.PENDING,
        )
        url = reverse('finance:expense_report')

        response = director_client.get(url, {'period': 'day'})
        ids = {e.pk for e in response.context['expenses']}
        assert recent.pk in ids
        assert old.pk not in ids

        response = director_client.get(url, {'period': 'year'})
        ids = {e.pk for e in response.context['expenses']}
        assert recent.pk in ids
        assert old.pk not in ids

    def test_phase_filter_narrows_results(self, director_client, site, expense_category, user, phase_a, phase_b):
        e_a = Expense.objects.create(
            site=site, phase=phase_a, requester=user, category=expense_category,
            amount=Decimal('10'), expense_date=date.today(),
            description='Ciment fondations', status=ExpenseStatus.PENDING,
        )
        e_b = Expense.objects.create(
            site=site, phase=phase_b, requester=user, category=expense_category,
            amount=Decimal('15'), expense_date=date.today(),
            description='Tôles toiture', status=ExpenseStatus.PENDING,
        )
        url = reverse('finance:expense_report')
        response = director_client.get(url, {'site': site.pk, 'phase': phase_a.pk})
        ids = {e.pk for e in response.context['expenses']}
        assert e_a.pk in ids
        assert e_b.pk not in ids

    def test_phases_listed_only_once_a_site_is_selected(self, director_client, site, phase_a):
        url = reverse('finance:expense_report')
        response = director_client.get(url)
        assert list(response.context['phases']) == []

        response = director_client.get(url, {'site': site.pk})
        assert phase_a in response.context['phases']
