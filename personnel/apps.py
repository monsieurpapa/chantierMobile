"""App config for `personnel` — see personnel/models.py's module
docstring for what this app owns."""
from django.apps import AppConfig


class PersonnelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'personnel'
