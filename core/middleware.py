"""
Request middleware for the two account-safety behaviors described in
docs/security.md: forcing a password change on a freshly-created account,
and logging an idle session out explicitly rather than letting it decay
into a confusing anonymous state. Both are plain old-style middleware
(callable classes) rather than per-view decorators, because they need to
run on every authenticated request regardless of which view handles it.
"""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
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


# Paths where an idle-expired session shouldn't trigger our own explicit
# logout-and-redirect — the login/logout views end up logging the user
# out (or already show a login form) on their own regardless, and static/
# media/i18n requests were never really "activity" in the first place.
IDLE_TIMEOUT_EXEMPT_PATH_PREFIXES = ('/static/', '/media/', '/i18n/', '/set-language/')
IDLE_TIMEOUT_EXEMPT_URL_NAMES = ('account_login', 'account_logout')


class SessionIdleTimeoutMiddleware:
    """
    Logs an authenticated user out after settings.SESSION_IDLE_TIMEOUT_SECONDS
    (15 minutes) of inactivity, with an explicit message, rather than
    leaving them to discover it only because @login_required happened to
    redirect them somewhere with no explanation.

    Stamps a `last_activity` timestamp into the session, and if the gap
    since that stamp exceeds the timeout, ends the session (logout()) and
    redirects to login with a message instead of silently continuing as a
    fresh anonymous session. The stamp itself is only rewritten once per
    SESSION_IDLE_TOUCH_INTERVAL_SECONDS (default 60s) rather than on every
    request — see the comment above SESSION_IDLE_TIMEOUT_SECONDS in
    settings.py for why: writing on every request works too, but costs a
    session-table write per authenticated page view, and the timeout only
    needs to be accurate to within that interval, not to the second.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user is not None
            and user.is_authenticated
            and not self._is_exempt(request.path)
        ):
            timeout_seconds = getattr(settings, 'SESSION_IDLE_TIMEOUT_SECONDS', 900)
            touch_interval = getattr(settings, 'SESSION_IDLE_TOUCH_INTERVAL_SECONDS', 60)
            now = time.time()
            last_activity = request.session.get('last_activity')
            if last_activity is not None and (now - last_activity) > timeout_seconds:
                logout(request)
                messages.info(
                    request,
                    _("Votre session a expiré après 15 minutes d'inactivité. Veuillez vous reconnecter."),
                )
                return redirect('account_login')
            if last_activity is None or (now - last_activity) >= touch_interval:
                request.session['last_activity'] = now
        return self.get_response(request)

    @staticmethod
    def _is_exempt(path):
        if any(path.startswith(prefix) for prefix in IDLE_TIMEOUT_EXEMPT_PATH_PREFIXES):
            return True
        for name in IDLE_TIMEOUT_EXEMPT_URL_NAMES:
            try:
                if path == reverse(name):
                    return True
            except Exception:
                continue
        return False
