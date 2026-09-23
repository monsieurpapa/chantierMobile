from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from accounts.models import UserCabinetRole


def get_session_cabinet(request):
    """
    Returns the session-scoped "active cabinet" for the current user, or
    None if none is set.

    Historically superuser-only (used to impersonate/browse a single
    cabinet at a time). Now also usable for a regular user who belongs to
    more than one cabinet, so multi-cabinet staff can disambiguate which
    cabinet a new record should be tagged with (see
    CabinetAccessMixin.get_user_cabinet) — a non-superuser's stored
    selection is always re-validated against their own UserCabinetRole
    memberships below, so the session can never grant access to a cabinet
    the user doesn't actually belong to.
    """
    if not request.user.is_authenticated:
        return None
    cabinet_id = request.session.get('active_cabinet_id')
    if not cabinet_id:
        return None
    try:
        from accounts.models import Cabinet
        cabinet = Cabinet.objects.get(pk=int(cabinet_id))
    except (Cabinet.DoesNotExist, ValueError, TypeError):
        try:
            del request.session['active_cabinet_id']
        except KeyError:
            pass
        return None

    if not request.user.is_superuser and not UserCabinetRole.objects.filter(
        user=request.user, cabinet=cabinet
    ).exists():
        # Stale/foreign selection (e.g. the role was revoked after they
        # switched into it) — never trust it, and drop it so it isn't
        # re-checked on every request.
        try:
            del request.session['active_cabinet_id']
        except KeyError:
            pass
        return None

    return cabinet


def can_act_for_cabinet(request, cabinet, allowed_roles):
    """
    Server-side authorization check for a role-gated, state-changing
    action (approve/send/accept/reject/validate/receive/cancel/...)
    scoped to a specific cabinet's resource.

    This is the function-based-view counterpart to RoleRequiredMixin +
    get_role_cabinet(): every such action view MUST call this (or an
    equivalent explicit check) before mutating data, because @login_required
    alone only proves the user is signed in — it says nothing about their
    role or which cabinet the resource belongs to. Without this, any
    authenticated user of any role, in any cabinet, could POST directly to
    the action URL and bypass the UI's has_role-gated button.

    A superuser passes unless they have switched their session into a
    *different* specific cabinet (so a superuser working "as" Cabinet A
    doesn't silently act on Cabinet B's data). A regular user must hold one
    of `allowed_roles` within that exact cabinet — a DIRECTOR in Cabinet A
    has no special rights in Cabinet B.
    """
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and cabinet != active_cabinet:
            return False
        return True
    return UserCabinetRole.objects.filter(
        user=user, cabinet=cabinet, role__in=allowed_roles
    ).exists()


def can_view_cabinet(request, cabinet):
    """Looser sibling of can_act_for_cabinet: true for any authenticated
    user who has *some* role in this cabinet (or a superuser), regardless
    of which role. For actions that are shared/collaborative rather than
    role-gated — e.g. commenting on a progress report, where anyone with
    access to the site should be able to join the discussion, not just the
    roles that can file the report itself.
    """
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and cabinet != active_cabinet:
            return False
        return True
    return UserCabinetRole.objects.filter(user=user, cabinet=cabinet).exists()


class CabinetAccessMixin:
    """
    Mixin to filter querysets based on the user's cabinet.

    Set `cabinet_lookup_field` on the view to the ORM path to the cabinet FK:
      - Direct FK (Site, Personnel, Budget): leave as default 'cabinet'
      - Indirect FK (Expense, MaterialRequest): set to 'site__cabinet'
      - Deep indirect (Invoice): set to 'contract__site__cabinet'
    """
    cabinet_lookup_field = 'cabinet'

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_authenticated:
            return qs.none()

        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(**{self.cabinet_lookup_field: active_cabinet})
            return qs

        if hasattr(self.request.user, 'cabinet_roles'):
            cabinets = self.request.user.cabinet_roles.values_list('cabinet', flat=True)
            return qs.filter(**{f'{self.cabinet_lookup_field}__in': cabinets})

        return qs.none()

    def get_user_cabinet(self):
        """Returns the cabinet to tag a newly-created object with.

        - Superuser: the cabinet they've switched into, or (unchanged
          legacy default) the oldest cabinet in the system if they haven't.
        - Regular user with exactly one cabinet: that cabinet — unambiguous.
        - Regular user with several cabinets: the one they've explicitly
          switched into (accounts:switch_cabinet — no navbar UI links
          there for a regular user, but a form can offer it inline; see
          get_ambiguous_cabinet_choices), or None if they haven't chosen
          one yet. This used to silently pick whichever cabinet happened
          to sort first, which could tag a new record to the wrong
          tenant for multi-cabinet staff; every caller already treats a
          None return as "ask the user to identify their cabinet" (see
          e.g. SiteCreateView, PersonnelCreateView), so an unresolved
          multi-cabinet user now hits that same prompt instead of a
          silent guess.
        """
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return active_cabinet
            from accounts.models import Cabinet
            return Cabinet.objects.order_by('created_at').first()

        if hasattr(self.request.user, 'cabinet_roles'):
            cabinet_ids = list(self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)[:2])
            if len(cabinet_ids) == 1:
                from accounts.models import Cabinet
                return Cabinet.objects.filter(pk=cabinet_ids[0]).first()
            if len(cabinet_ids) > 1:
                return get_session_cabinet(self.request)

        return None

    def get_ambiguous_cabinet_choices(self):
        """Companion to get_user_cabinet() for a creation form that wants
        to let an unresolved multi-cabinet user pick explicitly (e.g. via
        an extra 'cabinet' form field) instead of just being blocked.

        Returns the queryset of cabinets to choose from, or None when
        there's nothing to disambiguate — either get_user_cabinet()
        already resolved one (superuser, single-cabinet user, or a
        multi-cabinet user who has an active cabinet switched in), or the
        user has no cabinet at all. Deliberately not called from
        get_queryset()/get_user_cabinet() themselves, or from any global
        context processor — it costs an extra query and is only worth
        that cost on the specific forms that need it.
        """
        if self.request.user.is_superuser:
            return None
        if self.get_user_cabinet() is not None:
            return None
        from accounts.models import Cabinet
        cabinets = Cabinet.objects.filter(user_roles__user=self.request.user).distinct().order_by('name')
        return cabinets if cabinets.count() > 1 else None

class RoleRequiredMixin:
    """
    Mixin to check if the user has one of the allowed roles within their cabinet.
    Access is denied if the user does not have the role.

    By default, checks role across all of the user's cabinets. Override
    get_role_cabinet() to scope the check to a specific cabinet (e.g. the
    cabinet that owns the resource being accessed). This prevents a user who
    is a DIRECTOR in Cabinet A from taking write actions on Cabinet B.
    """
    allowed_roles = []  # List of roles e.g. ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_role_cabinet(self):
        """Return the cabinet to scope the role check to, or None to allow any cabinet."""
        return None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        qs = UserCabinetRole.objects.filter(
            user=request.user,
            role__in=self.allowed_roles,
        )
        cabinet = self.get_role_cabinet()
        if cabinet is not None:
            qs = qs.filter(cabinet=cabinet)
        has_role = qs.exists()

        if not has_role:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        return super().dispatch(request, *args, **kwargs)

class PageHeaderMixin:
    """
    Mixin to provide consistent data for the page_header component.
    """
    def get_header_title(self):
        return getattr(self, 'header_title', "")

    def get_header_subtitle(self):
        return getattr(self, 'header_subtitle', "")

    def get_breadcrumb_items(self):
        return getattr(self, 'breadcrumb_items', [])

    def get_back_url(self):
        return getattr(self, 'back_url', None)

    def get_header_actions(self):
        return getattr(self, 'header_actions', [])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['header_title'] = self.get_header_title()
        context['header_subtitle'] = self.get_header_subtitle()
        context['breadcrumb_items'] = self.get_breadcrumb_items()
        context['back_url'] = self.get_back_url()
        context['header_actions'] = self.get_header_actions()
        return context
