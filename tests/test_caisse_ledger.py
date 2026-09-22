"""
Tests for the Caisse ledger (Phase B1 of the Finance module build-out):
balance-tracked cash registers, the daily cashbook, inter-caisse loans
with repayment tracking, and plain transfers (e.g. to the caisse de
gestion administrative).
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import Caisse, CaisseTransaction, CaisseLoan
from chantiermobile.constants import CaisseTransactionType, CaisseType


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.mark.django_db
class TestCaisseBalance:
    def test_new_caisse_has_zero_balance(self, caisse_factory):
        c = caisse_factory()
        assert c.balance == 0

    def test_entree_increases_balance(self, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('500.00'), user)
        assert c.balance == Decimal('500.00')

    def test_sortie_decreases_balance(self, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('500.00'), user)
        c.record(CaisseTransactionType.SORTIE, Decimal('200.00'), user)
        assert c.balance == Decimal('300.00')

    def test_negative_amount_rejected(self, caisse_factory, user):
        c = caisse_factory()
        tx = CaisseTransaction(caisse=c, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('-10'), date=date.today(), recorded_by=user)
        with pytest.raises(ValidationError):
            tx.full_clean()


@pytest.mark.django_db
class TestCaisseTransfer:
    def test_transfer_moves_funds_between_caisses(self, caisse_factory, user):
        source = caisse_factory(name='Chantier')
        admin = caisse_factory(name='Administrative', is_administrative=True)
        source.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)

        source.transfer_to(admin, Decimal('400.00'), user, description='Remise quotidienne')

        assert source.balance == Decimal('600.00')
        assert admin.balance == Decimal('400.00')

    def test_transfer_to_self_is_rejected(self, caisse_factory, user):
        c = caisse_factory()
        with pytest.raises(ValueError):
            c.transfer_to(c, Decimal('10'), user)

    def test_transfer_view_rejects_insufficient_balance(self, director_client, caisse_factory, cabinet):
        source = caisse_factory(name='Empty')
        target = caisse_factory(name='Target')
        response = director_client.post(
            reverse('finance:caisse_transfer', kwargs={'pk': source.pk}),
            {'target_caisse': target.pk, 'amount': '100.00', 'description': 'test'},
        )
        assert response.status_code == 302
        assert source.balance == 0
        assert target.balance == 0


@pytest.mark.django_db
class TestCaisseLoan:
    def test_lend_moves_funds_and_tracks_outstanding(self, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        equip.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)

        loan = CaisseLoan.objects.create(
            lender_caisse=equip, borrower_caisse=site_caisse,
            amount=Decimal('300.00'), date=date.today(),
        )
        loan.disburse(user)

        assert equip.balance == Decimal('700.00')
        assert site_caisse.balance == Decimal('300.00')
        assert loan.outstanding_balance == Decimal('300.00')
        assert loan.is_fully_repaid is False

    def test_partial_then_full_repayment(self, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        equip.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)
        loan = CaisseLoan.objects.create(lender_caisse=equip, borrower_caisse=site_caisse, amount=Decimal('300.00'), date=date.today())
        loan.disburse(user)

        loan.repay(Decimal('100.00'), user)
        loan.refresh_from_db()
        assert loan.outstanding_balance == Decimal('200.00')
        assert site_caisse.balance == Decimal('200.00')
        assert equip.balance == Decimal('800.00')

        loan.repay(Decimal('200.00'), user)
        loan.refresh_from_db()
        assert loan.is_fully_repaid is True
        assert equip.balance == Decimal('1000.00')
        assert site_caisse.balance == Decimal('0.00')

    def test_overpayment_rejected(self, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        loan = CaisseLoan.objects.create(lender_caisse=equip, borrower_caisse=site_caisse, amount=Decimal('300.00'), date=date.today())
        loan.disburse(user)
        with pytest.raises(ValidationError):
            loan.repay(Decimal('301.00'), user)

    def test_lender_and_borrower_must_differ(self, caisse_factory):
        c = caisse_factory()
        loan = CaisseLoan(lender_caisse=c, borrower_caisse=c, amount=Decimal('10'), date=date.today())
        with pytest.raises(ValidationError):
            loan.clean()

    def test_repay_view_rbac(self, engineer_client, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        loan = CaisseLoan.objects.create(lender_caisse=equip, borrower_caisse=site_caisse, amount=Decimal('300.00'), date=date.today())
        loan.disburse(user)
        response = engineer_client.post(reverse('finance:caisse_loan_repay', kwargs={'pk': loan.pk}), {'amount': '50.00'})
        loan.refresh_from_db()
        assert loan.repaid_amount == Decimal('0.00')


@pytest.mark.django_db
class TestCaisseViews:
    def test_director_can_create_caisse(self, director_client, cabinet):
        response = director_client.post(reverse('finance:caisse_create'), {
            'name': 'Caisse principale', 'caisse_type': CaisseType.PRINCIPALE, 'site': '', 'is_administrative': 'on',
        })
        assert response.status_code == 302
        assert Caisse.objects.filter(cabinet=cabinet, name='Caisse principale', is_administrative=True).exists()

    def test_engineer_cannot_create_caisse(self, engineer_client, cabinet):
        response = engineer_client.post(reverse('finance:caisse_create'), {
            'name': 'Caisse X', 'caisse_type': CaisseType.SECONDAIRE, 'site': '',
        })
        assert not Caisse.objects.filter(name='Caisse X').exists()

    def test_caisse_detail_shows_running_balance(self, director_client, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('100.00'), user, date=date.today() - timedelta(days=1))
        c.record(CaisseTransactionType.SORTIE, Decimal('30.00'), user, date=date.today())
        response = director_client.get(reverse('finance:caisse_detail', kwargs={'pk': c.pk}))
        assert response.status_code == 200
        assert response.context['closing_balance'] == Decimal('70.00')

    def test_record_transaction_view_scoped_to_caisse(self, director_client, caisse_factory):
        c = caisse_factory()
        response = director_client.post(reverse('finance:caisse_transaction_create', kwargs={'pk': c.pk}), {
            'transaction_type': CaisseTransactionType.ENTREE, 'amount': '250.00', 'date': date.today(), 'description': 'Encaissement',
        })
        assert response.status_code == 302
        assert c.balance == Decimal('250.00')

    def test_caisse_report_filters_by_caisse(self, director_client, caisse_factory, user):
        c1 = caisse_factory(name='C1')
        c2 = caisse_factory(name='C2')
        c1.record(CaisseTransactionType.ENTREE, Decimal('10'), user)
        c2.record(CaisseTransactionType.ENTREE, Decimal('20'), user)
        response = director_client.get(reverse('finance:caisse_report'), {'caisse': c1.pk})
        txs = list(response.context['transactions'])
        assert len(txs) == 1
        assert txs[0].caisse_id == c1.pk


@pytest.mark.django_db
class TestExpensePhaseLink:
    def test_expense_can_link_to_a_phase(self, site, expense_category, user):
        from finance.models import Expense
        from projects.models import ProjectPhase
        phase = ProjectPhase.objects.create(site=site, name='Fondations', start_date=date.today())
        expense = Expense.objects.create(
            site=site, phase=phase, requester=user, category=expense_category,
            amount=Decimal('50.00'), expense_date=date.today(), description='test',
        )
        assert expense.phase == phase
