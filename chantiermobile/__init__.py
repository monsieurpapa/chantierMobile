"""Ensures the Celery app is created when Django starts, so
`@shared_task` decorators across the codebase pick it up."""
from .celery import app as celery_app

__all__ = ('celery_app',)
