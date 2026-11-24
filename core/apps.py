"""Django app configuration for the core app (see core/__init__.py)."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Superadmin audit journal: model + auth signal receivers.
        from core.audit import connect_signals
        connect_signals()
