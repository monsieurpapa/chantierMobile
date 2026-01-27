"""
Test utilities and helper functions.
"""

import pytest
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil
import os
import json

from tests.factories import *


class CustomAssertions:
    """Custom assertion methods for testing."""
    
    @staticmethod
    def assert_status_in(response, expected_statuses):
        """Assert response status is in expected list."""
        assert response.status_code in expected_statuses, \
            f"Expected status {expected_statuses}, got {response.status_code}"
    
    @staticmethod
    def assert_json_response(response, expected_data=None):
        """Assert response is valid JSON."""
        assert response['Content-Type'].startswith('application/json'), \
            f"Expected JSON response, got {response['Content-Type']}"
        
        if expected_data:
            response_data = json.loads(response.content)
            assert response_data == expected_data
    
    @staticmethod
    def assert_template_used(response, template_name):
        """Assert specific template was used."""
        assert template_name in [t.name for t in response.templates], \
            f"Template '{template_name}' not used in response"
    
    @staticmethod
    def assert_context_contains(response, *keys):
        """Assert response context contains specific keys."""
        for key in keys:
            assert key in response.context, f"Context key '{key}' not found"
    
    @staticmethod
    def assert_queryset_contains(queryset, obj):
        """Assert queryset contains specific object."""
        assert obj in queryset, f"Object {obj} not found in queryset"
    
    @staticmethod
    def assert_queryset_length(queryset, expected_length):
        """Assert queryset has expected length."""
        assert len(queryset) == expected_length, \
            f"Expected queryset length {expected_length}, got {len(queryset)}"


class TestDataMixin:
    """Mixin providing test data creation methods."""
    
    def create_test_user(self, **kwargs):
        """Create a test user with default values."""
        defaults = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123',
            'first_name': 'Test',
            'last_name': 'User'
        }
        defaults.update(kwargs)
        return UserFactory(**defaults)
    
    def create_test_cabinet(self, **kwargs):
        """Create a test cabinet."""
        defaults = {
            'name': 'Test Cabinet',
            'address': '123 Test Street',
            'tax_id': 'TEST123'
        }
        defaults.update(kwargs)
        return CabinetFactory(**defaults)
    
    def create_user_with_role(self, role=UserRoles.ENGINEER, **kwargs):
        """Create user with specific cabinet role."""
        user = self.create_test_user(**kwargs)
        cabinet = self.create_test_cabinet()
        
        UserCabinetRoleFactory(
            user=user,
            cabinet=cabinet,
            role=role,
            status=ApprovalStatus.APPROVED
        )
        
        return user, cabinet
    
    def create_complete_project(self, **kwargs):
        """Create a complete project with all related objects."""
        return CompleteProjectFactory.create_project_with_all_components()


class AuthenticationMixin:
    """Mixin providing authentication helper methods."""
    
    def login_user(self, client, user=None):
        """Login user to client."""
        if user is None:
            user = self.create_test_user()
        
        client.login(username=user.username, password='testpass123')
        return client
    
    def login_director(self, client):
        """Login director user."""
        user, cabinet = self.create_user_with_role(role=UserRoles.DIRECTOR)
        return self.login_user(client, user)
    
    def login_engineer(self, client):
        """Login engineer user."""
        user, cabinet = self.create_user_with_role(role=UserRoles.ENGINEER)
        return self.login_user(client, user)
    
    def login_accountant(self, client):
        """Login accountant user."""
        user, cabinet = self.create_user_with_role(role=UserRoles.ACCOUNTANT)
        return self.login_user(client, user)


class FileUploadMixin:
    """Mixin providing file upload helper methods."""
    
    def create_test_image(self, filename='test.jpg', size=(100, 100)):
        """Create a test image file."""
        from PIL import Image
        import io
        
        image = Image.new('RGB', size, 'red')
        image_io = io.BytesIO()
        image.save(image_io, 'JPEG')
        image_io.seek(0)
        
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(
            filename,
            image_io.getvalue(),
            content_type="image/jpeg"
        )
    
    def create_test_file(self, filename='test.txt', content=b'test content'):
        """Create a test file."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(
            filename,
            content,
            content_type="text/plain"
        )


class DateTimeMixin:
    """Mixin providing date/time helper methods."""
    
    @staticmethod
    def get_date_days_ago(days):
        """Get date N days ago."""
        return date.today() - timedelta(days=days)
    
    @staticmethod
    def get_date_days_from_now(days):
        """Get date N days from now."""
        return date.today() + timedelta(days=days)
    
    @staticmethod
    def get_date_range(start_days_ago, end_days_from_now):
        """Get date range."""
        start_date = DateTimeMixin.get_date_days_ago(start_days_ago)
        end_date = DateTimeMixin.get_date_days_from_now(end_days_from_now)
        return start_date, end_date


class MockMixin:
    """Mixin providing mock helper methods."""
    
    def mock_email_backend(self):
        """Mock email backend."""
        with patch('django.core.mail.backends.locmem.EmailBackend') as mock_backend:
            mock_backend.return_value.send_messages.return_value = 1
            yield mock_backend
    
    def mock_file_storage(self):
        """Mock file storage."""
        with patch('django.core.files.storage.FileSystemStorage') as mock_storage:
            mock_storage.return_value.save.return_value = 'test_file.jpg'
            mock_storage.return_value.url.return_value = '/media/test_file.jpg'
            yield mock_storage
    
    def mock_celery_task(self):
        """Mock Celery task."""
        with patch('celery.app.task.Task.apply_async') as mock_apply:
            mock_apply.return_value = Mock(id='test-task-id')
            yield mock_apply
    
    def mock_external_api(self, url_pattern, response_data):
        """Mock external API call."""
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = response_data
            mock_get.return_value.status_code = 200
            yield mock_get


class PermissionMixin:
    """Mixin providing permission testing helpers."""
    
    def assert_user_can_access(self, client, url, user=None):
        """Assert user can access URL."""
        if user:
            client.login(username=user.username, password='testpass123')
        
        response = client.get(url)
        assert response.status_code in [200, 302], \
            f"User should be able to access {url}, got {response.status_code}"
    
    def assert_user_cannot_access(self, client, url, user=None):
        """Assert user cannot access URL."""
        if user:
            client.login(username=user.username, password='testpass123')
        
        response = client.get(url)
        assert response.status_code in [403, 404, 302], \
            f"User should not be able to access {url}, got {response.status_code}"
    
    def assert_role_permissions(self, client, url, role_permissions):
        """Test permissions for different user roles."""
        for role, should_access in role_permissions.items():
            user, _ = self.create_user_with_role(role=role)
            
            if should_access:
                self.assert_user_can_access(client, url, user)
            else:
                self.assert_user_cannot_access(client, url, user)


class ValidationMixin:
    """Mixin providing validation testing helpers."""
    
    def assert_form_field_invalid(self, form_data, field_name):
        """Assert form field is invalid."""
        from finance.forms import ExpenseForm  # Example form
        
        form = ExpenseForm(data=form_data)
        assert not form.is_valid(), f"Form should be invalid with {field_name}"
        assert field_name in form.errors, f"Field '{field_name}' should have errors"
    
    def assert_model_validation_error(self, model_data, model_class):
        """Assert model validation raises error."""
        with pytest.raises(ValidationError):
            model_class(**model_data).full_clean()


class IntegrationTestMixin:
    """Mixin for integration test helpers."""
    
    def assert_workflow_completion(self, workflow_steps):
        """Assert workflow completes successfully."""
        for step_name, step_func in workflow_steps.items():
            try:
                result = step_func()
                assert result is not None, f"Workflow step '{step_name}' failed"
            except Exception as e:
                pytest.fail(f"Workflow step '{step_name}' raised exception: {e}")
    
    def assert_data_consistency(self, related_objects):
        """Assert data consistency across related objects."""
        # Example: Ensure total expenses match site budget
        # This would be customized based on specific business logic
        pass


class APITestMixin:
    """Mixin for API testing helpers."""
    
    def assert_api_response_structure(self, response, expected_fields):
        """Assert API response has expected structure."""
        response_data = json.loads(response.content)
        
        for field in expected_fields:
            assert field in response_data, f"API response missing field: {field}"
    
    def assert_api_list_response(self, response, expected_count=None):
        """Assert API list response format."""
        assert response.status_code == 200
        response_data = json.loads(response.content)
        
        if isinstance(response_data, list):
            if expected_count is not None:
                assert len(response_data) == expected_count
        elif isinstance(response_data, dict) and 'results' in response_data:
            if expected_count is not None:
                assert len(response_data['results']) == expected_count
    
    def assert_api_error_response(self, response, expected_status, expected_error):
        """Assert API error response."""
        assert response.status_code == expected_status
        response_data = json.loads(response.content)
        assert 'error' in response_data or 'detail' in response_data


class BaseTestCase(TestCase, TestDataMixin, AuthenticationMixin, 
                     FileUploadMixin, DateTimeMixin, MockMixin,
                     PermissionMixin, ValidationMixin, CustomAssertions):
    """Base test case with all mixins."""
    
    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.assertions = CustomAssertions()


class BaseAPITestCase(TestCase, TestDataMixin, AuthenticationMixin,
                      APITestMixin, CustomAssertions):
    """Base API test case."""
    
    def setUp(self):
        """Set up API test case."""
        super().setUp()
        self.assertions = CustomAssertions()


# Test decorators
def skip_if_ci(test_func):
    """Skip test if running in CI environment."""
    import os
    
    if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
        return pytest.mark.skip("Skipping test in CI environment")(test_func)
    
    return test_func


def requires_database(test_func):
    """Mark test as requiring database."""
    return pytest.mark.django_db(test_func)


def slow_test(test_func):
    """Mark test as slow running."""
    return pytest.mark.slow(test_func)


# Test context managers
class override_settings_context:
    """Context manager for overriding settings."""
    
    def __init__(self, **settings):
        self.settings = settings
        self.override = None
    
    def __enter__(self):
        self.override = override_settings(**self.settings)
        self.override.enable()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.override.disable()


class freeze_time_context:
    """Context manager for freezing time."""
    
    def __init__(self, freeze_time):
        self.freeze_time = freeze_time
        self.freezer = None
    
    def __enter__(self):
        from freezegun import freeze_time
        self.freezer = freeze_time(self.freeze_time)
        self.freezer.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.freezer.stop()


# Test data generators
class TestDataGenerator:
    """Generate test data for various scenarios."""
    
    @staticmethod
    def generate_expenses_for_site(site, count=10, status_distribution=None):
        """Generate expenses for a site with status distribution."""
        if status_distribution is None:
            status_distribution = {
                ExpenseStatus.PENDING: 0.3,
                ExpenseStatus.APPROVED: 0.5,
                ExpenseStatus.PAID: 0.2
            }
        
        expenses = []
        for i in range(count):
            # Determine status based on distribution
            rand = pytest.random.random()
            cumulative = 0
            status = ExpenseStatus.PENDING
            
            for status_option, probability in status_distribution.items():
                cumulative += probability
                if rand <= cumulative:
                    status = status_option
                    break
            
            expense = ExpenseFactory(site=site, status=status)
            expenses.append(expense)
        
        return expenses
    
    @staticmethod
    def generate_site_lifecycle():
        """Generate complete site lifecycle data."""
        cabinet = CabinetFactory()
        site = SiteFactory(cabinet=cabinet, status=SiteStatus.PLANNING)
        
        # Create phases
        phases = ProjectPhaseFactory.create_batch(3, site=site)
        
        # Create progress for each phase
        for phase in phases:
            SiteProgressFactory.create_batch(5, phase=phase)
        
        # Create expenses
        expenses = TestDataGenerator.generate_expenses_for_site(site, count=20)
        
        # Create personnel assignments
        personnel = PersonnelFactory.create_batch(5)
        for person in personnel:
            SiteAssignmentFactory(personnel=person, site=site)
        
        return {
            'cabinet': cabinet,
            'site': site,
            'phases': phases,
            'expenses': expenses,
            'personnel': personnel
        }


# Performance testing utilities
class PerformanceTracker:
    """Track performance metrics during tests."""
    
    def __init__(self):
        self.metrics = {}
    
    def track_query_count(self, test_func):
        """Track number of database queries."""
        from django.test.utils import override_settings
        from django.db import connection
        
        with self.assertNumQueries() as context:
            result = test_func()
        
        self.metrics['query_count'] = context.final_count
        return result
    
    def track_execution_time(self, test_func):
        """Track execution time."""
        import time
        
        start_time = time.time()
        result = test_func()
        end_time = time.time()
        
        self.metrics['execution_time'] = end_time - start_time
        return result
    
    def track_memory_usage(self, test_func):
        """Track memory usage."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        result = test_func()
        
        final_memory = process.memory_info().rss
        self.metrics['memory_delta'] = final_memory - initial_memory
        
        return result
