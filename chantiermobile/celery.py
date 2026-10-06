"""
Celery application entrypoint. Configuration (broker/result backend, beat
schedule) lives in chantiermobile/settings.py under the CELERY_* /
CELERY_BEAT_SCHEDULE settings — see docs/architecture/overview.md#async-
tasks-celery for what currently runs on this worker/beat pair.
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chantiermobile.settings')

app = Celery('chantiermobile')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
