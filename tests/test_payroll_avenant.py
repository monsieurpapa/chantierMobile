"""
Tests for progressive worker payroll (liste de paie) and avenants
(budget change orders -> client debt) — Phase B2 of the Finance
module build-out.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import Caisse, CaisseTransaction, PayrollList, PayrollListItem, Avenant
from chantiermobile.constants import CaisseTransactionType, CaisseType, PayrollListStatus, AvenantStatus


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.mark.django_db
class TestPayrollListWorkflow:
    def test_submit_requires_items(self, site, user):
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        with pytest.raises(ValidationError):
            pl.submit(user)

    def test_full_workflow_disburses_from_caisse(self, site, personnel_factory, caisse_factory, user):
        p1 = personnel_factory(first_name='A')
        p2 = personnel_factory(first_name='B')
        caisse = caisse_factory()
        caisse.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)

        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p1, amount=Decimal('150.00'))
        PayrollListItem.objects.create(payroll_list=pl, personnel=p2, amount=Decimal('100.00'))

        assert pl.total_amount == Decimal('250.00')

        pl.submit(user)
        assert pl.status == PayrollListStatus.SOUMISE

        pl.disburse(user, caisse)
        pl.refresh_from_db()
        assert pl.status == PayrollListStatus.PAYEE
        assert caisse.balance == Decimal('750.00')
        assert pl.caisse == caisse

    def test_disburse_rejects_insufficient_caisse_balance(self, site, personnel_factory, caisse_factory, user):
        p1 = personnel_factory()
        caisse = caisse_factory()  # empty
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p1, amount=Decimal('150.00'))
        pl.submit(user)
        with pytest.raises(ValidationError):
            pl.disburse(user, caisse)

    def test_cannot_disburse_a_draft(self, site, personnel_factory, caisse_factory, user):
        p1 = personnel_factory()
        caisse = caisse_factory()
        caisse.record(CaisseTransactionType.ENTREE, Decimal('1000'), user)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p1, amount=Decimal('50'))
        with pytest.raises(ValidationError):
            pl.disburse(user, caisse)


@pytest.mark.django_db
class TestPayrollListViews:
    def test_engineer_can_create_and_add_items(self, engineer_client, site, personnel_factory):
        from personnel.models import SiteAssignment
        p = personnel_factory()
        SiteAssignment.objects.create(personnel=p, site=site, role='Ouvrier', start_date=date.today(), daily_rate=Decimal('20.00'))
        response = engineer_client.post(reverse('finance:payroll_create'), {
            'site': site.pk, 'phase': '', 'notes': 'Avancement 50%',
        })
        assert response.status_code == 302
        pl = PayrollList.objects.get(site=site)

        response = engineer_client.post(reverse('finance:payroll_item_create', kwargs={'pk': pl.pk}), {
            'personnel': p.pk, 'amount': '120.00', 'progress_note': 'Semaine 1',
        })
        assert response.status_code == 302
        assert PayrollListItem.objects.filter(payroll_list=pl, personnel=p).exists()

    def test_worker_cannot_view_payroll_list(self, client, cabinet, site, django_user_model, personnel_factory, user):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        worker = django_user_model.objects.create_user(username='worker2', password='testpass123')
        UserCabinetRole.objects.create(user=worker, cabinet=cabinet, role=UserRoles.WORKER, status=ApprovalStatus.APPROVED)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        client.login(username='worker2', password='testpass123')
        response = client.get(reverse('finance:payroll_detail', kwargs={'pk': pl.pk}))
        assert response.status_code == 302

    def test_cashier_can_disburse(self, client, cabinet, site, django_user_model, personnel_factory, caisse_factory, user):
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        cashier = django_user_model.objects.create_user(username='cashier1', password='testpass123')
        UserCabinetRole.objects.create(user=cashier, cabinet=cabinet, role=UserRoles.CASHIER, status=ApprovalStatus.APPROVED)

        p = personnel_factory()
        caisse = caisse_factory()
        caisse.record(CaisseTransactionType.ENTREE, Decimal('500'), user)
        pl = PayrollList.objects.create(site=site, prepared_by=user)
        PayrollListItem.objects.create(payroll_list=pl, personnel=p, amount=Decimal('100'))
        pl.submit(user)

        client.login(username='cashier1', password='testpass123')
        response = client.post(reverse('finance:payroll_disburse', kwargs={'pk': pl.pk}), {'caisse': caisse.pk})
        assert response.status_code == 302
        pl.refresh_from_db()
        assert pl.status == PayrollListStatus.PAYEE


@pytest.mark.django_db
class TestAvenant:
    def test_approve_extends_budget_and_client_debt(self, site, user):
        from finance.models import Budget
        from revenue.models import Contract
        budget = Budget.objects.create(site=site, total_amount=Decimal('10000'), start_date=date.today(), end_date=date(date.today().year + 1, 1, 1))
        contract = Contract.objects.create(site=site, client_name='Client X', total_value=Decimal('20000'), signed_date=date.today())

        avenant = Avenant.objects.create(site=site, amount=Decimal('2000'), justification='Travaux additionnels', requested_by=user)
        avenant.approve(user, notes='OK')

        budget.refresh_from_db()
        contract.refresh_from_db()
        assert budget.total_amount == Decimal('12000')
        assert contract.avenant_debt == Decimal('2000')
        assert contract.client_balance == Decimal('22000')  # 20000 + 2000 avenant - 0 paid

    def test_reject_leaves_budget_untouched(self, site, user):
        from finance.models import Budget
        budget = Budget.objects.create(site=site, total_amount=Decimal('10000'), start_date=date.today(), end_date=date(date.today().year + 1, 1, 1))
        avenant = Avenant.objects.create(site=site, amount=Decimal('2000'), justification='x', requested_by=user)
        avenant.reject(user, notes='Non justifié')
        budget.refresh_from_db()
        assert budget.total_amount == Decimal('10000')
        assert avenant.status == AvenantStatus.REJECTED

    def test_cannot_decide_twice(self, site, user):
        avenant = Avenant.objects.create(site=site, amount=Decimal('500'), justification='x', requested_by=user)
        avenant.approve(user)
        with pytest.raises(ValidationError):
            avenant.approve(user)

    def test_expense_beyond_original_budget_allowed_after_avenant(self, site, expense_category, user, django_user_model):
        """The whole point of an avenant: once approved, a bigger expense
        that would have exceeded the original budget must go through."""
        from finance.models import Budget, Expense
        from chantiermobile.constants import ExpenseStatus
        approver = django_user_model.objects.create_user(username='approver1', password='testpass123')
        budget = Budget.objects.create(site=site, total_amount=Decimal('1000'), start_date=date.today(), end_date=date(date.today().year + 1, 1, 1))
        avenant = Avenant.objects.create(site=site, amount=Decimal('500'), justification='x', requested_by=user)
        avenant.approve(user)

        expense = Expense.objects.create(
            site=site, requester=user, category=expense_category,
            amount=Decimal('1400.00'), expense_date=date.today(), description='Gros achat', status=ExpenseStatus.PENDING,
        )
        expense.approve(approver)  # would fail if budget hadn't grown to 1500
        assert expense.status == ExpenseStatus.APPROVED


@pytest.mark.django_db
class TestAvenantViews:
    def test_director_can_approve_avenant(self, director_client, site, user):
        avenant = Avenant.objects.create(site=site, amount=Decimal('300'), justification='x', requested_by=user)
        response = director_client.post(reverse('finance:avenant_approve', kwargs={'pk': avenant.pk}), {'notes': 'ok'})
        avenant.refresh_from_db()
        assert response.status_code == 302
        assert avenant.status == AvenantStatus.APPROVED

    def test_engineer_cannot_approve_avenant(self, engineer_client, site, user):
        avenant = Avenant.objects.create(site=site, amount=Decimal('300'), justification='x', requested_by=user)
        response = engineer_client.post(reverse('finance:avenant_approve', kwargs={'pk': avenant.pk}), {'notes': 'ok'})
        avenant.refresh_from_db()
        assert avenant.status == AvenantStatus.PENDING
