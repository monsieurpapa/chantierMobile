"""
Performance tests for ChantierMobile application.
"""

import pytest
import time
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import override_settings
from unittest.mock import patch

from tests.factories import SiteFactory, ExpenseFactory, UserFactory, CabinetFactory, UserCabinetRoleFactory
from chantiermobile.constants import UserRoles


@pytest.mark.performance
@pytest.mark.django_db
class TestDatabasePerformance:
    """Test database query performance."""
    
    def test_site_list_query_performance(self, director_client):
        """Test site list query performance with large dataset."""
        # Create large dataset
        cabinet = CabinetFactory()
        user = director_client.request.user if hasattr(director_client, 'request') else UserFactory()
        UserCabinetRoleFactory(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR)
        
        sites = SiteFactory.create_batch(100, cabinet=cabinet)
        
        # Measure query time
        start_time = time.time()
        response = director_client.get(reverse('projects:site_list'))
        end_time = time.time()
        
        query_time = end_time - start_time
        
        assert response.status_code == 200
        assert query_time < 1.0  # Should complete within 1 second
        assert len(response.context['sites']) == 100
    
    def test_expense_list_with_optimization(self, accountant_client):
        """Test expense list query with select_related optimization."""
        # Create expenses
        expenses = ExpenseFactory.create_batch(50)
        
        # Test with optimization
        with self.assertNumQueries(3):  # Should be minimal queries
            response = accountant_client.get(reverse('finance:expense_list'))
            assert response.status_code == 200
    
    def test_dashboard_query_performance(self, director_client):
        """Test dashboard query performance."""
        # Create test data
        cabinet = CabinetFactory()
        user = director_client.request.user if hasattr(director_client, 'request') else UserFactory()
        UserCabinetRoleFactory(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR)
        
        sites = SiteFactory.create_batch(20, cabinet=cabinet)
        for site in sites:
            ExpenseFactory.create_batch(5, site=site)
        
        # Measure dashboard load time
        start_time = time.time()
        response = director_client.get(reverse('home'))
        end_time = time.time()
        
        load_time = end_time - start_time
        
        assert response.status_code == 200
        assert load_time < 2.0  # Should load within 2 seconds


@pytest.mark.performance
@pytest.mark.django_db
class TestMemoryUsage:
    """Test memory usage patterns."""
    
    def test_large_dataset_memory_usage(self):
        """Test memory usage with large datasets."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create large dataset
        sites = SiteFactory.create_batch(1000)
        for site in sites:
            ExpenseFactory.create_batch(10, site=site)
        
        # Load all data
        from projects.models import Site
        all_sites = list(Site.objects.all())
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 100MB)
        assert memory_increase < 100 * 1024 * 1024  # 100MB in bytes
        assert len(all_sites) == 1000
    
    def test_query_iterator_memory_efficiency(self):
        """Test iterator() for memory efficiency."""
        # Create large dataset
        SiteFactory.create_batch(5000)
        
        # Test iterator usage
        from projects.models import Site
        
        # Using iterator() should be memory efficient
        sites_iter = Site.objects.iterator()
        count = 0
        for site in sites_iter:
            count += 1
            if count > 100:  # Stop after 100 for test
                break
        
        assert count == 100


@pytest.mark.performance
@pytest.mark.django_db
class TestConcurrentAccess:
    """Test concurrent access performance."""
    
    def test_concurrent_site_creation(self):
        """Test concurrent site creation performance."""
        import threading
        import time
        
        results = []
        errors = []
        
        def create_site():
            try:
                site = SiteFactory()
                results.append(site.pk)
            except Exception as e:
                errors.append(e)
        
        # Create 10 concurrent threads
        threads = []
        start_time = time.time()
        
        for _ in range(10):
            thread = threading.Thread(target=create_site)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        assert len(errors) == 0
        assert len(results) == 10
        assert total_time < 5.0  # Should complete within 5 seconds
    
    def test_concurrent_expense_approval(self):
        """Test concurrent expense approval performance."""
        import threading
        
        # Create expenses
        expenses = ExpenseFactory.create_batch(20)
        results = []
        
        def approve_expense(expense):
            expense.status = 'APPROVED'
            expense.save()
            results.append(expense.pk)
        
        # Approve expenses concurrently
        threads = []
        for expense in expenses:
            thread = threading.Thread(target=approve_expense, args=(expense,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert len(results) == 20


@pytest.mark.performance
@pytest.mark.django_db
class TestCachePerformance:
    """Test caching performance."""
    
    @override_settings(CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    })
    def test_dashboard_caching(self, director_client):
        """Test dashboard caching performance."""
        # Create test data
        cabinet = CabinetFactory()
        user = director_client.request.user if hasattr(director_client, 'request') else UserFactory()
        UserCabinetRoleFactory(user=user, cabinet=cabinet, role=UserRoles.DIRECTOR)
        
        SiteFactory.create_batch(50, cabinet=cabinet)
        
        # First request (cache miss)
        start_time = time.time()
        response1 = director_client.get(reverse('home'))
        first_time = time.time() - start_time
        
        # Second request (cache hit)
        start_time = time.time()
        response2 = director_client.get(reverse('home'))
        second_time = time.time() - start_time
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Cached request should be faster
        assert second_time < first_time
    
    def test_query_caching(self):
        """Test query result caching."""
        from django.core.cache import cache
        from projects.models import Site
        
        # Create test data
        sites = SiteFactory.create_batch(10)
        
        # Test caching
        cache_key = 'all_sites'
        
        # Cache miss
        start_time = time.time()
        cached_sites = cache.get_or_set(cache_key, lambda: list(Site.objects.all()), timeout=300)
        first_time = time.time() - start_time
        
        # Cache hit
        start_time = time.time()
        cached_sites = cache.get_or_set(cache_key, lambda: list(Site.objects.all()), timeout=300)
        second_time = time.time() - start_time
        
        assert len(cached_sites) == 10
        assert second_time < first_time


@pytest.mark.performance
@pytest.mark.django_db
class TestFileUploadPerformance:
    """Test file upload performance."""
    
    def test_large_file_upload(self, authenticated_client):
        """Test large file upload performance."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        
        # Create a 5MB file
        large_file_content = b'x' * (5 * 1024 * 1024)
        large_file = SimpleUploadedFile(
            "large_file.jpg",
            large_file_content,
            content_type="image/jpeg"
        )
        
        start_time = time.time()
        response = authenticated_client.post(reverse('finance:expense_create'), {
            'site': 1,  # Mock site ID
            'category': 1,  # Mock category ID
            'amount': '1000.00',
            'description': 'Large file upload test',
            'receipt_image': large_file
        })
        end_time = time.time()
        
        upload_time = end_time - start_time
        
        # Upload should complete within reasonable time
        assert upload_time < 10.0  # 10 seconds for 5MB file
    
    def test_multiple_file_upload(self, authenticated_client):
        """Test multiple file upload performance."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        files = []
        for i in range(10):
            file_content = b'x' * (100 * 1024)  # 100KB each
            file = SimpleUploadedFile(
                f"file_{i}.jpg",
                file_content,
                content_type="image/jpeg"
            )
            files.append(file)
        
        start_time = time.time()
        
        # Upload files one by one
        for i, file in enumerate(files):
            response = authenticated_client.post(reverse('finance:expense_create'), {
                'site': 1,
                'category': 1,
                'amount': f'{100 + i}.00',
                'description': f'File upload test {i}',
                'receipt_image': file
            })
            assert response.status_code in [200, 302]
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # All uploads should complete within reasonable time
        assert total_time < 30.0  # 30 seconds for 10 files


@pytest.mark.performance
@pytest.mark.django_db
class TestAPIPerformance:
    """Test API endpoint performance."""
    
    def test_api_response_time(self, authenticated_client):
        """Test API response times."""
        # Create test data
        sites = SiteFactory.create_batch(100)
        
        # Test list endpoint
        start_time = time.time()
        response = authenticated_client.get('/api/sites/')
        end_time = time.time()
        
        response_time = end_time - start_time
        
        assert response.status_code == 200
        assert response_time < 0.5  # API should respond within 500ms
    
    def test_api_pagination_performance(self, authenticated_client):
        """Test API pagination performance."""
        # Create large dataset
        SiteFactory.create_batch(1000)
        
        # Test first page
        start_time = time.time()
        response = authenticated_client.get('/api/sites/?page=1&page_size=50')
        first_page_time = time.time() - start_time
        
        # Test middle page
        start_time = time.time()
        response = authenticated_client.get('/api/sites/?page=10&page_size=50')
        middle_page_time = time.time() - start_time
        
        # Test last page
        start_time = time.time()
        response = authenticated_client.get('/api/sites/?page=20&page_size=50')
        last_page_time = time.time() - start_time
        
        assert response.status_code == 200
        assert first_page_time < 1.0
        assert middle_page_time < 1.0
        assert last_page_time < 1.0


@pytest.mark.performance
@pytest.mark.django_db
class TestSearchPerformance:
    """Test search functionality performance."""
    
    def test_text_search_performance(self, authenticated_client):
        """Test text search performance."""
        # Create test data
        SiteFactory.create_batch(500)
        ExpenseFactory.create_batch(500)
        
        # Test search
        start_time = time.time()
        response = authenticated_client.get(reverse('search'), {'q': 'test'})
        end_time = time.time()
        
        search_time = end_time - start_time
        
        assert response.status_code == 200
        assert search_time < 2.0  # Search should complete within 2 seconds
    
    def test_filter_performance(self, authenticated_client):
        """Test filter performance."""
        # Create test data
        sites = SiteFactory.create_batch(200)
        
        # Test filtering
        start_time = time.time()
        response = authenticated_client.get(reverse('projects:site_list'), {
            'status': 'ACTIVE',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31'
        })
        end_time = time.time()
        
        filter_time = end_time - start_time
        
        assert response.status_code == 200
        assert filter_time < 1.0


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.django_db
class TestLoadTesting:
    """Load testing scenarios."""
    
    def test_heavy_load_simulation(self):
        """Simulate heavy load scenario."""
        import threading
        import time
        import random
        
        results = []
        
        def simulate_user():
            """Simulate a user session."""
            try:
                # Simulate various user actions
                time.sleep(random.uniform(0.1, 0.5))  # Random think time
                
                # Create site
                site = SiteFactory()
                results.append(('site_created', site.pk))
                
                # Create expenses
                for _ in range(random.randint(1, 5)):
                    expense = ExpenseFactory(site=site)
                    results.append(('expense_created', expense.pk))
                
                time.sleep(random.uniform(0.1, 0.3))
                
            except Exception as e:
                results.append(('error', str(e)))
        
        # Simulate 20 concurrent users
        threads = []
        start_time = time.time()
        
        for _ in range(20):
            thread = threading.Thread(target=simulate_user)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_operations = [r for r in results if r[0] != 'error']
        errors = [r for r in results if r[0] == 'error']
        
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(successful_operations) > 0
        assert total_time < 30.0  # Should complete within 30 seconds
        
        print(f"Load test completed: {len(successful_operations)} operations in {total_time:.2f}s")
