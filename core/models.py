"""
Shared base models used across every app in the system (see
docs/architecture/overview.md#base-models-coremodelspy for the full
picture). Every business model inherits `BaseModel` rather than
`models.Model` directly, so soft delete, audit stamping and a public-safe
UUID identifier come for free and behave identically everywhere instead of
each app reinventing its own convention.
"""
from django.db import models
import uuid
from django.utils import timezone
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class SoftDeleteManager(models.Manager):
    """Default manager for a SoftDeleteModel: excludes soft-deleted rows so
    normal queries never need to remember to filter is_deleted=False
    themselves."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def all_with_deleted(self):
        """Escape hatch for the rare query that does need deleted rows
        (without switching the model's `all_objects` manager)."""
        return super().get_queryset()

class SoftDeleteModel(models.Model):
    """Replaces hard deletion with a flag: `delete()` never removes the
    row. There is deliberately no hard-delete path through the application
    — a business record's history (who requested/approved what, when) must
    survive an in-app "delete" so it can still be audited later. Use
    `Model.objects` (default manager) for the normal non-deleted view, and
    `Model.all_objects` when an investigation needs to see deleted rows
    too."""
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft-delete: flips `is_deleted` and stamps `deleted_at` instead
        of issuing a SQL DELETE."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        """Reverses delete(), putting the row back in the default
        (non-deleted) manager's results."""
        self.is_deleted = False
        self.deleted_at = None
        self.save()

class TimeStampedModel(models.Model):
    """Abstract mixin adding created_at/updated_at timestamps, maintained
    automatically by Django (`auto_now_add` / `auto_now`)."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class AuditableModel(TimeStampedModel):
    """Adds created_by/updated_by FKs (who, not just when) on top of
    TimeStampedModel's timestamps — together these answer "who touched
    this record and when" for every BaseModel subclass without each app
    wiring it up itself."""
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


class Notification(models.Model):
    """In-app notification (item 13 of the Directors/Engineers audit):
    before this, the only signal that something needed attention was
    email (revenue/notifications.py's single payment-received trigger)
    or noticing it yourself on a list page — nothing showed up inside
    the app itself. Created via core/notifications.py's helpers, from
    both directions of a workflow: "something needs your decision"
    (sent to the relevant role holders) and "your request was decided"
    (sent back to whoever submitted it).

    Deliberately plain — no generic FK to the source object, just a
    ready-to-follow `url` — so it stays a thin, read-only fan-out layer
    like core/approvals.py rather than another thing every app's models
    have to import."""
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
    )
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.recipient} — {self.message}"


class AuditLogEntry(models.Model):
    """One line of the superadmin audit journal ("Journal d'audit"): who
    did what, to which record, when, and from where.

    Written automatically — never by a view — by core/audit.py: model
    signals record every create / update / (soft) delete / restore on the
    business apps' models with a field-by-field diff, and the auth
    signals record logins, logouts and failed logins. The request that
    caused the change (user, IP, path) comes from AuditContextMiddleware.

    Append-only by design: save() refuses to rewrite an existing row and
    delete() refuses outright, so the journal can't be quietly edited
    from inside the application. (Old rows are pruned only by the
    core.tasks.purge_audit_log retention task, via a queryset delete.)

    Snapshots (`actor_label`, `object_repr`) are stored alongside the FKs
    on purpose: the journal must stay readable after the user or the
    record it talks about has been deleted."""
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
    )
    actor_label = models.CharField(max_length=255, blank=True)

    action = models.CharField(max_length=20, db_index=True)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    # {field_name: {"label": verbose name, "old": str|None, "new": str|None}}
    changes = models.JSONField(default=dict, blank=True)

    cabinet = models.ForeignKey(
        'accounts.Cabinet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = "entrée du journal d'audit"
        verbose_name_plural = "journal d'audit"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['cabinet', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.actor_label or '—'} {self.action} {self.object_repr}"

    def save(self, *args, **kwargs):
        if self.pk is not None and not kwargs.get('force_insert'):
            raise ValueError("Audit journal entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit journal entries cannot be deleted.")

    def get_action_display(self):
        from chantiermobile.constants import AuditAction
        try:
            return AuditAction(self.action).label
        except ValueError:
            return self.action

    @property
    def model_label(self):
        if self.content_type_id is None:
            return ''
        model = self.content_type.model_class()
        if model is None:
            return self.content_type.model
        return str(model._meta.verbose_name).capitalize()
