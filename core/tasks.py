"""Periodic housekeeping for the core app."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def purge_audit_log():
    """Delete audit journal entries older than AUDIT_LOG_RETENTION_DAYS
    (default 730 days; 0 disables the purge). Runs monthly via
    CELERY_BEAT_SCHEDULE in settings. Uses a queryset delete on purpose:
    AuditLogEntry.delete() refuses single-row deletes."""
    from core.models import AuditLogEntry

    days = getattr(settings, 'AUDIT_LOG_RETENTION_DAYS', 730)
    if not days:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = AuditLogEntry.objects.filter(timestamp__lt=cutoff).delete()
    return deleted
