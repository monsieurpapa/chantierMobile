
import os
import dj_database_url
from pathlib import Path
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-key')

DEBUG = os.environ.get('DEBUG', '0') == '1'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'django_celery_results',
    'django_celery_beat',
    
    # Allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',

    # Local apps
    'core',
    'accounts',
    'projects',
    'personnel',
    'finance',
    'materials',
    'revenue',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Allauth
    "allauth.account.middleware.AccountMiddleware",
]

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# Allauth configuration
ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'optional'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

ROOT_URLCONF = 'chantiermobile.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'core.context_processors.language_context',
                'core.context_processors.site_info_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'chantiermobile.wsgi.application'

# Database
# Prefer DATABASE_URL (set by Render) over individual vars (used locally via docker-compose)
_db_default = 'postgresql://{user}:{password}@{host}:{port}/{name}'.format(
    user=os.environ.get('DB_USER', 'postgres'),
    password=os.environ.get('DB_PASSWORD', 'postgres'),
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    name=os.environ.get('DB_NAME', 'postgres'),
) if not os.environ.get('DATABASE_URL') else ''

DATABASES = {
    'default': dj_database_url.config(
        default=_db_default or 'sqlite:///db.sqlite3',
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'fr'

LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('English')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Language cookie settings
LANGUAGE_COOKIE_NAME = 'django_language'
LANGUAGE_COOKIE_AGE = 31536000  # 1 year
LANGUAGE_COOKIE_SECURE = not DEBUG  # True in production (HTTPS), False locally
LANGUAGE_COOKIE_HTTPONLY = False  # False so JavaScript can read it if needed
LANGUAGE_COOKIE_DOMAIN = None  # None for all domains

# Production security
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

TIME_ZONE = 'Africa/Kigali'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Celery
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

from celery.schedules import crontab
CELERY_TIMEZONE = TIME_ZONE  # Ensure beat schedule uses Africa/Kigali, not UTC
CELERY_BEAT_SCHEDULE = {
    'mark-overdue-invoices-daily': {
        'task': 'revenue.tasks.mark_overdue_invoices',
        'schedule': crontab(hour=1, minute=0),  # Runs at 01:00 Africa/Kigali daily
    },
}
