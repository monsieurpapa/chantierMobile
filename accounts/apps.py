from django.apps import AppConfig
from django.dispatch import receiver


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from allauth.account.signals import password_changed, password_set

        @receiver([password_changed, password_set], dispatch_uid='accounts_clear_must_change_password')
        def _clear_must_change_password(sender, request, user, **kwargs):
            if getattr(user, 'must_change_password', False):
                user.must_change_password = False
                user.save(update_fields=['must_change_password'])
