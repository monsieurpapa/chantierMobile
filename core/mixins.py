from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from accounts.models import UserCabinetRole

class CabinetAccessMixin:
    """
    Mixin to filter querysets based on the user's cabinet.
    Expects the view to have a 'model' attribute or 'get_queryset' method implementation.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_authenticated:
            return qs.none()
        
        # If superuser, allow all
        if self.request.user.is_superuser:
            return qs

        # Filter by user's cabinets
        if hasattr(self.request.user, 'cabinet_roles'):
            cabinets = self.request.user.cabinet_roles.values_list('cabinet', flat=True)
            return qs.filter(cabinet__in=cabinets)
        
        return qs.none()

    def get_user_cabinet(self):
        """Returns the first cabinet for the user. Useful for object creation."""
        if hasattr(self.request.user, 'cabinet_roles') and self.request.user.cabinet_roles.exists():
            return self.request.user.cabinet_roles.first().cabinet
        
        if self.request.user.is_superuser:
            from accounts.models import Cabinet
            return Cabinet.objects.first()
            
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
