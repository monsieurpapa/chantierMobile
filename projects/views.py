from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import Site, ProjectPhase, SiteProgress
from .forms import SiteForm, ProjectPhaseForm, SiteProgressForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin
from chantiermobile.constants import UserRoles

class SiteListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Site
    template_name = 'projects/site_list.html'
    context_object_name = 'sites'
    ordering = ['-created_at']
    header_title = "Projects & Sites"
    header_subtitle = "Manage and track all active construction projects"
    
    def get_header_actions(self):
        # We can't easily use rbac_tags here, so we use UserCabinetRole logic
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, 
            role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': 'Create New Site',
                'url': str(reverse_lazy('projects:site_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class SiteCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = "Register New Site"
    header_subtitle = "Enter site details to begin tracking"
    back_url = reverse_lazy('projects:site_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': 'New Site', 'url': None},
        ]

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
             messages.error(self.request, "You must belong to a Cabinet to create a site.")
             return self.form_invalid(form)
             
        form.instance.cabinet = cabinet
        messages.success(self.request, "Site created successfully!")
        return super().form_valid(form)

class SiteUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Site
    form_class = SiteForm
    template_name = 'projects/site_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_header_title(self):
        return f"Edit Site: {self.object.name}"

    def get_header_subtitle(self):
        return self.object.location

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': 'Edit', 'url': None},
        ]

    def form_valid(self, form):
        from django.core.exceptions import ValidationError
        from django.db import transaction
        from core.models import StatusChangeLog
        old_status = self.object.status
        try:
            form.instance.full_clean()
            with transaction.atomic():
                form.save()
                self.object = form.instance
                if old_status != self.object.status:
                    StatusChangeLog.log(
                        self.object,
                        changed_by=self.request.user,
                        old_status=old_status,
                        new_status=self.object.status,
                    )
            messages.success(self.request, "Site updated successfully!")
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(self.get_success_url())
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id})

class SiteDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DeleteView):
    model = Site
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    success_url = reverse_lazy('projects:site_list')
    allowed_roles = ['DIRECTOR']

    def get_header_title(self):
        return f"Delete Site: {self.object.name}"

    def get_header_subtitle(self):
        return "This action cannot be undone."

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))},
            {'title': 'Delete', 'url': None},
        ]

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Site deleted successfully!")
        return super().delete(request, *args, **kwargs)

class SiteDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Site
    template_name = 'projects/site_detail.html'
    context_object_name = 'site'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'

    def get_header_title(self):
        return self.object.name

    def get_header_subtitle(self):
        return self.object.location

    def get_back_url(self):
        return str(reverse_lazy('projects:site_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.name, 'url': None},
        ]

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        user = self.request.user
        actions = []
        
        is_admin = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists()
        
        is_director = user.is_superuser or UserCabinetRole.objects.filter(
            user=user, role='DIRECTOR'
        ).exists()

        if is_admin:
            actions.append({
                'label': 'Edit Site',
                'url': str(reverse_lazy('projects:site_update', kwargs={'unique_id': self.object.unique_id})),
                'icon': 'edit',
                'class': 'btn-falcon-default'
            })
        
        if is_director:
            actions.append({
                'label': 'Delete',
                'url': str(reverse_lazy('projects:site_delete', kwargs={'unique_id': self.object.unique_id})),
                'icon': 'trash-alt',
                'class': 'btn-falcon-danger'
            })
            
        return actions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use self.object (already fetched by DetailView.get) — avoids a duplicate DB query
        site = self.object

        # Financial context
        expenses_qs = site.expenses.select_related('category', 'requester').order_by('-created_at')
        context['expenses'] = expenses_qs
        context['contract'] = getattr(site, 'contract', None)
        if context['contract']:
            context['invoices'] = context['contract'].invoices.all().order_by('-issued_date')

        # Unified Timeline / History
        # We collect different types of events and tag them for the template
        timeline = []

        # 1. Progress Reports
        for progress in SiteProgress.objects.filter(phase__site=site).select_related('phase'):
            timeline.append({
                'type': 'PROGRESS',
                'date': progress.report_date,
                'timestamp': progress.created_at,
                'title': f"Progress logged for {progress.phase.name}",
                'content': f"Completed: {progress.percentage_complete}% - {progress.description}",
                'icon': 'fas fa-chart-line',
                'color': 'primary'
            })

        # 2. Expenses — reuse the already-evaluated queryset, no second DB round-trip
        for expense in expenses_qs:
            timeline.append({
                'type': 'EXPENSE',
                'date': expense.created_at.date(),
                'timestamp': expense.created_at,
                'title': f"Expense Request: {expense.category.name}",
                'content': f"Amount: ${expense.amount} - Status: {expense.get_status_display()}",
                'icon': 'fas fa-money-bill-wave',
                'color': 'warning'
            })
            
        # 3. Material Requests
        for req in site.material_requests.all().select_related('requested_by').prefetch_related('items__material'):
            timeline.append({
                'type': 'MATERIAL',
                'date': req.created_at.date(),
                'timestamp': req.created_at,
                'title': f"Material Request #{req.id}",
                'content': f"{req.total_items} item(s) - Status: {req.get_status_display()}",
                'icon': 'fas fa-boxes',
                'color': 'info'
            })

        # Sort combined timeline by timestamp descending
        context['timeline'] = sorted(timeline, key=lambda x: x['timestamp'], reverse=True)
        
        return context


# --- PHASES ---

class ProjectPhaseCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def dispatch(self, request, *args, **kwargs):
        self.site = get_object_or_404(Site, unique_id=self.kwargs.get('site_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_header_title(self):
        return f"Add Phase: {self.site.name}"

    def get_header_subtitle(self):
        return "Define a new construction phase for this project"

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id}))},
            {'title': 'Add Phase', 'url': None},
        ]

    def form_valid(self, form):
        form.instance.site = self.site
        messages.success(self.request, f"Phase '{form.instance.name}' added to project.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.site
        return context

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.site.unique_id})

class ProjectPhaseUpdateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, UpdateView):
    model = ProjectPhase
    form_class = ProjectPhaseForm
    template_name = 'projects/phase_form.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_header_title(self):
        return f"Edit Phase: {self.object.name}"

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))},
            {'title': 'Edit Phase', 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site'] = self.object.site
        return context

    def get_success_url(self):
        messages.success(self.request, "Phase updated.")
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class ProjectPhaseDeleteView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, DeleteView):
    model = ProjectPhase
    template_name = 'projects/confirm_delete.html'
    slug_field = 'unique_id'
    slug_url_kwarg = 'unique_id'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

    def get_header_title(self):
        return f"Delete Phase: {self.object.name}"

    def get_header_subtitle(self):
        return "This action cannot be undone."

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.object.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id}))},
            {'title': 'Delete Phase', 'url': None},
        ]

    def get_success_url(self):
        messages.success(self.request, "Phase deleted.")
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})


# --- PROGRESS ---

class SiteProgressCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = SiteProgress
    form_class = SiteProgressForm
    template_name = 'projects/progress_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']

    def dispatch(self, request, *args, **kwargs):
        self.phase = get_object_or_404(ProjectPhase, unique_id=self.kwargs.get('phase_id'))
        return super().dispatch(request, *args, **kwargs)

    def get_header_title(self):
        return f"Log Progress: {self.phase.name}"

    def get_header_subtitle(self):
        return f"Project: {self.phase.site.name}"

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id}))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Projects & Sites', 'url': str(reverse_lazy('projects:site_list'))},
            {'title': self.phase.site.name, 'url': str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id}))},
            {'title': 'Log Progress', 'url': None},
        ]

    def form_valid(self, form):
        form.instance.phase = self.phase
        messages.success(self.request, "Progress report logged.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phase'] = self.phase
        return context

    def get_success_url(self):
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.phase.site.unique_id})
