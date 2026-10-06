"""
Django settings for the chantiermobile project. Mostly standard Django
settings wired up from environment variables for deployment flexibility
(Render, Railway, or plain docker-compose); see docs/security.md and the
inline comments below for the reasoning behind the non-obvious ones
(session idle timeout, Cloudflare R2 media storage, Celery beat schedule).
"""
import os
import dj_database_url
from pathlib import Path
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-key')

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h]
# Render injects RENDER_EXTERNAL_HOSTNAME
_render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if _render_hostname:
    ALLOWED_HOSTS.append(_render_hostname)
# Railway injects RAILWAY_PUBLIC_DOMAIN
_railway_hostname = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
if _railway_hostname:
    ALLOWED_HOSTS.append(_railway_hostname)

CSRF_TRUSTED_ORIGINS = [h for h in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if h]
if _render_hostname:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_render_hostname}')
if _railway_hostname:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_railway_hostname}')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

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
    'pricing',
    'procurement',
    'tasks',
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

    # Log an idle user out after SESSION_IDLE_TIMEOUT_SECONDS (15 minutes)
    # with an explicit message — before ForcePasswordChangeMiddleware, so
    # an expired session is sent to login rather than to the password-
    # change page first.
    'core.middleware.SessionIdleTimeoutMiddleware',

    # Force a password change for accounts flagged with must_change_password
    'core.middleware.ForcePasswordChangeMiddleware',
]

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# Allauth configuration (django-allauth >= 0.56 / Django 6 compatible)
ACCOUNT_ADAPTER = 'accounts.adapter.AccountAdapter'
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
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
                'core.context_processors.active_cabinet_context',
                'core.context_processors.currency_context',
                'core.context_processors.notifications_context',
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

# Session idle timeout: 15 minutes of inactivity logs a user out, rather
# than leaving a construction director's or accountant's session (with
# access to financial data) open indefinitely on a shared or unattended
# device. Enforced by core.middleware.SessionIdleTimeoutMiddleware, which
# stamps a `last_activity` timestamp into the session and ends it with an
# explicit message once that stamp is older than SESSION_IDLE_TIMEOUT_SECONDS
# — rather than relying only on Django's own cookie/session-store expiry,
# which would just silently turn the next request into a fresh anonymous
# session with no explanation. SESSION_COOKIE_AGE is set to match as a
# backstop (bounds how long the cookie can ever be valid regardless of the
# middleware), but SESSION_SAVE_EVERY_REQUEST is deliberately left off:
# the middleware already marks the session modified (and so re-saved, and
# the cookie's Max-Age refreshed) on every request where it updates the
# stamp, and it only updates the stamp once per SESSION_IDLE_TOUCH_INTERVAL_SECONDS
# rather than on every single request — a request in between just reads
# the existing stamp to check the elapsed gap. Without that throttle, a
# user clicking around normally would write to the session table on every
# request (needless DB load in production, and it roughly tripled this
# suite's runtime in testing — most tests fire several requests from the
# same client within the same second). The throttle only costs precision:
# the recorded idle time can be up to SESSION_IDLE_TOUCH_INTERVAL_SECONDS
# stale, so the effective timeout is 15–16 minutes rather than exactly 15.
SESSION_COOKIE_AGE = 60 * 15  # 15 minutes
SESSION_IDLE_TIMEOUT_SECONDS = 60 * 15  # 15 minutes — used by SessionIdleTimeoutMiddleware
SESSION_IDLE_TOUCH_INTERVAL_SECONDS = 60  # how often the activity stamp is actually rewritten

# Production security
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

TIME_ZONE = 'Africa/Kigali'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (user uploads: cabinet logos, expense receipts)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

if not DEBUG:
    # Cloudflare R2 via S3-compatible API (10 GB free, no egress fees)
    # Env vars map from Render dashboard → Cloudflare R2 API token values:
    #   CLOUDFARE_R2_TOKEN_NAME  → the "Access Key ID" shown when you create an R2 API token
    #   CLOUDFARE_API_TOKEN      → the "Secret Access Key" shown when you create an R2 API token
    #   CLOUDFARE_R2_BUCKET_NAME → the bucket name you created (e.g. "chantiermobile-media")
    #   CLOUDFARE_R2_BUCKET_URL  → S3 endpoint: https://<account-id>.r2.cloudflarestorage.com
    DEFAULT_FILE_STORAGE = 'chantiermobile.storage_backends.MediaStorage'
    AWS_ACCESS_KEY_ID = os.environ.get('CLOUDFARE_R2_TOKEN_NAME')
    AWS_SECRET_ACCESS_KEY = os.environ.get('CLOUDFARE_API_TOKEN')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('CLOUDFARE_R2_BUCKET_NAME', 'chantiermobile-media')
    AWS_S3_ENDPOINT_URL = os.environ.get('CLOUDFARE_R2_BUCKET_URL')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN')  # optional: custom public domain
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# Email Configuration
if DEBUG:
    # Console backend for development — print emails to console
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # SMTP backend for production
    EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@chantiermobile.com')

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
