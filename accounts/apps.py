"""App config for accounts; wires up the signal that clears
must_change_password once an allauth password-change flow completes."""
from django.apps import AppConfig
from django.dispatch import receiver


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        """Registers a handler on allauth's password_changed/password_set
        signals: this is the other half of
        core.middleware.ForcePasswordChangeMiddleware — once the user
        actually sets a new password (via either signal, depending on
        which allauth flow they went through), the forced-redirect flag is
        cleared so the middleware stops intercepting their requests."""
        from allauth.account.signals import password_changed, password_set

        @receiver([password_changed, password_set], dispatch_uid='accounts_clear_must_change_password')
        def _clear_must_change_password(sender, request, user, **kwargs):
            if getattr(user, 'must_change_password', False):
                user.must_change_password = False
                user.save(update_fields=['must_change_password'])
