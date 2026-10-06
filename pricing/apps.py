"""App config for the price library (Bibliothèque de Prix) and DQE."""
from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"
