"""
Tests for the three Finance "money-flow" gaps flagged by the feature-vs-
proposal audit and fixed in this phase:

1. Expense payments never touched the caisse ledger — Expense.pay() now
   records the matching CaisseTransaction (finance/models.py, mark_expense_paid).
2. No way to pay office/admin monthly salaries — new SalaryPayment model,
   drawing on Personnel.monthly_salary, disbursed from a Caisse.
3. MaterialRequest.expense was a dead field — MaterialRequest.authorize()
   now creates and links the matching, pre-approved Expense.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import (
    Expense, ExpenseApproval, Caisse, CaisseTransaction, SalaryPayment,
)
from chantiermobile.constants import (
    CaisseTransactionType, CaisseType, ExpenseStatus, ExpenseNature,
    UserRoles, ApprovalStatus,
)
from materials.models import MaterialRequest, MaterialRequestItem, Material


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
def cashier_client(client, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    u = get_user_model().objects.create_user(username='cashier_mf', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.APPROVED)
    client.login(username='cashier_mf', password='testpass123')
    return client


@pytest.fixture
def approved_expense(site, expense_category, user):
    return Expense.objects.create(
        site=site, requester=user, category=expense_category,
        amount=Decimal('200.00'), expense_date=date.today(),
        description='Achat ciment', status=ExpenseStatus.APPROVED,
    )


@pytest.mark.django_db
class TestExpensePay:
    def test_pay_records_caisse_outflow(self, approved_expense, caisse, user):
        approved_expense.pay(user, caisse)
        approved_expense.refresh_from_db()
        assert approved_expense.status == ExpenseStatus.PAID
        assert caisse.balance == Decimal('4800.00')
        tx = CaisseTransaction.objects.get(expense=approved_expense)
        assert tx.transaction_type == CaisseTransactionType.SORTIE
        assert tx.amount == Decimal('200.00')
        assert tx.site == approved_expense.site

    def test_pay_rejects_insufficient_balance(self, approved_expense, caisse_factory, user):
        empty_caisse = caisse_factory(name='Caisse vide')
        with pytest.raises(ValidationError):
            approved_expense.pay(user, empty_caisse)
        approved_expense.refresh_from_db()
        assert approved_expense.status == ExpenseStatus.APPROVED
        assert not CaisseTransaction.objects.filter(expense=approved_expense).exists()

    def test_pay_rejects_non_approved_expense(self, site, expense_category, user, caisse):
        pending = Expense.objects.create(
            site=site, requester=user, category=expense_category,
            amount=Decimal('50'), expense_date=date.today(),
            description='x', status=ExpenseStatus.PENDING,
        )
        with pytest.raises(ValidationError):
            pending.pay(user, caisse)


@pytest.mark.django_db
class TestMarkExpensePaidView:
    def test_cashier_pay_with_caisse_creates_transaction(self, cashier_client, approved_expense, caisse):
        response = cashier_client.post(
            reverse('finance:expense_pay', kwargs={'pk': approved_expense.pk}), {'caisse': caisse.pk}
        )
        assert response.status_code == 302
        approved_expense.refresh_from_db()
        assert approved_expense.status == ExpenseStatus.PAID
        assert CaisseTransaction.objects.filter(expense=approved_expense, caisse=caisse).exists()

    def test_pay_without_selecting_caisse_does_not_pay(self, cashier_client, approved_expense):
        response = cashier_client.post(
            reverse('finance:expense_pay', kwargs={'pk': approved_expense.pk}), {}
        )
        assert response.status_code == 302
        approved_expense.refresh_from_db()
        assert approved_expense.status == ExpenseStatus.APPROVED

    def test_expense_detail_offers_pay_form_to_cashier(self, cashier_client, approved_expense, caisse):
        response = cashier_client.get(reverse('finance:expense_detail', kwargs={'pk': approved_expense.pk}))
        assert response.status_code == 200
        assert 'pay_form' in response.context
        assert caisse in response.context['pay_form'].fields['caisse'].queryset

    def test_engineer_cannot_pay(self, engineer_client, approved_expense, caisse):
        response = engineer_client.post(
            reverse('finance:expense_pay', kwargs={'pk': approved_expense.pk}), {'caisse': caisse.pk}
        )
        approved_expense.refresh_from_db()
        assert approved_expense.status == ExpenseStatus.APPROVED


@pytest.mark.django_db
class TestSalaryPayment:
    def test_disburse_records_caisse_outflow(self, personnel_factory, caisse, user):
        p = personnel_factory(monthly_salary=Decimal('450.00'))
        sp = SalaryPayment.objects.create(personnel=p, period='2026-09', amount=Decimal('450.00'), caisse=caisse)
        sp.disburse(user)
        assert caisse.balance == Decimal('4550.00')
        tx = CaisseTransaction.objects.get(caisse=caisse, transaction_type=CaisseTransactionType.SORTIE)
        assert tx.amount == Decimal('450.00')
        sp.refresh_from_db()
        assert sp.paid_by == user

    def test_disburse_rejects_insufficient_balance(self, personnel_factory, caisse_factory, user):
        p = personnel_factory(monthly_salary=Decimal('450.00'))
        empty_caisse = caisse_factory(name='Vide')
        sp = SalaryPayment.objects.create(personnel=p, period='2026-09', amount=Decimal('450.00'), caisse=empty_caisse)
        with pytest.raises(ValidationError):
            sp.disburse(user)

    def test_duplicate_period_for_same_personnel_rejected_by_db(self, personnel_factory, caisse):
        from django.db import IntegrityError, transaction as db_transaction
        p = personnel_factory(monthly_salary=Decimal('450.00'))
        SalaryPayment.objects.create(personnel=p, period='2026-09', amount=Decimal('450.00'), caisse=caisse)
        with pytest.raises(IntegrityError):
            with db_transaction.atomic():
                SalaryPayment.objects.create(personnel=p, period='2026-09', amount=Decimal('450.00'), caisse=caisse)

    def test_invalid_period_format_rejected(self, personnel_factory, caisse):
        p = personnel_factory(monthly_salary=Decimal('450.00'))
        sp = SalaryPayment(personnel=p, period='sept-2026', amount=Decimal('450.00'), caisse=caisse)
        with pytest.raises(ValidationError):
            sp.full_clean()


# NOTE: the view-level TestSalaryPaymentViews class (salary_payment_create /
# salary_payment_list) was removed along with the "Salaires du bureau" UI —
# see finance.models.SalaryPayment's DEPRECATED docstring and
# tests/test_personnel_payroll_overhaul.py for the replacement Liste de
# paie flow (Personnel.payroll_type == INGENIEUR). TestSalaryPayment above
# still covers the model itself, which is kept for historical data.


@pytest.fixture
def material_with_cost(site, user):
    material = Material.objects.create(name='Ciment', unit='sac', estimated_cost_per_unit=Decimal('12.50'))
    req = MaterialRequest.objects.create(site=site, requested_by=user, status='PENDING')
    MaterialRequestItem.objects.create(request=req, material=material, quantity=Decimal('10.00'))
    return req


@pytest.fixture
def magasinier_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    u = get_user_model().objects.create_user(username='magasinier_mf', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.MAGASINIER, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def dt_user(db, cabinet):
    from django.contrib.auth import get_user_model
    from accounts.models import UserCabinetRole
    u = get_user_model().objects.create_user(username='dt_mf', password='testpass123')
    UserCabinetRole.objects.create(user=u, cabinet=cabinet, role=UserRoles.DIRECTEUR_TECHNIQUE, status=ApprovalStatus.APPROVED)
    return u


@pytest.fixture
def dt_client(client, dt_user):
    client.login(username='dt_mf', password='testpass123')
    return client


@pytest.mark.django_db
class TestMaterialRequestExpenseLink:
    def test_authorize_creates_linked_approved_expense(self, material_with_cost, magasinier_user, dt_user):
        req = material_with_cost
        req.magasinier_validate(magasinier_user)
        req.authorize(dt_user)
        req.refresh_from_db()
        assert req.expense_id is not None
        assert req.expense.amount == Decimal('125.00')  # 10 * 12.50
        assert req.expense.status == ExpenseStatus.APPROVED
        assert req.expense.site == req.site
        assert req.expense.nature == ExpenseNature.MATERIEL
        approval = ExpenseApproval.objects.get(expense=req.expense)
        assert approval.approver == dt_user
        assert approval.status == ExpenseApproval.Status.APPROVED

    def test_authorize_without_estimated_cost_creates_no_expense(self, site, user, magasinier_user, dt_user):
        material = Material.objects.create(name='Autre', unit='u')  # no estimated_cost_per_unit
        req = MaterialRequest.objects.create(site=site, requested_by=user, status='PENDING')
        MaterialRequestItem.objects.create(request=req, material=material, quantity=Decimal('3.00'))
        req.magasinier_validate(magasinier_user)
        req.authorize(dt_user)
        req.refresh_from_db()
        assert req.expense_id is None

    def test_authorize_blocked_when_it_would_exceed_budget(self, material_with_cost, magasinier_user, dt_user, site):
        from finance.models import Budget
        Budget.objects.create(site=site, total_amount=Decimal('10'), start_date=date.today(), end_date=date(date.today().year + 1, 1, 1))
        req = material_with_cost
        req.magasinier_validate(magasinier_user)
        with pytest.raises(ValidationError):
            req.authorize(dt_user)
        req.refresh_from_db()
        # The whole authorization rolls back — état de besoin stays VALIDATED,
        # not silently APPROVED with no linked expense.
        assert req.status == 'VALIDATED'
        assert req.expense_id is None

    def test_authorize_via_view_shows_linked_expense_message(self, dt_client, material_with_cost, magasinier_user):
        req = material_with_cost
        req.magasinier_validate(magasinier_user)
        response = dt_client.post(
            reverse('materials:request_approve', kwargs={'pk': req.pk}), {'action': 'approve'}, follow=True
        )
        req.refresh_from_db()
        assert req.expense_id is not None
        messages = [str(m) for m in response.context['messages']]
        assert any('EX-' in m for m in messages)
