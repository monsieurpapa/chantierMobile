"""App config for `projects` — see projects/models.py's module docstring
for what this app owns."""
from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'projects'
