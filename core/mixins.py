from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from accounts.models import UserCabinetRole


def get_session_cabinet(request):
    """
    Returns the session-scoped Cabinet for a superuser, or None.
    Clears the session key if the cabinet no longer exists.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return None
    cabinet_id = request.session.get('active_cabinet_id')
    if not cabinet_id:
        return None
    try:
        from accounts.models import Cabinet
        return Cabinet.objects.get(pk=int(cabinet_id))
    except (Cabinet.DoesNotExist, ValueError, TypeError):
        try:
            del request.session['active_cabinet_id']
        except KeyError:
            pass
        return None


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
        """Returns the cabinet for object creation."""
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return active_cabinet
            from accounts.models import Cabinet
            return Cabinet.objects.order_by('created_at').first()

        if hasattr(self.request.user, 'cabinet_roles') and self.request.user.cabinet_roles.exists():
            return self.request.user.cabinet_roles.first().cabinet

        return None

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
            messages.error(request, "You do not have permission to perform this action.")
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
