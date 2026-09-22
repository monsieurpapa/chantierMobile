"""
Tests for the Personnel / Liste de paie overhaul — demo feedback from the
finance team:

1. Personnel.payroll_type (Ouvrier vs Ingénieur) drives which caisse
   category a décaissement is booked under, and whether the per-convention
   cap applies.
2. SiteAssignment.convention_amount tracks a per-task convention cap
   (a worker can have several active conventions on the same chantier —
   see MO.xlsx from the demo, e.g. "Peinture alain" vs "Etancheité alain").
3. PayrollList.disburse() splits the décaissement into two categorized
   caisse transactions ("Main d'œuvre Ouvriers" / "Salaire Ingénieurs").
4. The bulk allocation screen (PayrollListAllocateView) lets the Archi
   allocate a Montant per SiteAssignment in one page, capped by the
   convention's remaining balance for Ouvriers.
5. "Salaire bureau" is gone from the UI (no nav link, no URLs) — the
   SalaryPayment model/table stays for historical data only.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import (
    Caisse, CaisseTransaction, CaisseTransactionCategory, PayrollList, PayrollListItem,
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

    def test_cap_does_not_apply_to_ingenieur(self, site, personnel_factory, assignment_factory):
        p = personnel_factory(payroll_type=PersonnelPayrollType.INGENIEUR)
        a = assignment_factory(personnel=p, convention_amount=Decimal('50.00'))
        pl = PayrollList.objects.create(site=site, prepared_by=None)
        item = PayrollListItem(payroll_list=pl, personnel=p, assignment=a, amount=Decimal('500.00'))
        item.full_clean()  # Ingénieur: convention cap not enforced

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
class TestSalaireBureauRemovedFromUI:
    def test_salary_payment_urls_are_gone(self):
        with pytest.raises(Exception):
            reverse('finance:salary_payment_list')
        with pytest.raises(Exception):
            reverse('finance:salary_payment_create')

    def test_nav_has_no_salary_payment_link(self, director_client):
        response = director_client.get(reverse('finance:payroll_list'))
        assert response.status_code == 200
        assert b'salary_payment' not in response.content
        assert 'Salaires du bureau'.encode('utf-8') not in response.content
