import secrets
import string

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.views.generic import DetailView, UpdateView, ListView, DeleteView, CreateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.http import Http404
from .models import UserCabinetRole, Cabinet, CabinetContextLog
from .forms import UserProfileForm, UserCabinetRoleForm, UserAdminForm, UserCreateForm, AssignUserToCabinetForm, AssignUserToCabinetFromCabinetForm, CabinetForm, AssignRoleToCabinetUserForm
from projects.models import Site, ProjectPhase
from materials.models import MaterialRequest
from finance.models import Expense
from revenue.models import Invoice
from core.mixins import PageHeaderMixin
from chantiermobile.constants import UserRoles, ApprovalStatus

User = get_user_model()


def _generate_temp_password():
    """Same convention as bootstrap_admin_and_roles: a random temporary
    password the recipient must change on first login (must_change_password)."""
    alphabet = string.ascii_letters + string.digits
    return 'Cm-' + ''.join(secrets.choice(alphabet) for _ in range(10)) + '!'


class UserProfileUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    RBAC-Protected view for user profile management
    
    Access Control:
    - Users can only view/edit their own profile (LoginRequiredMixin + test_func)
    - Displays content based on user's cabinet roles and permissions
    - Shows only projects/materials/expenses/invoices from user's assigned cabinets
    
    Features:
    - Personal information editing
    - Cabinet roles display (based on RBAC)
    - Project assignment visibility
    - Material request tracking
    - Expense and invoice management
    """
    model = User
    form_class = UserProfileForm
    template_name = 'account/user_profile_update.html'
    success_url = reverse_lazy('accounts:profile_update')
    
    def test_func(self):
        """
        RBAC Check: Ensure user can only access their own profile
        Returns False if trying to access another user's profile
        """
        user = self.request.user
        # Users can only edit their own profile
        return True  # Already filtered by get_object()
    
    def get_object(self):
        """
        RBAC Override: Always return the current authenticated user
        Prevents users from accessing other users' profiles
        """
        return self.request.user
    
    def get_context_data(self, **kwargs):
        """
        Build context with RBAC-filtered data
        Only shows projects, materials, expenses, and invoices 
        from cabinets where user has a role
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # ====================
        # RBAC: Cabinet Roles
        # ====================
        cabinet_roles = user.cabinet_roles.all().select_related('cabinet')
        context['cabinet_roles'] = cabinet_roles
        context['has_cabinet_access'] = cabinet_roles.exists()
        
        # RBAC: Get list of cabinets user has access to
        user_cabinet_ids = cabinet_roles.values_list('cabinet_id', flat=True)
        
        # ====================
        # RBAC: Projects
        # ====================
        # Only show sites from cabinets where user has a role
        # Evaluate each queryset once: use list() so the slice is reused for .count via len()
        sites = list(Site.objects.filter(
            cabinet__in=user_cabinet_ids
        ).select_related('cabinet').order_by('-created_at')[:10])
        context['sites'] = sites
        context['total_sites'] = len(sites)

        # ====================
        # RBAC: Material Requests
        # ====================
        # Only show material requests from user's cabinet projects
        material_requests = list(MaterialRequest.objects.filter(
            site__cabinet__in=user_cabinet_ids
        ).select_related('site').order_by('-created_at')[:10])
        context['material_requests'] = material_requests
        context['total_material_requests'] = len(material_requests)

        # ====================
        # RBAC: Expenses
        # ====================
        # Only show expenses from sites in user's cabinets
        expenses = list(Expense.objects.filter(
            site__cabinet__in=user_cabinet_ids
        ).select_related('category', 'site').order_by('-created_at')[:10])
        context['expenses'] = expenses
        context['total_expenses'] = len(expenses)

        # ====================
        # RBAC: Invoices
        # ====================
        # Only show invoices from contracts related to user's cabinet sites
        invoices = list(Invoice.objects.filter(
            contract__site__cabinet__in=user_cabinet_ids
        ).select_related('contract').order_by('-created_at')[:10])
        context['invoices'] = invoices
        context['total_invoices'] = len(invoices)

        # ====================
        # RBAC: Statistics & Permissions
        # ====================
        # Calculate pending items for user's cabinets (separate queries — different filter)
        pending_material_requests = MaterialRequest.objects.filter(
            site__cabinet__in=user_cabinet_ids, status='PENDING'
        ).count()
        pending_expenses = Expense.objects.filter(
            site__cabinet__in=user_cabinet_ids, status='PENDING'
        ).count()
        context['pending_items'] = pending_material_requests + pending_expenses
        
        # Add permission context for template
        context['can_edit_profile'] = True  # Current user can always edit their own profile
        context['can_view_expenses'] = True  # Filtered by RBAC above
        context['can_view_materials'] = True  # Filtered by RBAC above
        
        # Add user roles for template conditionals
        user_roles = cabinet_roles.values_list('role', flat=True)
        context['user_roles'] = list(user_roles)
        context['is_director'] = 'DIRECTOR' in user_roles
        context['is_engineer'] = 'ENGINEER' in user_roles or 'CHIEF_ENGINEER' in user_roles
        context['is_accountant'] = 'ACCOUNTANT' in user_roles
        context['is_cashier'] = 'CASHIER' in user_roles
        
        return context
    
    def form_valid(self, form):
        """
        RBAC: Only allow user to update their own profile
        """
        if form.instance.id != self.request.user.id:
            messages.error(
                self.request, 
                _('You do not have permission to edit this profile.')
            )
            return self.form_invalid(form)
        
        messages.success(self.request, _('Your profile has been updated successfully.'))
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """Handle form errors"""
        messages.error(self.request, _('There was an error updating your profile. Please check the form.'))
        return super().form_invalid(form)


# ========================
# ADMIN USER MANAGEMENT
# ========================

class IsSuperAdminMixin(UserPassesTestMixin):
    """Mixin to check if user is superadmin"""
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access this page.'))
        return redirect('home')


class UserListAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, ListView):
    """
    SUPERADMIN ONLY: List all users with management capabilities

    Features:
    - View all system users
    - Search by username, email, name
    - Filter by status (active/inactive/staff/superadmin)
    - Per-row quick actions: activate/deactivate, reset password
    - Quick links to view, edit or delete users
    """
    model = User
    template_name = 'account/admin_users_list.html'
    context_object_name = 'users'
    paginate_by = 25
    header_title = _("Gestion des utilisateurs")
    header_subtitle = _("Gérez tous les utilisateurs, permissions et niveaux d'accès")
    back_url = reverse_lazy('home')

    def get_breadcrumb_items(self):
        return [
            {'title': 'Admin', 'url': None},
            {'title': 'Users', 'url': None},
        ]

    def get_header_actions(self):
        return [
            {
                'label': _("Nouvel utilisateur"),
                'url': str(reverse_lazy('accounts:admin_user_create')),
                'icon': 'user-plus',
                'class': 'btn-falcon-primary',
            },
            {
                'label': _("Affectations de rôles"),
                'url': str(reverse_lazy('accounts:admin_role_assignments_list')),
                'icon': 'sitemap',
                'class': 'btn-falcon-default',
            },
        ]

    def get_queryset(self):
        """Get all users with related data"""
        queryset = User.objects.all().order_by('-date_joined')
        
        # Search functionality
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                username__icontains=search
            ) | queryset.filter(
                email__icontains=search
            ) | queryset.filter(
                first_name__icontains=search
            ) | queryset.filter(
                last_name__icontains=search
            )
        
        # Filter by status
        status = self.request.GET.get('status', '')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        elif status == 'staff':
            queryset = queryset.filter(is_staff=True)
        elif status == 'superadmin':
            queryset = queryset.filter(is_superuser=True)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['inactive_users'] = User.objects.filter(is_active=False).count()
        context['staff_users'] = User.objects.filter(is_staff=True).count()
        context['superadmin_users'] = User.objects.filter(is_superuser=True).count()
        context['search'] = self.request.GET.get('search', '')
        context['status'] = self.request.GET.get('status', '')
        return context


class UserEditAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, UpdateView):
    """
    SUPERADMIN ONLY: Edit any user's information and permissions
    
    Allows superadmin to:
    - Edit user personal information
    - Activate/deactivate accounts
    - Grant/revoke staff access
    - Grant/revoke superadmin access
    """
    model = User
    form_class = UserAdminForm
    template_name = 'account/admin_user_edit.html'
    success_url = reverse_lazy('accounts:admin_users_list')

    def get_header_title(self):
        return _("Modifier l'utilisateur : %(name)s") % {'name': self.object.username}

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Utilisateurs"), 'url': str(reverse_lazy('accounts:admin_users_list'))},
            {'title': self.object.username, 'url': str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_object(self):
        """Get the user to edit"""
        user_id = self.kwargs.get('pk')
        return get_object_or_404(User, pk=user_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        context['target_user'] = user
        context['cabinet_roles'] = user.cabinet_roles.all().select_related('cabinet')
        return context

    def form_valid(self, form):
        """Handle successful form submission"""
        user = form.save(commit=False)

        # Guard: a superadmin editing their own account cannot revoke the
        # very access they're using right now — that would either lock
        # them out immediately (is_active) or leave the system with one
        # fewer superadmin able to undo the mistake. Other profile edits
        # in the same submission still go through.
        if user.pk == self.request.user.pk:
            original = User.objects.get(pk=user.pk)
            blocked = []
            if not user.is_active and original.is_active:
                user.is_active = True
                blocked.append(_('deactivate'))
            if not user.is_staff and original.is_staff:
                user.is_staff = True
                blocked.append(_('remove staff access from'))
            if not user.is_superuser and original.is_superuser:
                user.is_superuser = True
                blocked.append(_('remove superadmin access from'))
            if blocked:
                messages.warning(
                    self.request,
                    _('You cannot {actions} your own account — those changes were ignored. Ask another superadmin instead.').format(
                        actions=' / '.join(str(action) for action in blocked)
                    )
                )

        user.save()
        messages.success(
            self.request,
            _('User {} has been updated successfully.').format(user.username)
        )
        return super().form_valid(form)


class UserDeleteAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, DeleteView):
    """
    SUPERADMIN ONLY: Delete a user account
    
    Security:
    - Cannot delete own account
    - Confirmation required
    - Logs deletion action
    """
    model = User
    template_name = 'account/admin_user_delete.html'
    success_url = reverse_lazy('accounts:admin_users_list')

    def get_header_title(self):
        return _("Supprimer l'utilisateur : %(name)s") % {'name': self.object.username}

    def get_header_subtitle(self):
        return _("Cette action est irréversible.")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Utilisateurs"), 'url': str(reverse_lazy('accounts:admin_users_list'))},
            {'title': self.object.username, 'url': str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Supprimer"), 'url': None},
        ]

    def get_object(self):
        """Get the user to delete"""
        user_id = self.kwargs.get('pk')
        user = get_object_or_404(User, pk=user_id)

        # Prevent self-deletion
        if user.id == self.request.user.id:
            raise Http404(_('You cannot delete your own account.'))
        
        return user
    
    def delete(self, request, *args, **kwargs):
        """Delete the user and show message"""
        user = self.object
        username = user.username
        messages.warning(
            self.request,
            _('User {} has been deleted.').format(username)
        )
        return super().delete(request, *args, **kwargs)


class UserDetailAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, DetailView):
    """
    SUPERADMIN ONLY: View detailed user information
    
    Shows:
    - User profile information
    - Cabinet roles and permissions
    - Projects assigned
    - Account status
    - Creation date and last login
    """
    model = User
    template_name = 'account/admin_user_detail.html'
    context_object_name = 'target_user'

    def get_header_title(self):
        return _("Profil utilisateur : %(name)s") % {'name': self.object.username}

    def get_header_subtitle(self):
        return self.object.email or ""

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_users_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Utilisateurs"), 'url': str(reverse_lazy('accounts:admin_users_list'))},
            {'title': self.object.username, 'url': None},
        ]

    def get_header_actions(self):
        return [
            {
                'label': _("Modifier l'utilisateur"),
                'url': str(reverse_lazy('accounts:admin_user_edit', kwargs={'pk': self.object.pk})),
                'icon': 'edit',
                'class': 'btn-falcon-default',
            },
        ]

    def get_object(self):
        """Get the user to view"""
        user_id = self.kwargs.get('pk')
        return get_object_or_404(User, pk=user_id)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object

        # Get cabinet roles
        cabinet_roles = user.cabinet_roles.all().select_related('cabinet')
        context['cabinet_roles'] = cabinet_roles
        
        # Get projects assigned
        user_cabinet_ids = cabinet_roles.values_list('cabinet_id', flat=True)
        sites = Site.objects.filter(cabinet__in=user_cabinet_ids).select_related('cabinet')
        context['sites'] = sites[:10]
        context['projects'] = sites[:10]  # Same as sites for compatibility
        
        # Get material requests
        material_requests = MaterialRequest.objects.filter(site__cabinet__in=user_cabinet_ids).select_related('site')
        context['material_requests'] = material_requests[:10]
        context['total_material_requests'] = material_requests.count()
        
        # Get expenses
        expenses = Expense.objects.filter(site__cabinet__in=user_cabinet_ids).select_related('category', 'site')
        context['expenses'] = expenses[:10]
        context['total_expenses'] = expenses.count()
        
        # Get invoices
        invoices = Invoice.objects.filter(contract__site__cabinet__in=user_cabinet_ids).select_related('contract')
        context['invoices'] = invoices[:10]
        context['total_invoices'] = invoices.count()
        
        # Account statistics
        context['is_active'] = user.is_active
        context['is_staff'] = user.is_staff
        context['is_superuser'] = user.is_superuser
        
        return context


class UserCreateAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, CreateView):
    """
    SUPERADMIN ONLY: Create a brand-new user account.

    No password field in the form — a random temporary password is
    generated here and shown once in the success message, with
    must_change_password forced on so the new user sets their own
    password the first time they log in.
    """
    model = User
    form_class = UserCreateForm
    template_name = 'account/admin_user_create.html'
    header_title = _("Nouvel utilisateur")
    header_subtitle = _("Créez un compte et affectez ses accès initiaux")
    back_url = reverse_lazy('accounts:admin_users_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Utilisateurs"), 'url': str(reverse_lazy('accounts:admin_users_list'))},
            {'title': _("Nouvel utilisateur"), 'url': None},
        ]

    def form_valid(self, form):
        self.object = form.save(commit=False)
        temp_password = _generate_temp_password()
        self.object.set_password(temp_password)
        self.object.must_change_password = True
        self.object.save()
        messages.success(
            self.request,
            _('User {username} created. Temporary password: {password} — copy it now and share it securely; they must set their own password on first login.').format(
                username=self.object.username, password=temp_password
            )
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.object.pk})


class UserResetPasswordAdminView(LoginRequiredMixin, IsSuperAdminMixin, View):
    """
    SUPERADMIN ONLY: Generate a new temporary password for any user
    (including, edge case, themselves) and force a change on next login.
    POST-only — triggered by a one-click button with a JS confirm.
    """

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        temp_password = _generate_temp_password()
        user.set_password(temp_password)
        user.must_change_password = True
        user.save(update_fields=['password', 'must_change_password'])

        if user.pk == request.user.pk:
            # Changing your own password invalidates the session auth hash;
            # keep the current session alive instead of logging them out.
            update_session_auth_hash(request, user)

        messages.success(
            request,
            _('Password reset for {username}. New temporary password: {password} — copy it now and share it securely; they must set their own password on next login.').format(
                username=user.username, password=temp_password
            )
        )
        return redirect(request.META.get('HTTP_REFERER') or reverse_lazy('accounts:admin_user_detail', kwargs={'pk': user.pk}))


class UserToggleActiveAdminView(LoginRequiredMixin, IsSuperAdminMixin, View):
    """
    SUPERADMIN ONLY: One-click activate/deactivate toggle.
    POST-only. Blocks self-deactivation (mirrors the self-delete guard).
    """

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if user.pk == request.user.pk:
            messages.error(request, _('You cannot deactivate your own account.'))
            return redirect(request.META.get('HTTP_REFERER') or reverse_lazy('accounts:admin_user_detail', kwargs={'pk': pk}))

        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        if user.is_active:
            messages.success(request, _('{username} has been activated.').format(username=user.username))
        else:
            messages.warning(request, _('{username} has been deactivated.').format(username=user.username))
        return redirect(request.META.get('HTTP_REFERER') or reverse_lazy('accounts:admin_user_detail', kwargs={'pk': pk}))


# ============================================
# Cabinet Context Switching
# ============================================

class SwitchCabinetView(LoginRequiredMixin, View):
    """POST-only view to switch the caller's active cabinet context.

    A superuser can switch into any cabinet in the system (platform-admin
    impersonation). A regular user can only switch into a cabinet they
    actually belong to — get_object_or_404 below is scoped accordingly,
    so this can never be used to activate a session cabinet outside the
    user's own memberships. Regular users with only one cabinet (or none)
    have nothing to disambiguate and the template never offers them this
    control, but the view enforces the same rule regardless of what the
    UI shows.
    """

    def post(self, request):
        cabinet_id = request.POST.get('cabinet_id', '').strip()

        if not cabinet_id:
            # Clear active cabinet → back to "all cabinets" (superuser) or
            # "all of my cabinets" (multi-cabinet regular user).
            old_cabinet_id = request.session.pop('active_cabinet_id', None)
            if old_cabinet_id:
                CabinetContextLog.objects.create(
                    cabinet=None,
                    switched_by=request.user,
                    action=CabinetContextLog.CLEAR,
                )
        else:
            try:
                cabinet_pk = int(cabinet_id)
            except (ValueError, TypeError):
                messages.error(request, _('Invalid cabinet selection.'))
                return redirect(request.META.get('HTTP_REFERER') or 'home')

            if request.user.is_superuser:
                cabinet = get_object_or_404(Cabinet, pk=cabinet_pk)
            else:
                cabinet = get_object_or_404(Cabinet, pk=cabinet_pk, user_roles__user=request.user)
            request.session['active_cabinet_id'] = cabinet_pk
            CabinetContextLog.objects.create(
                cabinet=cabinet,
                switched_by=request.user,
                action=CabinetContextLog.SWITCH,
            )

        return redirect(request.META.get('HTTP_REFERER') or 'home')


class AssignUserToCabinetView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, CreateView):
    """
    Superadmin view to assign users to cabinets
    
    Features:
    - Only superadmin can access
    - Assigns user to cabinet with specific role
    - Sets initial approval status
    - Prevents duplicate assignments
    """
    model = UserCabinetRole
    form_class = AssignUserToCabinetForm
    template_name = 'account/assign_user_to_cabinet.html'

    def get_target_user(self):
        if not hasattr(self, '_target_user'):
            self._target_user = get_object_or_404(User, pk=self.kwargs.get('user_id'))
        return self._target_user

    def get_header_title(self):
        return _("Affecter %(name)s à un cabinet") % {'name': self.get_target_user().username}

    def get_header_subtitle(self):
        return _("Sélectionnez un cabinet et un rôle pour cet utilisateur")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': self.kwargs.get('user_id')}))

    def get_breadcrumb_items(self):
        user = self.get_target_user()
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Utilisateurs"), 'url': str(reverse_lazy('accounts:admin_users_list'))},
            {'title': user.username, 'url': str(reverse_lazy('accounts:admin_user_detail', kwargs={'pk': user.pk}))},
            {'title': _("Affecter un cabinet"), 'url': None},
        ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.get_target_user()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['target_user'] = self.get_target_user()
        return context

    def get_success_url(self):
        user_id = self.kwargs.get('user_id')
        return reverse_lazy('accounts:admin_user_detail', kwargs={'pk': user_id})

    def form_valid(self, form):
        messages.success(self.request, _('User assigned to cabinet successfully.'))
        return super().form_valid(form)


class CabinetListAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, ListView):
    """
    Superadmin view to manage all cabinets
    
    Features:
    - List all cabinets with statistics
    - Search by cabinet name
    - Show user count per cabinet
    - Show active roles count
    """
    model = Cabinet
    template_name = 'account/admin_cabinets_list.html'
    context_object_name = 'cabinets'
    paginate_by = 25
    header_title = _("Gestion des cabinets")
    header_subtitle = _("Gérez tous les cabinets et les affectations des utilisateurs")
    back_url = reverse_lazy('home')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': None},
        ]

    def get_header_actions(self):
        return [
            {
                'label': _("Nouveau cabinet"),
                'url': str(reverse_lazy('accounts:admin_cabinet_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }
        ]

    def get_queryset(self):
        qs = Cabinet.objects.all().order_by('name')
        
        # Search functionality
        search_query = self.request.GET.get('search', '')
        if search_query:
            qs = qs.filter(name__icontains=search_query)
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistics
        context['total_cabinets'] = Cabinet.objects.count()
        context['search_query'] = self.request.GET.get('search', '')
        
        # Calculate total users and pending assignments across all cabinets
        from accounts.models import UserCabinetRole
        context['total_users'] = UserCabinetRole.objects.filter(status='APPROVED').count()
        context['total_pending'] = UserCabinetRole.objects.filter(status='PENDING').count()
        
        # Add user and role counts to each cabinet
        for cabinet in context['cabinets']:
            cabinet.user_count = cabinet.user_roles.filter(
                status='APPROVED'
            ).count()
            cabinet.pending_count = cabinet.user_roles.filter(
                status='PENDING'
            ).count()
        
        return context


class CabinetDetailAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, DetailView):
    """
    Superadmin view to view cabinet details
    
    Features:
    - Show cabinet information
    - List all assigned users and their roles
    - Show pending assignments
    - Allow adding/removing users
    """
    model = Cabinet
    template_name = 'account/admin_cabinet_detail.html'
    context_object_name = 'cabinet'

    def get_header_title(self):
        return self.object.name

    def get_header_subtitle(self):
        return _("Détails du cabinet et affectations des utilisateurs")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinets_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': self.object.name, 'url': None},
        ]

    def get_header_actions(self):
        return [
            {
                'label': _("Modifier le cabinet"),
                'url': str(reverse_lazy('accounts:admin_cabinet_edit', kwargs={'pk': self.object.pk})),
                'icon': 'edit',
                'class': 'btn-falcon-default',
            },
            {
                'label': _("Ajouter un utilisateur"),
                'url': str(reverse_lazy('accounts:admin_assign_user_to_cabinet', kwargs={'cabinet_id': self.object.pk})),
                'icon': 'user-plus',
                'class': 'btn-falcon-success',
            },
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabinet = self.object

        # Get all user roles for this cabinet
        all_roles = cabinet.user_roles.select_related('user').order_by('-status', 'user__username')
        
        # Separate by status
        context['approved_roles'] = all_roles.filter(status='APPROVED')
        context['pending_roles'] = all_roles.filter(status='PENDING')
        context['rejected_roles'] = all_roles.filter(status='REJECTED')
        
        # Statistics
        context['total_users'] = all_roles.count()
        context['approved_users'] = context['approved_roles'].count()
        context['pending_users'] = context['pending_roles'].count()
        context['rejected_users'] = context['rejected_roles'].count()
        
        return context


class CabinetCreateView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, CreateView):
    """
    Superadmin view to create new cabinet
    
    Features:
    - Create new cabinet with information
    - Auto-redirect to detail page
    - Success message on creation
    """
    model = Cabinet
    form_class = CabinetForm
    template_name = 'account/admin_cabinet_form.html'
    header_title = _("Créer un nouveau cabinet")
    header_subtitle = _("Ajoutez un nouveau cabinet au système")
    back_url = reverse_lazy('accounts:admin_cabinets_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': _("Nouveau cabinet"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['submit_label'] = _('Create Cabinet')
        return context

    def get_success_url(self):
        messages.success(self.request, _('Cabinet created successfully.'))
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk})


class CabinetUpdateView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, UpdateView):
    """
    Superadmin view to edit cabinet information
    
    Features:
    - Edit cabinet details
    - Update logo and address
    - Auto-redirect to detail page
    """
    model = Cabinet
    form_class = CabinetForm
    template_name = 'account/admin_cabinet_form.html'

    def get_header_title(self):
        return _("Modifier le cabinet : %(name)s") % {'name': self.object.name}

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['submit_label'] = _('Update Cabinet')
        return context

    def get_success_url(self):
        messages.success(self.request, _('Cabinet updated successfully.'))
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk})


class CabinetDeleteView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, DeleteView):
    """
    Superadmin view to delete cabinet
    
    Features:
    - Confirm deletion
    - Redirect to cabinet list
    - Warning about related data
    """
    model = Cabinet
    template_name = 'account/admin_cabinet_confirm_delete.html'
    success_url = reverse_lazy('accounts:admin_cabinets_list')

    def get_header_title(self):
        return _("Supprimer le cabinet : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return _("Cette action supprimera définitivement le cabinet et toutes les données associées.")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Supprimer"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabinet = self.object
        context['user_count'] = cabinet.user_roles.count()
        context['approved_count'] = cabinet.user_roles.filter(status='APPROVED').count()
        context['pending_count'] = cabinet.user_roles.filter(status='PENDING').count()
        # Cascade warning: show what will be destroyed
        context['site_count'] = Site.objects.filter(cabinet=cabinet).count()
        context['expense_count'] = Expense.objects.filter(site__cabinet=cabinet).count()
        context['invoice_count'] = Invoice.objects.filter(contract__site__cabinet=cabinet).count()
        return context

    def delete(self, request, *args, **kwargs):
        messages.success(
            request,
            _('Cabinet deleted successfully.')
        )
        return super().delete(request, *args, **kwargs)


class AssignUserToCabinetFromDetailView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, CreateView):
    """
    Superadmin view to assign a user to a cabinet from the cabinet detail page.
    The cabinet is fixed from the URL; the form presents a user dropdown.
    """
    model = UserCabinetRole
    form_class = AssignUserToCabinetFromCabinetForm
    template_name = 'account/admin_assign_user_to_cabinet.html'

    def get_cabinet(self):
        if not hasattr(self, '_cabinet'):
            self._cabinet = get_object_or_404(Cabinet, pk=self.kwargs['cabinet_id'])
        return self._cabinet

    def get_header_title(self):
        return _("Ajouter un utilisateur à : %(name)s") % {'name': self.get_cabinet().name}

    def get_header_subtitle(self):
        return _("Assignez un utilisateur et un rôle à ce cabinet")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.kwargs['cabinet_id']}))

    def get_breadcrumb_items(self):
        cabinet = self.get_cabinet()
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': cabinet.name, 'url': str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet.pk}))},
            {'title': _("Ajouter un utilisateur"), 'url': None},
        ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['cabinet'] = self.get_cabinet()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cabinet'] = self.get_cabinet()
        return context

    def form_valid(self, form):
        messages.success(self.request, _('User assigned to cabinet successfully.'))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.kwargs['cabinet_id']})


class CabinetUserRoleUpdateView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, UpdateView):
    """
    Superadmin view to edit user role in cabinet
    
    Features:
    - Change user's role in cabinet
    - Change approval status
    - Redirect back to cabinet detail
    """
    model = UserCabinetRole
    form_class = AssignRoleToCabinetUserForm
    template_name = 'account/admin_cabinet_user_role_form.html'

    def get_header_title(self):
        return _("Modifier le rôle : %(name)s") % {'name': self.object.user.username}

    def get_header_subtitle(self):
        return _("Cabinet : %(name)s") % {'name': self.object.cabinet.name}

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.cabinet.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': self.object.cabinet.name, 'url': str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.cabinet.pk}))},
            {'title': _("Modifier le rôle"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.object.user
        context['cabinet'] = self.object.cabinet
        return context

    def get_success_url(self):
        cabinet_id = self.object.cabinet.pk
        messages.success(self.request, _('User role updated successfully.'))
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet_id})


class CabinetUserRoleDeleteView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, DeleteView):
    """
    Superadmin view to remove user from cabinet
    
    Features:
    - Delete user's cabinet assignment
    - Confirm deletion
    - Redirect back to cabinet detail
    """
    model = UserCabinetRole
    template_name = 'account/admin_cabinet_user_role_confirm_delete.html'

    def get_header_title(self):
        return _("Retirer %(user)s de %(cabinet)s") % {'user': self.object.user.username, 'cabinet': self.object.cabinet.name}

    def get_header_subtitle(self):
        return _("Cette action révoquera l'accès de l'utilisateur à ce cabinet.")

    def get_back_url(self):
        return str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.cabinet.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Cabinets"), 'url': str(reverse_lazy('accounts:admin_cabinets_list'))},
            {'title': self.object.cabinet.name, 'url': str(reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.cabinet.pk}))},
            {'title': _("Retirer l'utilisateur"), 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.object.user
        context['cabinet'] = self.object.cabinet
        context['role_display'] = self.object.get_role_display()
        return context

    def get_success_url(self):
        cabinet_id = self.object.cabinet.pk
        messages.success(self.request, _('User removed from cabinet successfully.'))
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet_id})


class CabinetUserRoleQuickStatusView(LoginRequiredMixin, IsSuperAdminMixin, View):
    """
    SUPERADMIN ONLY: One-click approve/reject for a cabinet role assignment
    — the fast path for the common case, without opening the full edit
    form. POST-only, status passed as a form field ('APPROVED'/'REJECTED').
    """

    def post(self, request, pk):
        role = get_object_or_404(UserCabinetRole, pk=pk)
        new_status = request.POST.get('status', '')
        valid_statuses = dict(ApprovalStatus.choices)

        if new_status not in valid_statuses:
            messages.error(request, _('Invalid status.'))
        else:
            role.status = new_status
            role.save(update_fields=['status'])
            messages.success(
                request,
                _('{user} is now {status} for {cabinet}.').format(
                    user=role.user.username,
                    status=valid_statuses[new_status],
                    cabinet=role.cabinet.name,
                )
            )
        return redirect(request.META.get('HTTP_REFERER') or reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': role.cabinet.pk}))


class RoleAssignmentListAdminView(LoginRequiredMixin, IsSuperAdminMixin, PageHeaderMixin, ListView):
    """
    SUPERADMIN ONLY: System-wide view of every cabinet role assignment,
    across all cabinets — answers "show me every DIRECTOR" or "show me
    every pending request" without going cabinet-by-cabinet.
    """
    model = UserCabinetRole
    template_name = 'account/admin_role_assignments_list.html'
    context_object_name = 'roles'
    paginate_by = 50
    header_title = _("Affectations de rôles")
    header_subtitle = _("Vue globale de tous les rôles attribués, tous cabinets confondus")
    back_url = reverse_lazy('accounts:admin_cabinets_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Admin"), 'url': None},
            {'title': _("Rôles"), 'url': None},
        ]

    def get_queryset(self):
        qs = UserCabinetRole.objects.select_related('user', 'cabinet').order_by('cabinet__name', '-status', 'user__username')

        search = self.request.GET.get('search', '')
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(cabinet__name__icontains=search)
            )

        role = self.request.GET.get('role', '')
        if role:
            qs = qs.filter(role=role)

        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)

        cabinet_id = self.request.GET.get('cabinet', '')
        if cabinet_id:
            qs = qs.filter(cabinet_id=cabinet_id)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['role_filter'] = self.request.GET.get('role', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['cabinet_filter'] = self.request.GET.get('cabinet', '')
        context['role_choices'] = UserRoles.choices
        context['status_choices'] = ApprovalStatus.choices
        context['cabinets'] = Cabinet.objects.order_by('name')
        context['total_pending'] = UserCabinetRole.objects.filter(status=ApprovalStatus.PENDING).count()
        return context

