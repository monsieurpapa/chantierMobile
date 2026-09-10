"""
Test configuration and shared fixtures for ChantierMobile project.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
import tempfile
import shutil
import os

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import UserRoles, ApprovalStatus, SiteStatus, ExpenseStatus, MaterialRequestStatus, InvoiceStatus

User = get_user_model()


@pytest.fixture(scope='session')
def django_db_setup():
    """Setup database for all tests."""
    pass


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def temp_media_root():
    """Temporary media directory for file uploads."""
    temp_dir = tempfile.mkdtemp()
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def superuser(db):
    """Create a superuser for testing."""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='testpass123'
    )


@pytest.fixture
def user(db):
    """Create a regular user for testing."""
    return User.objects.create_user(
        username='testuser',
        email='user@example.com',
        password='testpass123',
        first_name='John',
        last_name='Doe'
    )


@pytest.fixture
def cabinet(db):
    """Create a test cabinet."""
    return Cabinet.objects.create(
        name='Test Cabinet',
        address='123 Test Street',
        tax_id='TEST123'
    )


@pytest.fixture
def user_cabinet_role(db, user, cabinet):
    """Create a user cabinet role assignment."""
    return UserCabinetRole.objects.create(
        user=user,
        cabinet=cabinet,
        role=UserRoles.DIRECTOR,
        status=ApprovalStatus.APPROVED
    )


@pytest.fixture
def engineer_user(db, cabinet):
    """Create an engineer user."""
    user = User.objects.create_user(
        username='engineer',
        email='engineer@example.com',
        password='testpass123',
        first_name='Jane',
        last_name='Smith'
    )
    UserCabinetRole.objects.create(
        user=user,
        cabinet=cabinet,
        role=UserRoles.ENGINEER,
        status=ApprovalStatus.APPROVED
    )
    return user


@pytest.fixture
def accountant_user(db, cabinet):
    """Create an accountant user."""
    user = User.objects.create_user(
        username='accountant',
        email='accountant@example.com',
        password='testpass123',
        first_name='Bob',
        last_name='Johnson'
    )
    UserCabinetRole.objects.create(
        user=user,
        cabinet=cabinet,
        role=UserRoles.ACCOUNTANT,
        status=ApprovalStatus.APPROVED
    )
    return user


@pytest.fixture
def director_user(db, cabinet):
    """Create a director user."""
    user = User.objects.create_user(
        username='director',
        email='director@example.com',
        password='testpass123',
        first_name='Director',
        last_name='Name'
    )
    UserCabinetRole.objects.create(
        user=user,
        cabinet=cabinet,
        role=UserRoles.DIRECTOR,
        status=ApprovalStatus.APPROVED
    )
    return user


@pytest.fixture
def authenticated_client(client, user):
    """Authenticated client with regular user."""
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def director_client(client, user, user_cabinet_role):
    """Authenticated client with director role."""
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def engineer_client(client, engineer_user):
    """Authenticated client with engineer role."""
    client.login(username='engineer', password='testpass123')
    return client


@pytest.fixture
def accountant_client(client, accountant_user):
    """Authenticated client with accountant role."""
    client.login(username='accountant', password='testpass123')
    return client


@pytest.fixture
def admin_client(client, superuser):
    """Authenticated client with superuser."""
    client.login(username='admin', password='testpass123')
    return client


@pytest.fixture
def sample_date():
    """Sample date for testing."""
    return date(2024, 1, 15)


@pytest.fixture
def future_date():
    """Future date for testing."""
    return date.today() + timedelta(days=30)


@pytest.fixture
def past_date():
    """Past date for testing."""
    return date.today() - timedelta(days=30)


@pytest.fixture
def sample_amount():
    """Sample monetary amount for testing."""
    return Decimal('1000.50')


@pytest.fixture
def sample_image_file():
    """Sample image file for testing."""
    import io
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    image = Image.new('RGB', (100, 100), 'red')
    image_io = io.BytesIO()
    image.save(image_io, 'JPEG')
    image_io.seek(0)

    return SimpleUploadedFile(
        "test_image.jpg",
        image_io.getvalue(),
        content_type="image/jpeg"
    )


@pytest.fixture
def mock_file_upload():
    """Mock image upload for testing — used against ImageField fields
    (Expense.receipt_image, Cabinet.logo), which run Pillow validation
    and reject non-image content."""
    import io
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    buffer = io.BytesIO()
    Image.new('RGB', (1, 1), color='white').save(buffer, format='PNG')
    return SimpleUploadedFile(
        "test_file.png",
        buffer.getvalue(),
        content_type="image/png"
    )


@pytest.fixture
def mock_email_backend():
    """Mock email backend for testing."""
    from django.core import mail
    mail.outbox = []
    return mail.outbox


@pytest.fixture
def freeze_time():
    """Freeze time for consistent testing."""
    from freezegun import freeze_time
    return freeze_time("2024-01-15 10:00:00")


# Model Fixtures
@pytest.fixture
def site_factory(db, cabinet):
    """Factory for creating Site objects."""
    from projects.models import Site
    
    def create_site(**kwargs):
        defaults = {
            'name': 'Test Site',
            'location': 'Test Location',
            'status': SiteStatus.PLANNING,
            'start_date': date.today(),
            'expected_end_date': date.today() + timedelta(days=90),
            'cabinet': cabinet
        }
        defaults.update(kwargs)
        return Site.objects.create(**defaults)
    
    return create_site


@pytest.fixture
def site(db, site_factory):
    """Create a test site."""
    return site_factory()


@pytest.fixture
def active_site(db, site_factory):
    """Create an active test site."""
    return site_factory(status=SiteStatus.ACTIVE)


@pytest.fixture
def expense_category_factory(db):
    """Factory for creating ExpenseCategory objects."""
    from finance.models import ExpenseCategory
    
    def create_category(**kwargs):
        defaults = {
            'name': 'Test Category',
            'description': 'Test category description'
        }
        defaults.update(kwargs)
        return ExpenseCategory.objects.create(**defaults)
    
    return create_category


@pytest.fixture
def expense_category(db, expense_category_factory):
    """Create a test expense category."""
    return expense_category_factory()


@pytest.fixture
def expense_factory(db, site, user, expense_category):
    """Factory for creating Expense objects."""
    from finance.models import Expense
    
    def create_expense(**kwargs):
        defaults = {
            'site': site,
            'requester': user,
            'category': expense_category,
            'amount': Decimal('500.00'),
            'expense_date': date.today(),
            'description': 'Test expense',
            'status': ExpenseStatus.PENDING
        }
        defaults.update(kwargs)
        return Expense.objects.create(**defaults)
    
    return create_expense


@pytest.fixture
def expense(db, expense_factory):
    """Create a test expense."""
    return expense_factory()


@pytest.fixture
def material_factory(db):
    """Factory for creating Material objects."""
    from materials.models import Material
    
    def create_material(**kwargs):
        defaults = {
            'name': 'Test Material',
            'unit': 'kg',
            'estimated_cost_per_unit': Decimal('10.50')
        }
        defaults.update(kwargs)
        return Material.objects.create(**defaults)
    
    return create_material


@pytest.fixture
def material(db, material_factory):
    """Create a test material."""
    return material_factory()


@pytest.fixture
def material_request_factory(db, site, user):
    """Factory for creating MaterialRequest objects."""
    from materials.models import MaterialRequest
    
    def create_material_request(**kwargs):
        defaults = {
            'site': site,
            'requested_by': user,
            'status': MaterialRequestStatus.PENDING,
            'notes': 'Test material request'
        }
        defaults.update(kwargs)
        return MaterialRequest.objects.create(**defaults)
    
    return create_material_request


@pytest.fixture
def material_request(db, material_request_factory):
    """Create a test material request."""
    return material_request_factory()


@pytest.fixture
def personnel_factory(db, cabinet):
    """Factory for creating Personnel objects."""
    from personnel.models import Personnel
    
    def create_personnel(**kwargs):
        defaults = {
            'cabinet': cabinet,
            'first_name': 'Test',
            'last_name': 'Person',
            'default_daily_rate': Decimal('100.00')
        }
        defaults.update(kwargs)
        return Personnel.objects.create(**defaults)
    
    return create_personnel


@pytest.fixture
def personnel(db, personnel_factory):
    """Create a test personnel."""
    return personnel_factory()


@pytest.fixture
def contract_factory(db, site):
    """Factory for creating Contract objects."""
    from revenue.models import Contract
    
    def create_contract(**kwargs):
        defaults = {
            'site': site,
            'client_name': 'Test Client',
            'total_value': Decimal('50000.00'),
            'signed_date': date.today()
        }
        defaults.update(kwargs)
        return Contract.objects.create(**defaults)
    
    return create_contract


@pytest.fixture
def contract(db, contract_factory):
    """Create a test contract."""
    return contract_factory()


@pytest.fixture
def invoice_factory(db, contract):
    """Factory for creating Invoice objects."""
    from revenue.models import Invoice
    
    def create_invoice(**kwargs):
        defaults = {
            'contract': contract,
            'invoice_number': 'INV-001',
            'amount': Decimal('10000.00'),
            'issued_date': date.today(),
            'due_date': date.today() + timedelta(days=30),
            'status': InvoiceStatus.DRAFT
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)
    
    return create_invoice


@pytest.fixture
def invoice(db, invoice_factory):
    """Create a test invoice."""
    return invoice_factory()


# Helper fixtures for common test scenarios
@pytest.fixture
def complete_project_setup(db, cabinet, site, user, user_cabinet_role, expense_category, material, personnel):
    """Complete project setup with all related objects."""
    return {
        'cabinet': cabinet,
        'site': site,
        'user': user,
        'user_cabinet_role': user_cabinet_role,
        'expense_category': expense_category,
        'material': material,
        'personnel': personnel
    }


@pytest.fixture
def mock_redis():
    """Mock Redis for testing."""
    import fakeredis
    return fakeredis.FakeRedis()


@pytest.fixture
def mock_celery():
    """Mock Celery for testing."""
    with patch('celery.app.task.Task.apply_async') as mock_apply:
        mock_apply.return_value = Mock(id='test-task-id')
        yield mock_apply
