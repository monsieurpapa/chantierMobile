from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse


class AccountAdapter(DefaultAccountAdapter):
    """
    Sends the user to their (role-scoped) dashboard after they change or
    set their password, instead of allauth's default behaviour of looping
    back to the change-password form itself.

    This matters most right after a forced password change: an account
    created with `must_change_password=True` (see
    accounts.management.commands.bootstrap_admin_and_roles) is redirected
    to the change-password page by core.middleware.ForcePasswordChangeMiddleware
    on every request until the password is replaced. Once that happens,
    the user should land straight on the dashboard — which is itself
    already scoped to what their role and cabinet(s) allow them to see
    (core.dashboard.build_dashboard_context) — rather than stare at an
    empty "change password" page again.
    """

    def get_password_change_redirect_url(self, request):
        return reverse('home')
