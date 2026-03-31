from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponseRedirect
from .models import Material, MaterialRequest
from .forms import MaterialForm, MaterialRequestForm, MaterialRequestItemFormSet
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
    
    def form_valid(self, form):
        from django.contrib import messages
        messages.success(self.request, f"Material '{form.instance.name}' added to catalog successfully!")
        return super().form_valid(form)
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
    
    def form_valid(self, form):
        from django.contrib import messages
        messages.success(self.request, f"Material '{form.instance.name}' updated successfully!")
        return super().form_valid(form)
    
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
        qs = super().get_queryset().prefetch_related('items__material').select_related('site', 'requested_by')
        if not self.request.user.is_superuser:
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
        if self.request.user.is_superuser:
            form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = MaterialRequestItemFormSet(self.request.POST, instance=self.object)
        else:
            context['items_formset'] = MaterialRequestItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context['items_formset']
        
        if items_formset.is_valid():
            form.instance.requested_by = self.request.user
            self.object = form.save()
            items_formset.instance = self.object
            items_formset.save()
            messages.success(self.request, f"Material request submitted with {self.object.total_items} item(s).")
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

class MaterialRequestUpdateView(LoginRequiredMixin, PageHeaderMixin, UpdateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    success_url = reverse_lazy('materials:request_list')
    
    def get_header_title(self):
        return f"Edit Request #{self.object.id}"

    def get_header_subtitle(self):
        return f"Site: {self.object.site.name}"

    def get_back_url(self):
        return reverse_lazy('materials:request_detail', kwargs={'pk': self.object.pk})

    def get_breadcrumb_items(self):
        return [
            {'title': 'Requests', 'url': str(reverse_lazy('materials:request_list'))},
            {'title': f"REQ-{self.object.id}", 'url': str(reverse_lazy('materials:request_detail', kwargs={'pk': self.object.pk}))},
            {'title': 'Edit', 'url': None},
        ]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = MaterialRequestItemFormSet(self.request.POST, instance=self.object)
        else:
            context['items_formset'] = MaterialRequestItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context['items_formset']
        
        if items_formset.is_valid():
            self.object = form.save()
            items_formset.instance = self.object
            items_formset.save()
            messages.success(self.request, f"Material request updated with {self.object.total_items} item(s).")
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

class MaterialRequestDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    model = MaterialRequest
    template_name = 'materials/request_detail.html'
    context_object_name = 'req'
    
    def get_queryset(self):
        return super().get_queryset().prefetch_related('items__material')

    def get_header_title(self):
        return f"Request #{self.object.id}"

    def get_header_subtitle(self):
        return f"Site: {self.object.site.name} | {self.object.total_items} item(s) | Status: {self.object.get_status_display()}"

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


def materials_data_api(request):
    """API endpoint to fetch material data (units and costs) for dynamic form"""
    from django.http import JsonResponse
    
    materials = Material.objects.all().values('id', 'name', 'unit', 'estimated_cost_per_unit')
    
    data = {}
    for material in materials:
        data[str(material['id'])] = {
            'name': material['name'],
            'unit': material['unit'],
            'cost_per_unit': float(material['estimated_cost_per_unit'] or 0)
        }
    
    return JsonResponse(data)
