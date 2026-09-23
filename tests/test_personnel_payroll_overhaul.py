"""
Tests for the Personnel / Liste de paie overhaul.

Two strictly separate payroll tracks, each its own tab under "Liste de
paie", both ultimately booked to a caisse under their own category:

1. "Main d'œuvre" tab (PayrollList/PayrollListItem) — Ouvriers only, paid
   progressively per chantier, capped by SiteAssignment.convention_amount
   when one is set. PayrollListItem.clean() rejects Ingénieur/Staff
   personnel outright.
2. "Ingénieurs & Staff" tab (SalaryPayment) — Ingénieur/Staff personnel
   only, paid a fixed monthly salary not tied to a chantier.
   SalaryPayment.clean() rejects Ouvrier personnel outright.
3. SiteAssignment.convention_amount tracks a per-task convention cap
   (a worker can have several active conventions on the same chantier —
   see MO.xlsx from the demo, e.g. "Peinture alain" vs "Etancheité alain").
4. PayrollList.disburse() books to "Main d'œuvre Ouvriers"; the split by
   category is kept as a safety net for any pre-existing legacy item, but
   new items can no longer be anything but Ouvrier (see get_rows() below).
5. The bulk allocation screen (PayrollListAllocateView) lets the Archi
   allocate a Montant per SiteAssignment in one page — Ouvrier rows only —
   capped by the convention's remaining balance.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import (
    Caisse, CaisseTransaction, CaisseTransactionCategory, PayrollList, PayrollListItem, SalaryPayment,
    PAYROLL_OUVRIER_CATEGORY_NAME, PAYROLL_INGENIEUR_CATEGORY_NAME,
)
from personnel.models import SiteAssignment
from chantiermobile.constants import (
    CaisseTransactionType, CaisseType, PayrollListStatus, PersonnelPayrollType,
)


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


@pytest.fixture
def assignment_factory(db, site):
    def create_assignment(**kwargs):
        defaults = {
            'site': site, 'role': 'Ouvrier', 'start_date': date.today(),
            'daily_rate': Decimal('20.00'),
        }
        defaults.update(kwargs)
        return SiteAssignment.objects.create(**defaults)
    return create_assignment


@pytest.mark.django_db
class TestPayrollTypeDefaultAndDisplay:
    def test_default_payroll_type_is_ouvrier(self, personnel_factory):
        p = personnel_factory()
        assert p.payroll_type == PersonnelPayrollType.OUVRIER

    def test_can_set_ingenieur(self, personnel_factory):
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR)
        assert p.payroll_type == PersonnelPayrollType.INGENIEUR


@pytest.mark.django_db
class TestConventionCap:
    def test_multiple_conventions_per_worker_per_site(self, personnel_factory, assignment_factory):
        """Mirrors MO.xlsx: the same worker can have two distinct
        task-conventions active on the same chantier at once."""
        p = personnel_factory()
        a1 = assignment_factory(personnel=p, role='Peinture', convention_amount=Decimal('200.00'))
        a2 = assignment_factory(personnel=p, role='Etancheité', convention_amount=Decimal('150.00'))
        assert a1.remaining_convention == Decimal('200.00')
        assert a2.remaining_convention == Decimal('150.00')

    def test_uncapped_assignment_has_no_remaining(self, personnel_factory, assignment_factory):
        p = personnel_factory()
        a = assignment_factory(personnel=p)  # no convention_amount
        assert a.remaining_convention is None

    def test_item_rejected_when_amount_exceeds_remaining(self, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        a = assignment_factory(personnel=p, convention_amount=Decimal('100.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('150.00'))
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_item_accepted_within_remaining(self, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        a = assignment_factory(personnel=p, convention_amount=Decimal('100.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('60.00'))
        item.full_clean()  # should not raise
        item.save()
        assert a.remaining_convention == Decimal('40.00')

    def test_second_payment_capped_by_amount_already_paid(self, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        a = assignment_factory(personnel=p, convention_amount=Decimal('100.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('60.00'))
        second = PayrollListItem(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('50.00'))
        with pytest.raises(ValidationError):
            second.full_clean()

    def test_editing_own_item_does_not_double_count(self, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        a = assignment_factory(personnel=p, convention_amount=Decimal('100.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem.objects.create(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('60.00'))
        item.amount = Decimal('90.00')  # still <= 100, editing shouldn't double-count the prior 60
        item.full_clean()  # should not raise

    def test_ingenieur_rejected_from_payroll_list_item(self, site, personnel_factory, assignment_factory):
        """Ingénieur/Staff personnel belong on SalaryPayment (Ingénieurs &
        Staff tab), never on a chantier's Liste de paie."""
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR)
        a = assignment_factory(personnel=p, convention_amount=Decimal('50.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('10.00'))
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_assignment_must_belong_to_the_paid_personnel(self, site, personnel_factory, assignment_factory):
        p1 = personnel_factory(first_name='A')
        p2 = personnel_factory(first_name='B')
        a = assignment_factory(personnel=p1, convention_amount=Decimal('100.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem(payroll_list=pl, personnel=p2, assignment=a, amount=Decimal('10.00'))
        with pytest.raises(ValidationError):
            item.full_clean()


@pytest.mark.django_db
class TestDisburseSplitsByCategory:
    """disburse() itself still splits by category unconditionally — this is
    what keeps any pre-existing Ingénieur item (from before PayrollListItem.
    clean() started rejecting them) disbursing safely under its own
    category. These tests use .objects.create(), which bypasses clean(),
    to simulate that legacy/edge-case data on purpose."""
    def test_only_ouvrier_items_creates_one_transaction(self, site, personnel_factory, caisse, user):
        p = personnel_factory(payroll_type=PersonnelPayrollType.OUVRIER)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p, amount=Decimal('80.00'))
        pl.submit(user)
        pl.disburse(user, caisse)
        txs = CaisseTransaction.objects.filter(caisse=caisse, transaction_type=CaisseTransactionType.SORTIE)
        assert txs.count() == 1
        assert txs.first().category.name == PAYROLL_OUVRIER_CATEGORY_NAME
        assert txs.first().amount == Decimal('80.00')

    def test_only_ingenieur_items_creates_one_transaction(self, site, personnel_factory, caisse, user):
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p, amount=Decimal('120.00'))
        pl.submit(user)
        pl.disburse(user, caisse)
        txs = CaisseTransaction.objects.filter(caisse=caisse, transaction_type=CaisseTransactionType.SORTIE)
        assert txs.count() == 1
        assert txs.first().category.name == PAYROLL_INGENIEUR_CATEGORY_NAME

    def test_mixed_items_creates_two_categorized_transactions(self, site, personnel_factory, caisse, user):
        ouvrier = personnel_factory(first_name='O', payroll_type=PersonnelPayrollType.OUVRIER)
        ingenieur = personnel_factory(first_name='I', payroll_type=PersonnelPayrollType.INGENIEUR)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=ouvrier, amount=Decimal('80.00'))
        PayrollListItem.objects.create(payroll_list=pl, personnel=ingenieur, amount=Decimal('120.00'))
        pl.submit(user)
        pl.disburse(user, caisse)
        txs = CaisseTransaction.objects.filter(caisse=caisse, transaction_type=CaisseTransactionType.SORTIE)
        assert txs.count() == 2
        by_category = {tx.category.name: tx.amount for tx in txs}
        assert by_category[PAYROLL_OUVRIER_CATEGORY_NAME] == Decimal('80.00')
        assert by_category[PAYROLL_INGENIEUR_CATEGORY_NAME] == Decimal('120.00')
        assert caisse.balance == Decimal('5000.00') - Decimal('200.00')


@pytest.mark.django_db
class TestBulkAllocationView:
    def test_engineer_sees_one_row_per_assignment(self, engineer_client, site, personnel_factory, assignment_factory):
        p1 = personnel_factory(first_name='A')
        p2 = personnel_factory(first_name='B')
        assignment_factory(personnel=p1, role='Peinture')
        assignment_factory(personnel=p2, role='Maçonnerie')
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        assert response.status_code == 200
        assert len(response.context['rows']) == 2

    def test_ineligible_personnel_excluded_from_rows(self, engineer_client, site, personnel_factory, assignment_factory):
        from chantiermobile.constants import PersonnelStatus
        p = personnel_factory(status=PersonnelStatus.NON_ELIGIBLE)
        assignment_factory(personnel=p)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        assert response.context['rows'] == []

    def test_ingenieur_assignments_excluded_from_rows(self, engineer_client, site, personnel_factory, assignment_factory):
        """Main d'œuvre only — an Ingénieur/Staff assignment on the same
        chantier must not show up here, even though SiteAssignment itself
        doesn't care about payroll_type."""
        ouvrier = personnel_factory(first_name='A', payroll_type=PersonnelPayrollType.OUVRIER)
        ingenieur = personnel_factory(first_name='B', payroll_type=PersonnelPayrollType.INGENIEUR)
        assignment_factory(personnel=ouvrier)
        assignment_factory(personnel=ingenieur)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        rows = response.context['rows']
        assert len(rows) == 1
        assert rows[0]['personnel'] == ouvrier

    def test_post_creates_items_for_filled_rows_only(self, engineer_client, site, personnel_factory, assignment_factory):
        p1 = personnel_factory(first_name='A')
        p2 = personnel_factory(first_name='B')
        a1 = assignment_factory(personnel=p1)
        a2 = assignment_factory(personnel=p2)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.post(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}), {
            f'amount_{a1.pk}': '75.00',
            f'amount_{a2.pk}': '',
        })
        assert response.status_code == 302
        assert PayrollListItem.objects.filter(payroll_list=pl).count() == 1
        item = PayrollListItem.objects.get(payroll_list=pl)
        assert item.personnel == p1
        assert item.assignment == a1
        assert item.amount == Decimal('75.00')

    def test_post_rejects_amount_over_cap_but_keeps_valid_rows(self, engineer_client, site, personnel_factory, assignment_factory):
        p1 = personnel_factory(first_name='A')
        p2 = personnel_factory(first_name='B')
        a1 = assignment_factory(personnel=p1, convention_amount=Decimal('50.00'))
        a2 = assignment_factory(personnel=p2)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.post(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}), {
            f'amount_{a1.pk}': '999.00',  # over the 50.00 cap
            f'amount_{a2.pk}': '30.00',
        })
        assert response.status_code == 302
        items = PayrollListItem.objects.filter(payroll_list=pl)
        assert items.count() == 1
        assert items.first().personnel == p2

    def test_director_can_access(self, director_client, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        assignment_factory(personnel=p)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        director_response = director_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        assert director_response.status_code == 200

    def test_accountant_cannot_access(self, accountant_client, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        assignment_factory(personnel=p)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        accountant_response = accountant_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        assert accountant_response.status_code == 302  # ACCOUNTANT not in PAYROLL_PREPARE_ROLES

    def test_non_brouillon_list_redirects(self, engineer_client, site, user, personnel_factory, assignment_factory, caisse):
        p = personnel_factory()
        assignment_factory(personnel=p)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p, amount=Decimal('10.00'))
        pl.submit(user)
        response = engineer_client.get(reverse('finance:payroll_allocate', kwargs={'pk': pl.pk}))
        assert response.status_code == 302


@pytest.mark.django_db
class TestLegacySingleItemPathStillWorks:
    """PayrollListItemCreateView / payroll_item_create must keep working —
    the bulk allocation screen supplements it, doesn't replace it."""
    def test_engineer_can_still_add_item_the_old_way(self, engineer_client, site, personnel_factory, assignment_factory):
        p = personnel_factory()
        assignment_factory(personnel=p)
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        response = engineer_client.post(reverse('finance:payroll_item_create', kwargs={'pk': pl.pk}), {
            'personnel': p.pk, 'amount': '45.00', 'progress_note': '',
        })
        assert response.status_code == 302
        assert PayrollListItem.objects.filter(payroll_list=pl, personnel=p, amount=Decimal('45.00')).exists()


@pytest.mark.django_db
class TestSalaryPaymentTabRevived:
    """"Ingénieurs & Staff" tab (SalaryPayment) — the counterpart to "Main
    d'œuvre", not the old deprecated/removed "Salaire bureau" screen."""

    def test_salary_payment_urls_resolve(self):
        assert reverse('finance:salary_payment_list')
        assert reverse('finance:salary_payment_create')

    def test_tabs_link_both_lists(self, director_client):
        payroll_url = reverse('finance:payroll_list').encode()
        salary_url = reverse('finance:salary_payment_list').encode()
        for url_name in ('finance:payroll_list', 'finance:salary_payment_list'):
            response = director_client.get(reverse(url_name))
            assert response.status_code == 200
            assert payroll_url in response.content
            assert salary_url in response.content

    def test_director_can_create_salary_payment(self, director_client, personnel_factory, caisse):
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR, monthly_salary=Decimal('600.00'))
        response = director_client.post(reverse('finance:salary_payment_create'), {
            'personnel': p.pk, 'period': '2026-09', 'amount': '600.00', 'caisse': caisse.pk, 'notes': '',
        })
        assert response.status_code == 302
        sp = SalaryPayment.objects.get(personnel=p, period='2026-09')
        assert sp.paid_by is not None
        tx = CaisseTransaction.objects.get(caisse=caisse, transaction_type=CaisseTransactionType.SORTIE)
        assert tx.amount == Decimal('600.00')
        assert tx.category.name == PAYROLL_INGENIEUR_CATEGORY_NAME
        assert tx.recipient == str(p)

    def test_engineer_role_cannot_create_salary_payment(self, engineer_client, personnel_factory, caisse):
        # ENGINEER is in PAYROLL_PREPARE_ROLES but not PAYROLL_DISBURSE_ROLES —
        # a salary payment is disbursed immediately, so it needs the
        # disburse-level roles, unlike a draft PayrollList.
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR)
        response = engineer_client.post(reverse('finance:salary_payment_create'), {
            'personnel': p.pk, 'period': '2026-09', 'amount': '600.00', 'caisse': caisse.pk, 'notes': '',
        })
        assert not SalaryPayment.objects.filter(personnel=p).exists()

    def test_form_only_offers_ingenieur_personnel(self, director_client, personnel_factory):
        ouvrier = personnel_factory(first_name='O', payroll_type=PersonnelPayrollType.OUVRIER)
        ingenieur = personnel_factory(first_name='I', payroll_type=PersonnelPayrollType.INGENIEUR)
        response = director_client.get(reverse('finance:salary_payment_create'))
        assert response.status_code == 200
        qs = response.context['form'].fields['personnel'].queryset
        assert ingenieur in qs
        assert ouvrier not in qs

    def test_ouvrier_rejected_by_view(self, director_client, personnel_factory, caisse):
        """An Ouvrier's pk posted directly (bypassing the dropdown) is still
        rejected — the form's personnel queryset excludes it, and
        SalaryPayment.clean() would reject it too if that were bypassed
        (see TestSalaryPayment.test_disburse_rejects_ouvrier_personnel in
        test_finance_money_flow_gaps.py for the direct model-level check)."""
        p = personnel_factory(payroll_type=PersonnelPayrollType.OUVRIER)
        response = director_client.post(reverse('finance:salary_payment_create'), {
            'personnel': p.pk, 'period': '2026-09', 'amount': '600.00', 'caisse': caisse.pk, 'notes': '',
        })
        assert response.status_code == 200  # form redisplayed with errors
        assert not SalaryPayment.objects.filter(personnel=p).exists()
