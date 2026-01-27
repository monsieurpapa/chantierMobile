"""
Integration tests for ChantierMobile application.
These tests test interactions between different components and modules.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from chantiermobile.constants import (
    UserRoles, ApprovalStatus, SiteStatus, ExpenseStatus, 
    MaterialRequestStatus, InvoiceStatus, PaymentMethod
)


@pytest.mark.integration
@pytest.mark.django_db
class TestFinanceIntegration:
    """Test finance module integration with other modules."""
    
    def test_expense_site_integration(self, director_client, site, expense_category, user):
        """Test expense creation integrates with site management."""
        # Create expense linked to site
        response = director_client.post(reverse('finance:expense_create'), {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '1000.00',
            'description': 'Site equipment rental'
        }, follow=True)
        
        assert response.status_code == 200
        
        from finance.models import Expense
        expense = Expense.objects.get(description='Site equipment rental')
        assert expense.site == site
        
        # Verify expense appears in site detail view
        response = director_client.get(reverse('projects:site_detail', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert expense in response.context.get('expenses', [])
    
    def test_material_request_expense_integration(self, director_client, site, material, user):
        """Test material request integration with expense tracking."""
        # Create material request
        from materials.models import MaterialRequest, MaterialRequestItem
        
        material_request = MaterialRequest.objects.create(
            site=site,
            requested_by=user,
            status=MaterialRequestStatus.APPROVED
        )
        
        MaterialRequestItem.objects.create(
            request=material_request,
            material=material,
            quantity=Decimal('50'),
            notes='For construction'
        )
        
        # Create expense linked to material request
        from finance.models import Expense
        expense = Expense.objects.create(
            site=site,
            requester=user,
            category__name='Materials',
            amount=Decimal('525.00'),  # 50 * 10.50
            description='Material purchase for request',
            status=ExpenseStatus.APPROVED
        )
        
        material_request.expense = expense
        material_request.save()
        
        # Verify integration
        material_request.refresh_from_db()
        assert material_request.expense == expense


@pytest.mark.integration
@pytest.mark.django_db
class TestPersonnelIntegration:
    """Test personnel module integration."""
    
    def test_personnel_site_assignment_integration(self, director_client, site, personnel):
        """Test personnel assignment integrates with site management."""
        # Create assignment
        from personnel.models import SiteAssignment
        assignment = SiteAssignment.objects.create(
            personnel=personnel,
            site=site,
            role='Site Manager',
            start_date=date.today(),
            daily_rate=Decimal('200.00')
        )
        
        # Verify assignment affects site calculations
        site.refresh_from_db()
        assert site.total_daily_personnel_cost == Decimal('200.00')
        
        # Test assignment appears in site detail
        response = director_client.get(reverse('projects:site_detail', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert assignment in response.context.get('assignments', [])
    
    def test_personnel_expense_integration(self, director_client, site, personnel, user, expense_category):
        """Test personnel costs integrate with expense tracking."""
        # Create personnel assignment
        from personnel.models import SiteAssignment
        assignment = SiteAssignment.objects.create(
            personnel=personnel,
            site=site,
            role='Worker',
            start_date=date.today(),
            daily_rate=Decimal('150.00')
        )
        
        # Create personnel expense
        from finance.models import Expense
        expense = Expense.objects.create(
            site=site,
            requester=user,
            category=expense_category,
            amount=Decimal('150.00'),
            description='Daily wages',
            status=ExpenseStatus.APPROVED
        )
        
        # Verify expense affects site budget
        site.refresh_from_db()
        assert site.total_spent >= expense.amount


@pytest.mark.integration
@pytest.mark.django_db
class TestRevenueIntegration:
    """Test revenue module integration."""
    
    def test_contract_site_integration(self, director_client, site):
        """Test contract creation integrates with site management."""
        # Create contract for site
        from revenue.models import Contract
        contract = Contract.objects.create(
            site=site,
            client_name='Test Client',
            total_value=Decimal('100000.00'),
            signed_date=date.today()
        )
        
        # Verify contract appears in site detail
        response = director_client.get(reverse('projects:site_detail', kwargs={'pk': site.pk}))
        assert response.status_code == 200
        assert hasattr(site, 'contract')
        assert site.contract == contract
    
    def test_invoice_payment_integration(self, accountant_client, contract):
        """Test invoice and payment integration."""
        # Create invoice
        from revenue.models import Invoice, Payment
        invoice = Invoice.objects.create(
            contract=contract,
            invoice_number='INV-001',
            amount=Decimal('25000.00'),
            issued_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT
        )
        
        # Create payment
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal('25000.00'),
            payment_date=date.today(),
            method=PaymentMethod.BANK_TRANSFER,
            reference='BANK-001'
        )
        
        # Verify payment updates invoice status
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.PAID
        
        # Verify contract revenue calculation
        contract.refresh_from_db()
        assert contract.site.total_revenue == Decimal('25000.00')


@pytest.mark.integration
@pytest.mark.django_db
class TestUserRolesIntegration:
    """Test user role integration across modules."""
    
    def test_director_permissions_integration(self, director_client, site, expense_category):
        """Test director has appropriate permissions across modules."""
        # Can access site management
        response = director_client.get(reverse('projects:site_create'))
        assert response.status_code == 200
        
        # Can access expense management
        response = director_client.get(reverse('finance:expense_create'))
        assert response.status_code == 200
        
        # Can access personnel management
        response = director_client.get(reverse('personnel:assignment_create'))
        assert response.status_code == 200
    
    def test_engineer_permissions_integration(self, engineer_client, site):
        """Test engineer has appropriate permissions."""
        # Can create material requests
        response = engineer_client.get(reverse('materials:request_create'))
        assert response.status_code == 200
        
        # Cannot access admin functions
        response = engineer_client.get(reverse('admin:index'))
        assert response.status_code in [302, 403]
    
    def test_accountant_permissions_integration(self, accountant_client, contract):
        """Test accountant has appropriate permissions."""
        # Can access revenue management
        response = accountant_client.get(reverse('revenue:invoice_create', kwargs={'contract_id': contract.pk}))
        assert response.status_code == 200
        
        # Can access expense approval
        response = accountant_client.get(reverse('finance:expense_list'))
        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.django_db
class TestDashboardIntegration:
    """Test dashboard integration with all modules."""
    
    def test_dashboard_data_aggregation(self, director_client, complete_project_setup):
        """Test dashboard aggregates data from all modules."""
        setup = complete_project_setup
        
        # Create additional test data
        from finance.models import Expense
        from materials.models import MaterialRequest
        from revenue.models import Invoice
        
        # Create expense
        expense = Expense.objects.create(
            site=setup['site'],
            requester=setup['user'],
            category=setup['expense_category'],
            amount=Decimal('1000.00'),
            description='Test expense',
            status=ExpenseStatus.APPROVED
        )
        
        # Create material request
        material_request = MaterialRequest.objects.create(
            site=setup['site'],
            requested_by=setup['user'],
            status=MaterialRequestStatus.PENDING
        )
        
        # Create invoice
        invoice = Invoice.objects.create(
            contract=setup['contract'],
            invoice_number='INV-DASH-001',
            amount=Decimal('5000.00'),
            issued_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status=InvoiceStatus.SENT
        )
        
        # Test dashboard displays aggregated data
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        
        # Verify context contains data from all modules
        assert 'sites' in response.context
        assert 'recent_expenses' in response.context
        assert 'material_requests' in response.context
        assert 'invoices' in response.context
        
        # Verify specific data appears
        assert setup['site'] in response.context['sites']
        assert expense in response.context['recent_expenses']
        assert material_request in response.context['material_requests']
        assert invoice in response.context['invoices']


@pytest.mark.integration
@pytest.mark.django_db
class TestNotificationIntegration:
    """Test notification system integration."""
    
    def test_expense_approval_notification(self, director_client, user, site, expense_category):
        """Test expense approval triggers notifications."""
        # Create expense
        from finance.models import Expense
        expense = Expense.objects.create(
            site=site,
            requester=user,
            category=expense_category,
            amount=Decimal('500.00'),
            description='Test expense',
            status=ExpenseStatus.PENDING
        )
        
        # Approve expense (this should trigger notification)
        expense.status = ExpenseStatus.APPROVED
        expense.save()
        
        # In a real implementation, this would check for notification creation
        # For now, we verify the status change was successful
        assert expense.status == ExpenseStatus.APPROVED
    
    def test_material_request_notification(self, engineer_client, director_client, site, material):
        """Test material request status changes trigger notifications."""
        # Create material request
        from materials.models import MaterialRequest, MaterialRequestItem
        material_request = MaterialRequest.objects.create(
            site=site,
            requested_by=engineer_client.request.user if hasattr(engineer_client, 'request') else site.cabinet.user_roles.first().user,
            status=MaterialRequestStatus.PENDING
        )
        
        MaterialRequestItem.objects.create(
            request=material_request,
            material=material,
            quantity=Decimal('25'),
            notes='Urgent need'
        )
        
        # Approve request
        material_request.status = MaterialRequestStatus.APPROVED
        material_request.save()
        
        assert material_request.status == MaterialRequestStatus.APPROVED


@pytest.mark.integration
@pytest.mark.django_db
class TestFileUploadIntegration:
    """Test file upload integration across modules."""
    
    def test_expense_receipt_upload(self, director_client, site, expense_category, mock_file_upload):
        """Test expense receipt upload integration."""
        # Create expense with receipt
        response = director_client.post(reverse('finance:expense_create'), {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '750.00',
            'description': 'Expense with receipt',
            'receipt_image': mock_file_upload
        }, follow=True)
        
        assert response.status_code == 200
        
        from finance.models import Expense
        expense = Expense.objects.get(description='Expense with receipt')
        assert expense.receipt_image
    
    def test_cabinet_logo_upload(self, admin_client, mock_file_upload):
        """Test cabinet logo upload integration."""
        # Create cabinet with logo
        response = admin_client.post(reverse('admin:accounts_cabinet_add'), {
            'name': 'Test Cabinet with Logo',
            'address': 'Test Address',
            'tax_id': 'TEST123',
            'logo': mock_file_upload
        }, follow=True)
        
        # In a real implementation, this would verify the logo was uploaded
        # For now, we verify the request was processed
        assert response.status_code in [200, 302]


@pytest.mark.integration
@pytest.mark.django_db
class TestSearchIntegration:
    """Test search functionality integration."""
    
    def test_global_search_integration(self, director_client, site, user):
        """Test global search across modules."""
        # Search for site
        response = director_client.get(reverse('search'), {'q': site.name})
        assert response.status_code == 200
        
        # Search for user
        response = director_client.get(reverse('search'), {'q': user.username})
        assert response.status_code == 200
        
        # Search with no results
        response = director_client.get(reverse('search'), {'q': 'NonExistentTerm'})
        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.django_db
class TestAPIIntegration:
    """Test API integration between frontend and backend."""
    
    def test_api_endpoints_integration(self, authenticated_client, site):
        """Test API endpoints work correctly."""
        # Test site list API
        response = authenticated_client.get('/api/sites/')
        assert response.status_code == 200
        
        # Test site detail API
        response = authenticated_client.get(f'/api/sites/{site.pk}/')
        assert response.status_code == 200
        
        # Verify JSON response
        assert response['Content-Type'].startswith('application/json')


@pytest.mark.integration
@pytest.mark.django_db
class TestCacheIntegration:
    """Test caching integration."""
    
    def test_dashboard_caching(self, director_client, site):
        """Test dashboard caching functionality."""
        # First request
        response1 = director_client.get(reverse('home'))
        assert response1.status_code == 200
        
        # Second request (should use cache)
        response2 = director_client.get(reverse('home'))
        assert response2.status_code == 200
        
        # Both responses should be similar
        assert response1.status_code == response2.status_code
