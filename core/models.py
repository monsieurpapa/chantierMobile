from django.db import models
import uuid
from django.utils import timezone
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def all_with_deleted(self):
        return super().get_queryset()

class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save()

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class AuditableModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated"
    )

    class Meta:
        abstract = True

class BaseModel(SoftDeleteModel, AuditableModel):
    """
    Standard base model for most entities in the system.
    Includes soft delete, audit fields (created/updated by/at).
    """
    unique_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True


class StatusChangeLog(models.Model):
    """
    Generic audit log for status transitions on any model (Site, Invoice, etc.).

    Usage:
        StatusChangeLog.log(instance, changed_by=request.user, old_status='ACTIVE', new_status='PAUSED')
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='status_changes',
    )
    old_status = models.CharField(max_length=50)
    new_status = models.CharField(max_length=50)
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.content_type} #{self.object_id}: {self.old_status} → {self.new_status} by {self.changed_by}"

    @classmethod
    def log(cls, instance, changed_by, old_status, new_status, note=''):
        """Create a log entry for a status transition."""
        cls.objects.create(
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            changed_by=changed_by,
            old_status=old_status,
            new_status=new_status,
            note=note,
        )
