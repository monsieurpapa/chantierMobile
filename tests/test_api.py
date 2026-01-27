"""
API tests for ChantierMobile application.
"""

import pytest
from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

from chantiermobile.constants import SiteStatus, ExpenseStatus


@pytest.mark.api
@pytest.mark.django_db
class TestSiteAPI:
    """Test Site API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.DIRECTOR)
        self.client.force_authenticate(user=self.user)
    
    def test_list_sites(self):
        """Test GET /api/sites/"""
        site = SiteFactory(cabinet=self.cabinet)
        response = self.client.get('/api/sites/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert response.data[0]['name'] == site.name
    
    def test_create_site(self):
        """Test POST /api/sites/"""
        data = {
            'name': 'API Test Site',
            'location': 'Test Location',
            'status': SiteStatus.PLANNING,
            'start_date': '2024-01-15',
            'expected_end_date': '2024-06-15'
        }
        
        response = self.client.post('/api/sites/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'API Test Site'
    
    def test_retrieve_site(self):
        """Test GET /api/sites/{id}/"""
        site = SiteFactory(cabinet=self.cabinet)
        response = self.client.get(f'/api/sites/{site.pk}/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == site.name
    
    def test_update_site(self):
        """Test PUT /api/sites/{id}/"""
        site = SiteFactory(cabinet=self.cabinet)
        data = {
            'name': 'Updated Site Name',
            'location': site.location,
            'status': SiteStatus.ACTIVE,
            'start_date': site.start_date.isoformat(),
            'expected_end_date': site.expected_end_date.isoformat()
        }
        
        response = self.client.put(f'/api/sites/{site.pk}/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Updated Site Name'
    
    def test_delete_site(self):
        """Test DELETE /api/sites/{id}/"""
        site = SiteFactory(cabinet=self.cabinet)
        response = self.client.delete(f'/api/sites/{site.pk}/')
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
    
    def test_site_permissions(self):
        """Test site API permissions."""
        # Test unauthorized access
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/sites/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        # Test user without cabinet access
        other_user = UserFactory()
        self.client.force_authenticate(user=other_user)
        response = self.client.get('/api/sites/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0


@pytest.mark.api
@pytest.mark.django_db
class TestExpenseAPI:
    """Test Expense API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        self.site = SiteFactory(cabinet=self.cabinet)
        self.category = ExpenseCategoryFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.ENGINEER)
        self.client.force_authenticate(user=self.user)
    
    def test_list_expenses(self):
        """Test GET /api/expenses/"""
        expense = ExpenseFactory(site=self.site, requester=self.user, category=self.category)
        response = self.client.get('/api/expenses/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert response.data[0]['amount'] == str(expense.amount)
    
    def test_create_expense(self):
        """Test POST /api/expenses/"""
        data = {
            'site': self.site.pk,
            'category': self.category.pk,
            'amount': '1500.00',
            'description': 'API Test Expense'
        }
        
        response = self.client.post('/api/expenses/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['amount'] == '1500.00'
    
    def test_approve_expense(self):
        """Test POST /api/expenses/{id}/approve/"""
        expense = ExpenseFactory(site=self.site, requester=self.user, category=self.category)
        
        response = self.client.post(f'/api/expenses/{expense.pk}/approve/')
        assert response.status_code == status.HTTP_200_OK
        
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.APPROVED
    
    def test_reject_expense(self):
        """Test POST /api/expenses/{id}/reject/"""
        expense = ExpenseFactory(site=self.site, requester=self.user, category=self.category)
        
        response = self.client.post(f'/api/expenses/{expense.pk}/reject/')
        assert response.status_code == status.HTTP_200_OK
        
        expense.refresh_from_db()
        assert expense.status == ExpenseStatus.REJECTED


@pytest.mark.api
@pytest.mark.django_db
class TestMaterialRequestAPI:
    """Test MaterialRequest API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        self.site = SiteFactory(cabinet=self.cabinet)
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.ENGINEER)
        self.client.force_authenticate(user=self.user)
    
    def test_list_material_requests(self):
        """Test GET /api/material-requests/"""
        request = MaterialRequestFactory(site=self.site, requested_by=self.user)
        response = self.client.get('/api/material-requests/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
    
    def test_create_material_request(self):
        """Test POST /api/material-requests/"""
        data = {
            'site': self.site.pk,
            'notes': 'API Test Request'
        }
        
        response = self.client.post('/api/material-requests/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['notes'] == 'API Test Request'
    
    def test_add_material_item(self):
        """Test POST /api/material-requests/{id}/add-item/"""
        material_request = MaterialRequestFactory(site=self.site, requested_by=self.user)
        material = MaterialFactory()
        
        data = {
            'material': material.pk,
            'quantity': '25.5',
            'notes': 'Test item'
        }
        
        response = self.client.post(f'/api/material-requests/{material_request.pk}/add-item/', data)
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.api
@pytest.mark.django_db
class TestPersonnelAPI:
    """Test Personnel API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.DIRECTOR)
        self.client.force_authenticate(user=self.user)
    
    def test_list_personnel(self):
        """Test GET /api/personnel/"""
        personnel = PersonnelFactory()
        response = self.client.get('/api/personnel/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
    
    def test_create_personnel(self):
        """Test POST /api/personnel/"""
        data = {
            'first_name': 'API',
            'last_name': 'Person',
            'default_daily_rate': '200.00'
        }
        
        response = self.client.post('/api/personnel/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['first_name'] == 'API'
    
    def test_create_assignment(self):
        """Test POST /api/personnel/{id}/assign/"""
        personnel = PersonnelFactory()
        site = SiteFactory(cabinet=self.cabinet)
        
        data = {
            'site': site.pk,
            'role': 'Site Manager',
            'start_date': '2024-01-15',
            'daily_rate': '250.00'
        }
        
        response = self.client.post(f'/api/personnel/{personnel.pk}/assign/', data)
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.api
@pytest.mark.django_db
class TestRevenueAPI:
    """Test Revenue API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        self.site = SiteFactory(cabinet=self.cabinet)
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.ACCOUNTANT)
        self.client.force_authenticate(user=self.user)
    
    def test_list_contracts(self):
        """Test GET /api/contracts/"""
        contract = ContractFactory(site=self.site)
        response = self.client.get('/api/contracts/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
    
    def test_create_contract(self):
        """Test POST /api/contracts/"""
        data = {
            'site': self.site.pk,
            'client_name': 'API Client',
            'total_value': '100000.00',
            'signed_date': '2024-01-15'
        }
        
        response = self.client.post('/api/contracts/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['client_name'] == 'API Client'
    
    def test_list_invoices(self):
        """Test GET /api/invoices/"""
        contract = ContractFactory(site=self.site)
        invoice = InvoiceFactory(contract=contract)
        response = self.client.get('/api/invoices/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
    
    def test_create_payment(self):
        """Test POST /api/invoices/{id}/pay/"""
        contract = ContractFactory(site=self.site)
        invoice = InvoiceFactory(contract=contract)
        
        data = {
            'amount': '5000.00',
            'payment_date': '2024-01-15',
            'method': PaymentMethod.BANK_TRANSFER,
            'reference': 'API-PAY-001'
        }
        
        response = self.client.post(f'/api/invoices/{invoice.pk}/pay/', data)
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.api
@pytest.mark.django_db
class TestSearchAPI:
    """Test Search API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.ENGINEER)
        self.client.force_authenticate(user=self.user)
    
    def test_search_sites(self):
        """Test GET /api/search/?q=term&type=sites"""
        site = SiteFactory(cabinet=self.cabinet, name='Special Project Site')
        response = self.client.get('/api/search/?q=Special&type=sites')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['sites']) >= 1
        assert response.data['sites'][0]['name'] == 'Special Project Site'
    
    def test_search_expenses(self):
        """Test GET /api/search/?q=term&type=expenses"""
        expense = ExpenseFactory(description='Special equipment purchase')
        response = self.client.get('/api/search/?q=Special&type=expenses')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['expenses']) >= 1
    
    def test_global_search(self):
        """Test GET /api/search/?q=term"""
        site = SiteFactory(cabinet=self.cabinet, name='Test Site')
        expense = ExpenseFactory(description='Test expense')
        
        response = self.client.get('/api/search/?q=Test')
        assert response.status_code == status.HTTP_200_OK
        assert 'sites' in response.data
        assert 'expenses' in response.data


@pytest.mark.api
@pytest.mark.django_db
class TestDashboardAPI:
    """Test Dashboard API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.DIRECTOR)
        self.client.force_authenticate(user=self.user)
    
    def test_dashboard_stats(self):
        """Test GET /api/dashboard/stats/"""
        site = SiteFactory(cabinet=self.cabinet)
        expense = ExpenseFactory(site=site)
        
        response = self.client.get('/api/dashboard/stats/')
        assert response.status_code == status.HTTP_200_OK
        
        assert 'sites_count' in response.data
        assert 'expenses_count' in response.data
        assert 'total_expenses' in response.data
        assert 'recent_activities' in response.data
    
    def test_dashboard_charts(self):
        """Test GET /api/dashboard/charts/"""
        response = self.client.get('/api/dashboard/charts/')
        assert response.status_code == status.HTTP_200_OK
        
        assert 'expenses_by_category' in response.data
        assert 'sites_by_status' in response.data
        assert 'monthly_expenses' in response.data


@pytest.mark.api
@pytest.mark.django_db
class TestFileUploadAPI:
    """Test File Upload API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.cabinet = CabinetFactory()
        UserCabinetRoleFactory(user=self.user, cabinet=self.cabinet, role=UserRoles.ENGINEER)
        self.client.force_authenticate(user=self.user)
    
    def test_upload_expense_receipt(self):
        """Test POST /api/expenses/{id}/upload-receipt/"""
        expense = ExpenseFactory()
        
        # Create test file
        from django.core.files.uploadedfile import SimpleUploadedFile
        test_file = SimpleUploadedFile(
            "receipt.jpg",
            b"file_content",
            content_type="image/jpeg"
        )
        
        response = self.client.post(
            f'/api/expenses/{expense.pk}/upload-receipt/',
            {'receipt_image': test_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_200_OK
        expense.refresh_from_db()
        assert expense.receipt_image


@pytest.mark.api
@pytest.mark.django_db
class TestAuthenticationAPI:
    """Test Authentication API endpoints."""
    
    def test_login_api(self):
        """Test POST /api/auth/login/"""
        user = UserFactory()
        
        response = self.client.post('/api/auth/login/', {
            'username': user.username,
            'password': 'password'  # Default password from factory
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access_token' in response.data
        assert 'refresh_token' in response.data
    
    def test_logout_api(self):
        """Test POST /api/auth/logout/"""
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        response = self.client.post('/api/auth/logout/')
        assert response.status_code == status.HTTP_200_OK
    
    def test_user_profile_api(self):
        """Test GET /api/auth/profile/"""
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        response = self.client.get('/api/auth/profile/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == user.username
