"""
No core models are registered with the Django admin: Notification and
StatusChangeLog are internal, system-generated audit/fan-out rows that no
one edits by hand, so there's nothing here to expose.
"""
from django.contrib import admin

# Register your models here.
