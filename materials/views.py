from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import Material, MaterialRequest
from .forms import MaterialForm, MaterialRequestForm
from projects.models import Site
from core.mixins import RoleRequiredMixin, PageHeaderMixin

# Material Catalog Views
class MaterialListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    model = Material
    template_name = 'materials/material_list.html'
    context_object_name = 'materials'
    paginate_by = 50
    header_title = "Logistics: Material Catalog"
    header_subtitle = "Browse and manage available construction materials"
    
    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=['DIRECTOR', 'CHIEF_ENGINEER']
        ).exists():
            return [{
                'label': 'Add Material',
                'url': str(reverse_lazy('materials:material_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class MaterialCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    success_url = reverse_lazy('materials:material_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = "Add New Material"
    header_subtitle = "Define a new item in the material catalog"
    back_url = reverse_lazy('materials:material_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Logistics', 'url': str(reverse_lazy('materials:material_list'))},
            {'title': 'New Material', 'url': None},
        ]

class MaterialUpdateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    success_url = reverse_lazy('materials:material_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    
    def get_header_title(self):
        return f"Edit: {self.object.name}"

    def get_back_url(self):
        return str(reverse_lazy('materials:material_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Logistics', 'url': str(reverse_lazy('materials:material_list'))},
            {'title': 'Edit Material', 'url': None},
        ]

# Material Request Views
class MaterialRequestListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    model = MaterialRequest
    template_name = 'materials/request_list.html'
    context_object_name = 'requests'
    header_title = "Material Requests"
    header_subtitle = "Monitor and manage site-specific material logistics"

    def get_header_actions(self):
        return [{
            'label': 'New Request',
            'url': str(reverse_lazy('materials:request_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'material', 'requested_by')
        if not self.request.user.is_staff:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)
        return qs.order_by('-created_at')

class MaterialRequestCreateView(LoginRequiredMixin, PageHeaderMixin, CreateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    success_url = reverse_lazy('materials:request_list')
    header_title = "New Material Request"
    header_subtitle = "Request items from the catalog for a project site"
    back_url = reverse_lazy('materials:request_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Requests', 'url': str(reverse_lazy('materials:request_list'))},
            {'title': 'New Request', 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.request.GET.get('site')
        if site_id:
            initial['site'] = site_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        messages.success(self.request, "Material request submitted.")
        return super().form_valid(form)

class MaterialRequestDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    model = MaterialRequest
    template_name = 'materials/request_detail.html'
    context_object_name = 'req'

    def get_header_title(self):
        return f"Request: {self.object.material.name}"

    def get_header_subtitle(self):
        return f"Qty: {self.object.quantity} {self.object.material.unit} | Site: {self.object.site.name}"

    def get_back_url(self):
        return str(reverse_lazy('materials:request_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Requests', 'url': str(reverse_lazy('materials:request_list'))},
            {'title': f"REQ-{self.object.id}", 'url': None},
        ]

def approve_material_request(request, pk):
    if request.method == 'POST':
        mat_request = get_object_or_404(MaterialRequest, pk=pk)
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=mat_request.site.cabinet, role__in=['DIRECTOR', 'CHIEF_ENGINEER']).exists():
            action = request.POST.get('action')
            if action == 'approve':
                mat_request.status = MaterialRequest.Status.APPROVED
                messages.success(request, "Material request approved.")
            elif action == 'reject':
                mat_request.status = MaterialRequest.Status.REJECTED
                messages.error(request, "Material request rejected.")
            mat_request.save()
        else:
            messages.error(request, "Unauthorized.")
        return redirect('materials:request_detail', pk=pk)
    return redirect('materials:request_list')
