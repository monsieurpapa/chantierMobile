import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chantiermobile.settings')

app = Celery('chantiermobile')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
