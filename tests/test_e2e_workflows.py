"""
End-to-end tests for ChantierMobile application.
These tests simulate real user workflows and interactions.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from chantiermobile.constants import (
    UserRoles, ApprovalStatus, SiteStatus, ExpenseStatus, 
    MaterialRequestStatus, InvoiceStatus, PaymentMethod
)


@pytest.mark.e2e
@pytest.mark.django_db
class TestAuthenticationWorkflow:
    """Test complete authentication workflow."""
    
    def test_user_registration_and_login(self, client):
        """Test user registration and login workflow."""
        # Test registration page loads
        response = client.get(reverse('account_signup'))
        assert response.status_code == 200
        
        # Test user registration
        registration_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complexpassword123',
            'password2': 'complexpassword123',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = client.post(reverse('account_signup'), registration_data)
        # Should redirect after successful registration
        assert response.status_code in [302, 200]
        
        # Test login with new user
        login_data = {
            'login': 'newuser',
            'password': 'complexpassword123'
        }
        
        response = client.post(reverse('account_login'), login_data)
        assert response.status_code in [302, 200]
    
    def test_login_workflow(self, client, user):
        """Test login workflow with existing user."""
        # Test login page loads
        response = client.get(reverse('account_login'))
        assert response.status_code == 200
        
        # Test successful login
        login_data = {
            'login': 'testuser',
            'password': 'testpass123'
        }
        
        response = client.post(reverse('account_login'), login_data, follow=True)
        assert response.status_code == 200
        # Should be logged in now
        assert response.context['user'].is_authenticated
    
    def test_logout_workflow(self, authenticated_client):
        """Test logout workflow."""
        # User is already authenticated
        response = authenticated_client.get(reverse('home'))
        assert response.context['user'].is_authenticated
        
        # Test logout
        response = authenticated_client.post(reverse('account_logout'), follow=True)
        assert response.status_code == 200
        # Should be logged out
        assert not response.context['user'].is_authenticated


@pytest.mark.e2e
@pytest.mark.django_db
class TestProjectManagementWorkflow:
    """Test complete project management workflow."""
    
    def test_create_site_workflow(self, director_client, cabinet):
        """Test creating a new site from start to finish."""
        # Navigate to site creation
        response = director_client.get(reverse('projects:site_create'))
        assert response.status_code == 200
        
        # Create site
        site_data = {
            'name': 'Construction Site Alpha',
            'location': '123 Main Street, City',
            'status': SiteStatus.PLANNING,
            'start_date': date.today(),
            'expected_end_date': date.today() + timedelta(days=180)
        }
        
        response = director_client.post(reverse('projects:site_create'), site_data, follow=True)
        assert response.status_code == 200
        
        # Verify site was created
        from projects.models import Site
        site = Site.objects.get(name='Construction Site Alpha')
        assert site.location == '123 Main Street, City'
        assert site.cabinet == cabinet
    
    def test_site_lifecycle_workflow(self, director_client, site):
        """Test complete site lifecycle from planning to completion."""
        # Start with planning site
        assert site.status == SiteStatus.PLANNING
        
        # Activate site
        response = director_client.post(
            reverse('projects:site_update', kwargs={'unique_id': site.unique_id}),
            {
                'name': site.name,
                'location': site.location,
                'status': SiteStatus.ACTIVE,
                'start_date': site.start_date,
                'expected_end_date': site.expected_end_date
            },
            follow=True
        )
        assert response.status_code == 200
        
        # Refresh and verify status change
        site.refresh_from_db()
        assert site.status == SiteStatus.ACTIVE
        
        # Add project phase
        response = director_client.get(reverse('projects:phase_create', kwargs={'site_id': site.unique_id}))
        assert response.status_code == 200

        phase_data = {
            'name': 'Foundation Phase',
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=30)
        }

        response = director_client.post(
            reverse('projects:phase_create', kwargs={'site_id': site.unique_id}),
            phase_data,
            follow=True
        )
        assert response.status_code == 200

        # Verify phase was created
        from projects.models import ProjectPhase
        phase = ProjectPhase.objects.get(name='Foundation Phase')
        assert phase.site == site

        # Add progress report
        response = director_client.get(reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id}))
        assert response.status_code == 200

        progress_data = {
            'report_date': date.today(),
            'percentage_complete': 25,
            'description': 'Foundation work started successfully'
        }

        response = director_client.post(
            reverse('projects:progress_create', kwargs={'phase_id': phase.unique_id}),
            progress_data,
            follow=True
        )
        assert response.status_code == 200
        
        # Complete the site
        response = director_client.post(
            reverse('projects:site_update', kwargs={'unique_id': site.unique_id}),
            {
                'name': site.name,
                'location': site.location,
                'status': SiteStatus.COMPLETED,
                'start_date': site.start_date,
                'expected_end_date': site.expected_end_date
            },
            follow=True
        )
        assert response.status_code == 200
        
        site.refresh_from_db()
        assert site.status == SiteStatus.COMPLETED


@pytest.mark.e2e
@pytest.mark.django_db
class TestExpenseManagementWorkflow:
    """Test complete expense management workflow."""
    
    def test_expense_approval_workflow(self, director_client, accountant_client, site, user, expense_category):
        """Test expense creation and approval workflow."""
        # Employee creates expense
        response = director_client.get(reverse('finance:expense_create'))
        assert response.status_code == 200
        
        expense_data = {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '1500.75',
            'expense_date': date.today(),
            'description': 'Construction materials purchase'
        }
        
        response = director_client.post(reverse('finance:expense_create'), expense_data, follow=True)
        assert response.status_code == 200
        
        # Verify expense was created
        from finance.models import Expense
        expense = Expense.objects.get(description='Construction materials purchase')
        assert expense.status == ExpenseStatus.PENDING
        assert expense.amount == Decimal('1500.75')
        
        # Director reviews and approves expense
        response = director_client.get(reverse('finance:expense_detail', kwargs={'pk': expense.pk}))
        assert response.status_code == 200
        
        # Approve expense (this would typically be a POST to an approval endpoint)
        expense.status = ExpenseStatus.APPROVED
        expense.save()
        
        # Accountant processes payment
        response = accountant_client.get(reverse('finance:expense_detail', kwargs={'pk': expense.pk}))
        assert response.status_code == 200
        
        # Mark as paid
        expense.status = ExpenseStatus.PAID
        expense.save()
        
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.PAID
    
    def test_expense_rejection_workflow(self, director_client, site, user, expense_category):
        """Test expense rejection workflow."""
        # Create expense
        response = director_client.post(reverse('finance:expense_create'), {
            'site': site.pk,
            'category': expense_category.pk,
            'amount': '5000.00',
            'expense_date': date.today(),
            'description': 'Unreasonable expense request'
        }, follow=True)
        
        from finance.models import Expense
        expense = Expense.objects.get(description='Unreasonable expense request')
        
        # Director rejects expense
        expense.status = ExpenseStatus.REJECTED
        expense.save()
        
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.REJECTED


@pytest.mark.e2e
@pytest.mark.django_db
class TestMaterialRequestWorkflow:
    """Test complete material request workflow."""
    
    def test_material_request_lifecycle(self, engineer_client, director_client, site, material):
        """Test material request from creation to delivery."""
        # Engineer creates material request
        response = engineer_client.get(reverse('materials:request_create'))
        assert response.status_code == 200
        
        request_data = {
            'site': site.pk,
            'notes': 'Materials needed for foundation work',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-material': material.pk,
            'items-0-quantity': '100',
            'items-0-notes': 'For foundation concrete',
        }

        response = engineer_client.post(reverse('materials:request_create'), request_data, follow=True)
        assert response.status_code == 200
        
        # Verify request was created, with its item (submitted via the items formset above)
        from materials.models import MaterialRequest
        material_request = MaterialRequest.objects.get(notes='Materials needed for foundation work')
        assert material_request.status == MaterialRequestStatus.PENDING
        assert material_request.items.filter(material=material).exists()

        # Director approves request
        response = director_client.get(reverse('materials:request_detail', kwargs={'pk': material_request.pk}))
        assert response.status_code == 200
        
        material_request.status = MaterialRequestStatus.APPROVED
        material_request.save()
        
        # Mark as ordered
        material_request.status = MaterialRequestStatus.ORDERED
        material_request.save()
        
        # Mark as delivered
        material_request.status = MaterialRequestStatus.DELIVERED
        material_request.save()
        
        material_request.refresh_from_db()
        assert material_request.status == MaterialRequestStatus.DELIVERED


@pytest.mark.e2e
@pytest.mark.django_db
class TestRevenueManagementWorkflow:
    """Test complete revenue management workflow."""
    
    def test_invoice_creation_and_payment_workflow(self, accountant_client, site, contract):
        """Test invoice creation and payment workflow."""
        # Create invoice
        response = accountant_client.get(reverse('revenue:invoice_create_from_contract', kwargs={'contract_id': contract.pk}))
        assert response.status_code == 200
        
        invoice_data = {
            'contract': contract.pk,
            'invoice_number': 'INV-2024-001',
            'amount': '25000.00',
            'issued_date': date.today(),
            'due_date': date.today() + timedelta(days=30),
            'status': InvoiceStatus.SENT
        }
        
        response = accountant_client.post(
            reverse('revenue:invoice_create_from_contract', kwargs={'contract_id': contract.pk}),
            invoice_data,
            follow=True
        )
        assert response.status_code == 200
        
        # Verify invoice was created
        from revenue.models import Invoice
        invoice = Invoice.objects.get(invoice_number='INV-2024-001')
        assert invoice.amount == Decimal('25000.00')
        assert invoice.status == InvoiceStatus.SENT
        
        # Record payment
        response = accountant_client.get(reverse('revenue:payment_create', kwargs={'invoice_id': invoice.pk}))
        assert response.status_code == 200
        
        payment_data = {
            'invoice': invoice.pk,
            'amount': '25000.00',
            'payment_date': date.today(),
            'method': PaymentMethod.BANK_TRANSFER,
            'reference': 'BANK-REF-001'
        }
        
        response = accountant_client.post(reverse('revenue:payment_create', kwargs={'invoice_id': invoice.pk}), payment_data, follow=True)
        assert response.status_code == 200
        
        # Verify payment was created and invoice status updated
        from revenue.models import Payment
        payment = Payment.objects.get(reference='BANK-REF-001')
        assert payment.amount == Decimal('25000.00')
        
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.PAID


@pytest.mark.e2e
@pytest.mark.django_db
class TestPersonnelManagementWorkflow:
    """Test complete personnel management workflow."""
    
    def test_personnel_assignment_workflow(self, director_client, site):
        """Test personnel assignment and management workflow."""
        # Create personnel
        from personnel.models import Personnel
        personnel = Personnel.objects.create(
            cabinet=site.cabinet,
            first_name='John',
            last_name='Worker',
            default_daily_rate=Decimal('150.00')
        )
        
        # Assign personnel to site
        response = director_client.get(reverse('personnel:assignment_create'))
        assert response.status_code == 200
        
        assignment_data = {
            'personnel': personnel.pk,
            'site': site.pk,
            'role': 'Site Supervisor',
            'start_date': date.today(),
            'daily_rate': '160.00'
        }
        
        response = director_client.post(reverse('personnel:assignment_create'), assignment_data, follow=True)
        assert response.status_code == 200
        
        # Verify assignment was created
        from personnel.models import SiteAssignment
        assignment = SiteAssignment.objects.get(personnel=personnel, site=site)
        assert assignment.role == 'Site Supervisor'
        assert assignment.daily_rate == Decimal('160.00')


@pytest.mark.e2e
@pytest.mark.django_db
class TestInternationalizationWorkflow:
    """Test internationalization workflow."""
    
    def test_language_switching_workflow(self, authenticated_client):
        """Test language switching functionality."""
        # Test default language (French)
        response = authenticated_client.get(reverse('home'))
        assert response.status_code == 200

        # Switch to English
        response = authenticated_client.post(reverse('set_language'), {'language': 'en'}, follow=True)
        assert response.status_code == 200

        # Switch back to French
        response = authenticated_client.post(reverse('set_language'), {'language': 'fr'}, follow=True)
        assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.django_db
class TestDashboardWorkflow:
    """Test dashboard functionality and data display."""
    
    def test_dashboard_data_display(self, director_client, complete_project_setup):
        """Test dashboard displays correct data."""
        setup = complete_project_setup
        
        # Access dashboard
        response = director_client.get(reverse('home'))
        assert response.status_code == 200
        
        # Verify dashboard contains expected data (core/dashboard.py::build_dashboard_context)
        assert 'revenue_all' in response.context
        assert 'expense_all' in response.context
        assert 'pending_expenses_count' in response.context
        assert 'total_sites_count' in response.context
        assert response.context['total_sites_count'] >= 1


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.django_db
class TestPerformanceWorkflow:
    """Test application performance under load."""
    
    @pytest.mark.django_db(transaction=True)
    def test_multiple_concurrent_requests(self, director_client, site):
        """Test handling multiple concurrent requests.

        Needs transaction=True: worker threads open their own DB connections,
        which can't see rows from the default django_db fixture's uncommitted
        atomic() wrapper — only a real commit (transactional_db) is visible
        across threads/connections. Needs director_client specifically:
        authenticated_client's user has no UserCabinetRole, so
        CabinetAccessMixin would 404 it against any site regardless of
        threading.
        """
        import threading
        import time

        results = []

        def make_request():
            response = director_client.get(reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}))
            results.append(response.status_code)
        
        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 10


@pytest.mark.e2e
@pytest.mark.django_db
class TestErrorHandlingWorkflow:
    """Test error handling and user experience."""
    
    def test_404_error_handling(self, client):
        """Test 404 error page."""
        response = client.get('/nonexistent-page/')
        assert response.status_code == 404
        
    def test_permission_denied_handling(self, authenticated_client, site):
        """Test permission denied handling."""
        # Try to access admin-only endpoint as regular user
        response = authenticated_client.get(reverse('admin:index'))
        # Should redirect to login or show permission denied
        assert response.status_code in [302, 403]
    
    def test_form_validation_errors(self, director_client):
        """Test form validation error handling."""
        # Try to create site with invalid data
        response = director_client.post(reverse('projects:site_create'), {
            'name': '',  # Empty name should cause validation error
            'location': 'Test Location',
            'status': SiteStatus.PLANNING
        })
        
        # Should return form with errors
        assert response.status_code == 200
        assert 'form' in response.context
