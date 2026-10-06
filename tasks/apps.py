"""App config for `tasks` — see tasks/models.py's module docstring for
what this app owns."""
from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks'
    verbose_name = 'Tâches'
