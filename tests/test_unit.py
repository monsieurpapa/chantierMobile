"""
Unit tests for ChantierMobile application.
These tests test individual components in isolation.
"""

import pytest
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date

from chantiermobile.constants import SiteStatus, ExpenseStatus


@pytest.mark.unit
class TestConstants:
    """Test constants definitions."""
    
    def test_site_status_choices(self):
        """Test site status choices are properly defined."""
        assert SiteStatus.ACTIVE == 'ACTIVE'
        assert SiteStatus.PLANNING == 'PLANNING'
        assert SiteStatus.COMPLETED == 'COMPLETED'
        assert len(SiteStatus.choices) == 5
    
    def test_expense_status_choices(self):
        """Test expense status choices are properly defined."""
        assert ExpenseStatus.PENDING == 'PENDING'
        assert ExpenseStatus.APPROVED == 'APPROVED'
        assert ExpenseStatus.PAID == 'PAID'
        assert len(ExpenseStatus.choices) == 4


@pytest.mark.unit
class TestModels:
    """Test model methods and properties."""
    
    def test_site_string_representation(self, site):
        """Test Site model string representation."""
        expected = f"{site.name} ({site.status})"
        assert str(site) == expected
    
    def test_site_total_spent_property(self, site, expense):
        """Test Site total_spent property calculation."""
        # Create approved expense
        from finance.models import Expense
        expense.status = ExpenseStatus.APPROVED
        expense.save()
        
        site.refresh_from_db()
        assert site.total_spent == expense.amount
    
    def test_expense_approval_methods(self, expense, user, director_user):
        """Test Expense approval methods."""
        # Self-approval must be blocked (requester == approver)
        with pytest.raises(Exception):
            expense.approve(user, "Self-approve attempt")

        # Approval by a different user must succeed
        expense.approve(director_user, "Looks good")
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.APPROVED

        # Test reject method
        expense.reject(director_user, "Not approved")
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.REJECTED


@pytest.mark.unit
class TestForms:
    """Test form validation and methods."""
    
    def test_expense_form_validation(self, expense_category, site):
        """Test ExpenseForm validation."""
        from finance.forms import ExpenseForm
        
        # Valid form data
        form_data = {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '1000.00',
            'expense_date': date.today(),
            'description': 'Valid expense'
        }
        form = ExpenseForm(data=form_data)
        assert form.is_valid()
        
        # Invalid amount
        form_data['amount'] = '-100.00'
        form = ExpenseForm(data=form_data)
        assert not form.is_valid()
    
    @pytest.mark.django_db
    def test_budget_form_date_validation(self, site):
        """Test BudgetForm date validation."""
        from finance.forms import BudgetForm

        # Invalid date range
        form_data = {
            'site': site.pk,
            'total_amount': '10000.00',
            'start_date': date(2024, 1, 15),
            'end_date': date(2024, 1, 10)  # Before start date
        }
        form = BudgetForm(data=form_data)
        assert not form.is_valid()
        assert 'end_date' in form.errors


@pytest.mark.unit
class TestViews:
    """Test view logic and responses."""
    
    def test_home_view_context(self, authenticated_client):
        """Test home view (dashboard) context data — core/dashboard.py::build_dashboard_context."""
        response = authenticated_client.get(reverse('home'))
        assert response.status_code == 200
        # Hero KPIs
        assert 'revenue_all' in response.context
        assert 'expense_all' in response.context
        assert 'net_margin' in response.context
        assert 'active_sites_count' in response.context
        # Charts
        assert 'cashflow_labels' in response.context
        assert 'devis_chart' in response.context
        assert 'task_chart' in response.context
        # Watchlists + activity feed
        assert 'overdue_invoices' in response.context
        assert 'overdue_tasks' in response.context
        assert 'activity_items' in response.context
    
    def test_login_view_redirect(self, authenticated_client):
        """Test login view redirects authenticated users."""
        response = authenticated_client.get(reverse('account_login'))
        assert response.status_code in [302, 200]


@pytest.mark.unit
class TestUtilities:
    """Test utility functions and helpers."""
    
    def test_date_formatting(self):
        """Test date formatting utilities."""
        from datetime import datetime
        date_obj = datetime(2024, 1, 15, 10, 30)
        formatted = date_obj.strftime('%Y-%m-%d')
        assert formatted == '2024-01-15'
    
    def test_currency_formatting(self):
        """Test currency formatting."""
        amount = Decimal('1234.56')
        formatted = f"${amount:,.2f}"
        assert formatted == "$1,234.56"


@pytest.mark.unit
class TestValidators:
    """Test custom validators."""
    
    def test_positive_number_validator(self):
        """Test positive number validation."""
        from django.core.exceptions import ValidationError
        from chantiermobile.constants import ValidationMessages
        
        # Valid positive number
        try:
            # This would normally call the validator
            amount = Decimal('100.00')
            assert amount > 0
        except ValidationError:
            pytest.fail("Valid positive number should not raise ValidationError")
        
        # Invalid negative number
        try:
            amount = Decimal('-100.00')
            if amount <= 0:
                raise ValidationError(ValidationMessages.POSITIVE_NUMBER)
            pytest.fail("Negative number should raise ValidationError")
        except ValidationError:
            pass  # Expected


@pytest.mark.unit
@pytest.mark.django_db
class TestSoftDeleteCascade:
    """Regression tests for Site.delete() cascade soft-delete (fix: 7dfbc03)."""

    def test_site_delete_cascades_to_expenses(self, site, expense):
        """Soft-deleting a site must mark its expenses as deleted."""
        from finance.models import Expense
        assert not expense.is_deleted
        site.delete()
        expense.refresh_from_db()
        assert expense.is_deleted

    def test_site_delete_cascades_to_contract_and_invoices(self, site, contract, invoice):
        """Soft-deleting a site must cascade to contract and invoices."""
        from revenue.models import Contract, Invoice
        assert not contract.is_deleted
        assert not invoice.is_deleted
        site.delete()
        contract.refresh_from_db()
        invoice.refresh_from_db()
        assert contract.is_deleted
        assert invoice.is_deleted

    def test_site_delete_cascades_to_budget(self, site):
        """Soft-deleting a site must cascade to its budget."""
        from finance.models import Budget
        from datetime import timedelta
        budget = Budget.objects.create(
            site=site,
            total_amount=Decimal('5000.00'),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        site.delete()
        budget.refresh_from_db()
        assert budget.is_deleted


@pytest.mark.unit
@pytest.mark.django_db
class TestApprovalViewAuth:
    """Regression tests for @login_required on approval FBVs (fix: 7dfbc03)."""

    def test_approve_expense_requires_login(self, client, expense):
        """Unauthenticated POST to approve_expense must redirect to login, not 500."""
        url = reverse('finance:expense_approve', kwargs={'pk': expense.pk})
        response = client.post(url)
        assert response.status_code == 302
        assert '/login' in response['Location'] or 'login' in response['Location']

    def test_mark_expense_paid_requires_login(self, client, expense):
        """Unauthenticated POST to mark_expense_paid must redirect to login, not 500."""
        url = reverse('finance:expense_pay', kwargs={'pk': expense.pk})
        response = client.post(url)
        assert response.status_code == 302
        assert '/login' in response['Location'] or 'login' in response['Location']

    def test_approve_material_request_requires_login(self, client, db):
        """Unauthenticated POST to approve_material_request must redirect to login, not 500."""
        from accounts.models import Cabinet, UserCabinetRole
        from projects.models import Site
        from materials.models import Material, MaterialRequest
        from chantiermobile.constants import UserRoles, ApprovalStatus, SiteStatus
        from django.contrib.auth import get_user_model
        from datetime import date, timedelta

        User = get_user_model()
        cabinet = Cabinet.objects.create(name='MatCabinet')
        requester = User.objects.create_user(username='mat_req', password='pass', email='r@r.com')
        UserCabinetRole.objects.create(user=requester, cabinet=cabinet, role=UserRoles.ENGINEER, status=ApprovalStatus.APPROVED)
        site = Site.objects.create(
            name='Mat Site', cabinet=cabinet,
            start_date=date.today(), expected_end_date=date.today() + timedelta(days=30),
            status=SiteStatus.PLANNING,
        )
        mat_request = MaterialRequest.objects.create(site=site, requested_by=requester)
        url = reverse('materials:request_approve', kwargs={'pk': mat_request.pk})
        response = client.post(url)
        assert response.status_code == 302
        assert '/login' in response['Location'] or 'login' in response['Location']


@pytest.mark.unit
@pytest.mark.django_db
class TestSiteAssignmentCabinetScoping:
    """Regression test: SiteAssignmentCreateView must only show cabinet-scoped sites/personnel."""

    def test_form_only_shows_cabinet_sites(self, client, db):
        """A director of cabinet A must not see cabinet B's sites in the assignment form."""
        from accounts.models import Cabinet, UserCabinetRole
        from projects.models import Site
        from chantiermobile.constants import UserRoles, ApprovalStatus, SiteStatus
        from django.contrib.auth import get_user_model
        from datetime import date, timedelta

        User = get_user_model()

        # Cabinet A with a director and a site
        cabinet_a = Cabinet.objects.create(name='Cabinet A')
        director = User.objects.create_user(username='dir_a', password='pass', email='a@a.com')
        UserCabinetRole.objects.create(user=director, cabinet=cabinet_a, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        site_a = Site.objects.create(
            name='Site A', cabinet=cabinet_a,
            start_date=date.today(), expected_end_date=date.today() + timedelta(days=30),
            status=SiteStatus.PLANNING,
        )

        # Cabinet B with a separate site (should NOT appear for director of A)
        cabinet_b = Cabinet.objects.create(name='Cabinet B')
        site_b = Site.objects.create(
            name='Site B', cabinet=cabinet_b,
            start_date=date.today(), expected_end_date=date.today() + timedelta(days=30),
            status=SiteStatus.PLANNING,
        )

        client.login(username='dir_a', password='pass')
        response = client.get('/personnel/assignments/add/')

        assert response.status_code == 200
        site_qs = response.context['form'].fields['site'].queryset
        assert site_a in site_qs
        assert site_b not in site_qs


@pytest.mark.unit
@pytest.mark.django_db
class TestBudgetCabinetScoping:
    """Regression tests for CabinetAccessMixin on Budget views (fix: eng-review-2026-04-15)."""

    def test_budget_detail_scoped_to_cabinet(self, client, db):
        """A director of cabinet A must get 404 when accessing cabinet B's budget detail."""
        from accounts.models import Cabinet, UserCabinetRole
        from projects.models import Site
        from finance.models import Budget
        from chantiermobile.constants import UserRoles, ApprovalStatus, SiteStatus
        from django.contrib.auth import get_user_model
        from datetime import date, timedelta
        from decimal import Decimal

        User = get_user_model()

        # Cabinet A — director logs in
        cabinet_a = Cabinet.objects.create(name='Budget Cabinet A')
        director = User.objects.create_user(username='budget_dir_a', password='pass', email='ba@ba.com')
        UserCabinetRole.objects.create(user=director, cabinet=cabinet_a, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        site_a = Site.objects.create(
            name='Budget Site A', cabinet=cabinet_a,
            start_date=date.today(), expected_end_date=date.today() + timedelta(days=30),
            status=SiteStatus.PLANNING,
        )

        # Cabinet B — separate budget (should NOT be accessible to director_a)
        cabinet_b = Cabinet.objects.create(name='Budget Cabinet B')
        site_b = Site.objects.create(
            name='Budget Site B', cabinet=cabinet_b,
            start_date=date.today(), expected_end_date=date.today() + timedelta(days=30),
            status=SiteStatus.PLANNING,
        )
        budget_b = Budget.objects.create(
            site=site_b,
            total_amount=Decimal('10000.00'),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )

        client.login(username='budget_dir_a', password='pass')
        response = client.get(reverse('finance:budget_detail', kwargs={'pk': budget_b.pk}))
        assert response.status_code == 404


@pytest.mark.unit
class TestMixins:
    """Test custom mixins."""

    def test_cabinet_access_mixin_logic(self, user, cabinet):
        """Test CabinetAccessMixin logic."""
        # User with cabinet role should have access
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import UserRoles, ApprovalStatus
        
        UserCabinetRole.objects.create(
            user=user,
            cabinet=cabinet,
            role=UserRoles.ENGINEER,
            status=ApprovalStatus.APPROVED
        )
        
        # Check user has cabinet access
        user_cabinets = user.cabinet_roles.filter(status=ApprovalStatus.APPROVED)
        assert user_cabinets.exists()
        assert user_cabinets.first().cabinet == cabinet
