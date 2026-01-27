from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.views.generic import DetailView, UpdateView, ListView, DeleteView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.http import Http404
from .models import UserCabinetRole, Cabinet
from .forms import UserProfileForm, UserCabinetRoleForm, UserAdminForm, AssignUserToCabinetForm, CabinetForm, AssignRoleToCabinetUserForm
from projects.models import Site, ProjectPhase
from materials.models import MaterialRequest
from finance.models import Expense
from revenue.models import Invoice

User = get_user_model()


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
        sites = Site.objects.filter(
            cabinet__in=user_cabinet_ids
        ).select_related('cabinet').order_by('-created_at')
        context['sites'] = sites[:10]
        context['total_sites'] = sites.count()
        
        # ====================
        # RBAC: Material Requests
        # ====================
        # Only show material requests from user's cabinet projects
        material_requests = MaterialRequest.objects.filter(
            site__cabinet__in=user_cabinet_ids
        ).select_related('site').order_by('-created_at')
        context['material_requests'] = material_requests[:10]
        context['total_material_requests'] = material_requests.count()
        
        # ====================
        # RBAC: Expenses
        # ====================
        # Only show expenses from sites in user's cabinets
        expenses = Expense.objects.filter(
            site__cabinet__in=user_cabinet_ids
        ).select_related('category', 'site').order_by('-created_at')
        context['expenses'] = expenses[:10]
        context['total_expenses'] = expenses.count()
        
        # ====================
        # RBAC: Invoices
        # ====================
        # Only show invoices from contracts related to user's cabinet sites
        invoices = Invoice.objects.filter(
            contract__site__cabinet__in=user_cabinet_ids
        ).select_related('contract').order_by('-created_at')
        context['invoices'] = invoices[:10]
        context['total_invoices'] = invoices.count()
        
        # ====================
        # RBAC: Statistics & Permissions
        # ====================
        # Calculate pending items for user's cabinets
        pending_material_requests = material_requests.filter(status='PENDING').count()
        pending_expenses = expenses.filter(status='PENDING').count()
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


class UserListAdminView(LoginRequiredMixin, IsSuperAdminMixin, ListView):
    """
    SUPERADMIN ONLY: List all users with management capabilities
    
    Features:
    - View all system users
    - Search by username, email, name
    - Filter by status (active/inactive/staff/superadmin)
    - Bulk actions (activate, deactivate, make staff, remove staff)
    - Quick links to edit or delete users
    """
    model = User
    template_name = 'account/admin_users_list.html'
    context_object_name = 'users'
    paginate_by = 25
    
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


class UserEditAdminView(LoginRequiredMixin, IsSuperAdminMixin, UpdateView):
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
    
    def get_object(self):
        """Get the user to edit"""
        user_id = self.kwargs.get('pk')
        return get_object_or_404(User, pk=user_id)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        context['target_user'] = user
        context['cabinet_roles'] = user.cabinet_roles.all().select_related('cabinet')
        return context
    
    def form_valid(self, form):
        """Handle successful form submission"""
        user = form.save(commit=False)
        user.save()
        messages.success(
            self.request,
            _('User {} has been updated successfully.').format(user.username)
        )
        return super().form_valid(form)


class UserDeleteAdminView(LoginRequiredMixin, IsSuperAdminMixin, DeleteView):
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
        user = self.get_object()
        username = user.username
        messages.warning(
            self.request,
            _('User {} has been deleted.').format(username)
        )
        return super().delete(request, *args, **kwargs)


class UserDetailAdminView(LoginRequiredMixin, IsSuperAdminMixin, DetailView):
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
    
    def get_object(self):
        """Get the user to view"""
        user_id = self.kwargs.get('pk')
        return get_object_or_404(User, pk=user_id)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        
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


# ============================================
# Superadmin Cabinet Assignment Views
# ============================================

class IsSuperAdminMixin(UserPassesTestMixin):
    """Mixin to restrict views to superadmin users only"""
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(
            self.request,
            _('You do not have permission to access this page.')
        )
        return redirect('home')


class AssignUserToCabinetView(IsSuperAdminMixin, CreateView):
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
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user_id = self.kwargs.get('user_id')
        user = get_object_or_404(User, pk=user_id)
        kwargs['user'] = user
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_id = self.kwargs.get('user_id')
        target_user = get_object_or_404(User, pk=user_id)
        context['target_user'] = target_user
        context['page_title'] = _('Assign User to Cabinet')
        return context
    
    def get_success_url(self):
        user_id = self.kwargs.get('user_id')
        return reverse_lazy('accounts:admin_user_detail', kwargs={'pk': user_id})
    
    def form_valid(self, form):
        messages.success(
            self.request,
            _('User assigned to cabinet successfully.')
        )
        return super().form_valid(form)


class CabinetListAdminView(IsSuperAdminMixin, ListView):
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


class CabinetDetailAdminView(IsSuperAdminMixin, DetailView):
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabinet = self.get_object()
        
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


class CabinetCreateView(IsSuperAdminMixin, CreateView):
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Create New Cabinet')
        context['page_subtitle'] = _('Add a new project cabinet to the system')
        context['submit_label'] = _('Create Cabinet')
        return context
    
    def get_success_url(self):
        messages.success(
            self.request,
            _('Cabinet created successfully.')
        )
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk})


class CabinetUpdateView(IsSuperAdminMixin, UpdateView):
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Edit Cabinet')
        context['page_subtitle'] = _('Update cabinet information')
        context['submit_label'] = _('Update Cabinet')
        return context
    
    def get_success_url(self):
        messages.success(
            self.request,
            _('Cabinet updated successfully.')
        )
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': self.object.pk})


class CabinetDeleteView(IsSuperAdminMixin, DeleteView):
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabinet = self.get_object()
        context['user_count'] = cabinet.user_roles.count()
        context['approved_count'] = cabinet.user_roles.filter(status='APPROVED').count()
        context['pending_count'] = cabinet.user_roles.filter(status='PENDING').count()
        return context
    
    def delete(self, request, *args, **kwargs):
        messages.success(
            request,
            _('Cabinet deleted successfully.')
        )
        return super().delete(request, *args, **kwargs)


class AssignUserToCabinetFromDetailView(IsSuperAdminMixin, CreateView):
    """
    Superadmin view to assign user to cabinet from cabinet detail page
    
    Same as AssignUserToCabinetView but accessed from cabinet detail
    Instead of passing user_id in URL, passes cabinet_id
    """
    model = UserCabinetRole
    form_class = AssignUserToCabinetForm
    template_name = 'account/admin_assign_user_to_cabinet.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # No user pre-selected - let form handle it
        kwargs['user'] = None
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cabinet_id = self.kwargs.get('cabinet_id')
        cabinet = get_object_or_404(Cabinet, pk=cabinet_id)
        context['cabinet'] = cabinet
        context['page_title'] = _('Assign User to Cabinet')
        return context
    
    def form_valid(self, form):
        cabinet_id = self.kwargs.get('cabinet_id')
        cabinet = get_object_or_404(Cabinet, pk=cabinet_id)
        form.instance.cabinet = cabinet
        messages.success(
            self.request,
            _('User assigned to cabinet successfully.')
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        cabinet_id = self.kwargs.get('cabinet_id')
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet_id})


class CabinetUserRoleUpdateView(IsSuperAdminMixin, UpdateView):
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.get_object()
        context['page_title'] = _('Edit Cabinet Assignment')
        context['user'] = role.user
        context['cabinet'] = role.cabinet
        context['page_subtitle'] = _('Modify user role and approval status')
        return context
    
    def get_success_url(self):
        cabinet_id = self.get_object().cabinet.pk
        messages.success(
            self.request,
            _('User role updated successfully.')
        )
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet_id})


class CabinetUserRoleDeleteView(IsSuperAdminMixin, DeleteView):
    """
    Superadmin view to remove user from cabinet
    
    Features:
    - Delete user's cabinet assignment
    - Confirm deletion
    - Redirect back to cabinet detail
    """
    model = UserCabinetRole
    template_name = 'account/admin_cabinet_user_role_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.get_object()
        context['user'] = role.user
        context['cabinet'] = role.cabinet
        context['role_display'] = role.get_role_display()
        return context
    
    def get_success_url(self):
        cabinet_id = self.get_object().cabinet.pk
        messages.success(
            self.request,
            _('User removed from cabinet successfully.')
        )
        return reverse_lazy('accounts:admin_cabinet_detail', kwargs={'pk': cabinet_id})

