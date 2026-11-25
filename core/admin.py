"""
Notification and StatusChangeLog stay unregistered: they're internal,
system-generated audit/fan-out rows that no one edits by hand.

AuditLogEntry is registered read-only, as a fallback view of the journal
for superusers in Django admin (the main screen is the in-app "Journal
d'audit", core/audit_views.py). No add / change / delete: the journal is
append-only.
"""
from django.contrib import admin

from core.models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor_label', 'action', 'content_type', 'object_repr', 'cabinet', 'ip_address')
    list_filter = ('action', 'content_type', 'cabinet')
    search_fields = ('actor_label', 'object_repr', 'object_id', 'ip_address', 'request_path')
    date_hierarchy = 'timestamp'
    list_select_related = ('content_type', 'cabinet')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
