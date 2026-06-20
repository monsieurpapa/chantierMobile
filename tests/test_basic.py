"""
Simple test to verify the testing setup works correctly.
"""

import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from chantiermobile.constants import SiteStatus, UserRoles


@pytest.mark.unit
class TestBasicSetup(TestCase):
    """Test basic testing setup."""
    
    def test_django_setup(self):
        """Test Django is properly configured."""
        from django.conf import settings
        assert settings.configured == True
    
    def test_constants_import(self):
        """Test constants can be imported."""
        assert SiteStatus.ACTIVE == 'ACTIVE'
        assert UserRoles.DIRECTOR == 'DIRECTOR'
    
    def test_user_model(self):
        """Test User model is accessible."""
        User = get_user_model()
        assert User is not None
    
    def test_url_reverse(self):
        """Test URL reverse works."""
        home_url = reverse('home')
        assert home_url == '/'


@pytest.mark.integration
@pytest.mark.django_db
class TestBasicIntegration(TestCase):
    """Test basic integration functionality."""
    
    def test_create_user(self):
        """Test user creation."""
        User = get_user_model()
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
    
    def test_home_page_loads(self):
        """Test home page loads for authenticated user."""
        User = get_user_model()
        user = User.objects.create_user(username='hometest', password='pass123')
        self.client.force_login(user)
        response = self.client.get('/')
        assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.django_db
class TestBasicWorkflow(TestCase):
    """Test basic end-to-end workflow."""
    
    def test_user_registration_workflow(self):
        """Test basic user registration workflow."""
        # Test registration page loads
        response = self.client.get(reverse('account:signup'))
        assert response.status_code == 200
        
        # Create user
        User = get_user_model()
        user = User.objects.create_user(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        assert user is not None
        
        # Test login
        response = self.client.post(reverse('account:login'), {
            'username': 'newuser',
            'password': 'testpass123'
        }, follow=True)
        assert response.status_code == 200
