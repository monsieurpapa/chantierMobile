from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# Paths that must stay reachable even for a user who still has to change
# their password — otherwise they could never reach the change-password
# page (or log out) in the first place.
EXEMPT_PATH_PREFIXES = ('/static/', '/media/', '/i18n/', '/set-language/')
EXEMPT_URL_NAMES = ('account_change_password', 'account_logout')


class ForcePasswordChangeMiddleware:
    """
    Redirects an authenticated user with `must_change_password=True` to the
    password-change page on every request, until they change it.

    Used for default/temporary accounts created by an administrator (see
    accounts.management.commands.bootstrap_admin_and_roles), so a shared
    temporary password can never be left in place after first login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, 'must_change_password', False)
            and not self._is_exempt(request.path)
        ):
            messages.info(
                request,
                _('For security, please set a new password before continuing.'),
            )
            return redirect('account_change_password')
        return self.get_response(request)

    @staticmethod
    def _is_exempt(path):
        if any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES):
            return True
        for name in EXEMPT_URL_NAMES:
            try:
                if path == reverse(name):
                    return True
            except Exception:
                continue
        return False
