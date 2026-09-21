from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'site', 'phase', 'status', 'priority', 'assigned_to', 'due_date')
    list_filter = ('status', 'priority', 'site')
    search_fields = ('title', 'site__name', 'assigned_to__first_name', 'assigned_to__last_name')
    readonly_fields = ('completed_at',)
