"""
Test configuration and setup for ChantierMobile project.
"""

# Test settings overrides
TEST_SETTINGS = {
    'DATABASES': {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    },
    'CACHES': {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }
    },
    'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
    'MEDIA_ROOT': '/tmp/test_media',
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
    'PASSWORD_HASHERS': [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ],
}

# Test constants
TEST_USER_PASSWORD = 'testpass123'
TEST_ADMIN_PASSWORD = 'adminpass123'

# Test data constants
TEST_SITE_NAME = 'Test Construction Site'
TEST_CLIENT_NAME = 'Test Client Company'
TEST_EXPENSE_AMOUNT = '1000.00'
TEST_MATERIAL_QUANTITY = '25.5'

# Test file constants
TEST_IMAGE_CONTENT = b'fake_image_data'
TEST_FILE_CONTENT = b'test_file_content'

# Performance thresholds
MAX_RESPONSE_TIME = 2.0  # seconds
MAX_QUERY_COUNT = 10     # queries
MAX_MEMORY_USAGE = 50    # MB
