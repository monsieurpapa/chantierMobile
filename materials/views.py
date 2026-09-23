from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from .models import Material, MaterialRequest
from .forms import MaterialForm, MaterialRequestForm, MaterialRequestItemFormSet
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from core.quickcreate import QuickCreateView
from chantiermobile.constants import UserRoles, FINAL_AUTHORIZATION_ROLES

# État de besoin — two-stage approval: the magasinier validates first,
# then a Directeur Technique/Général (or Directeur de Cabinet, kept for
# single-cabinet setups without a dedicated DT/DG role) gives the final
# authorization.
MAGASINIER_VALIDATE_ROLES = ['MAGASINIER', 'DIRECTOR']

# Material Catalog Views
class MaterialListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    model = Material
    template_name = 'materials/material_list.html'
    context_object_name = 'materials'
    paginate_by = 50
    header_title = _("Catalogue des matériaux")
    header_subtitle = _("Parcourez et gérez les matériaux de construction disponibles")

    def get_queryset(self):
        return super().get_queryset().order_by('name')

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Ajouter un matériau"),
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
    header_title = _("Ajouter un nouveau matériau")
    header_subtitle = _("Définir un nouvel article dans le catalogue des matériaux")
    back_url = reverse_lazy('materials:material_list')

    def form_valid(self, form):
        from django.contrib import messages
        messages.success(self.request, _("Matériau '%(name)s' ajouté au catalogue avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)

    def get_breadcrumb_items(self):
        return [
            {'title': _("Logistique"), 'url': str(reverse_lazy('materials:material_list'))},
            {'title': _("Nouveau matériau"), 'url': None},
        ]

class MaterialUpdateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = 'materials/material_form.html'
    success_url = reverse_lazy('materials:material_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    
    def form_valid(self, form):
        from django.contrib import messages
        messages.success(self.request, _("Matériau '%(name)s' mis à jour avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)

    def get_header_title(self):
        return _("Modifier : %(name)s") % {'name': self.object.name}

    def get_back_url(self):
        return str(reverse_lazy('materials:material_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Logistique"), 'url': str(reverse_lazy('materials:material_list'))},
            {'title': _("Modifier le matériau"), 'url': None},
        ]

# Material Request Views
class MaterialRequestListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    model = MaterialRequest
    template_name = 'materials/request_list.html'
    context_object_name = 'requests'
    header_title = _("Demandes de matériaux")
    header_subtitle = _("Gérez la logistique des matériaux par chantier")

    def get_header_actions(self):
        return [{
            'label': _("Nouvelle demande"),
            'url': str(reverse_lazy('materials:request_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('items__material').select_related('site', 'requested_by')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(site__cabinet=active_cabinet)
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)
        return qs.order_by('-created_at')

class MaterialRequestCreateView(LoginRequiredMixin, PageHeaderMixin, CreateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    success_url = reverse_lazy('materials:request_list')
    header_title = _("Nouvelle demande de matériaux")
    header_subtitle = _("Demandez des articles du catalogue pour un chantier")
    back_url = reverse_lazy('materials:request_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Demandes"), 'url': str(reverse_lazy('materials:request_list'))},
            {'title': _("Nouvelle demande"), 'url': None},
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
            messages.success(self.request, _("Demande de matériaux soumise avec %(count)s article(s).") % {'count': self.object.total_items})
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

class MaterialRequestUpdateView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    success_url = reverse_lazy('materials:request_list')
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier la demande n°%(id)s") % {'id': self.object.id}

    def get_header_subtitle(self):
        return _("Chantier : %(name)s") % {'name': self.object.site.name}

    def get_back_url(self):
        return reverse_lazy('materials:request_detail', kwargs={'pk': self.object.pk})

    def get_breadcrumb_items(self):
        return [
            {'title': _("Demandes"), 'url': str(reverse_lazy('materials:request_list'))},
            {'title': f"REQ-{self.object.id}", 'url': str(reverse_lazy('materials:request_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

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
            self.object = form.save()
            items_formset.instance = self.object
            items_formset.save()
            messages.success(self.request, _("Demande de matériaux mise à jour avec %(count)s article(s).") % {'count': self.object.total_items})
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

class MaterialRequestDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = MaterialRequest
    template_name = 'materials/request_detail.html'
    context_object_name = 'req'
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('items__material')

    def get_header_title(self):
        return _("Demande n°%(id)s") % {'id': self.object.id}

    def get_header_subtitle(self):
        return _("Chantier : %(site)s | %(count)s article(s) | Statut : %(status)s") % {
            'site': self.object.site.name,
            'count': self.object.total_items,
            'status': self.object.get_status_display(),
        }

    def get_back_url(self):
        return str(reverse_lazy('materials:request_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Demandes"), 'url': str(reverse_lazy('materials:request_list'))},
            {'title': f"REQ-{self.object.id}", 'url': None},
        ]

@login_required
def request_validate(request, pk):
    """First stage: the magasinier (or a director) validates the état de
    besoin before it goes up for final authorization."""
    mat_request = get_object_or_404(MaterialRequest, pk=pk)
    if request.method != 'POST':
        return redirect('materials:request_detail', pk=pk)
    if not can_act_for_cabinet(request, mat_request.site.cabinet, MAGASINIER_VALIDATE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('materials:request_detail', pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'reject':
            mat_request.reject(request.user)
            messages.error(request, _("Demande de matériaux rejetée."))
        else:
            mat_request.magasinier_validate(request.user)
            messages.success(request, _("Demande validée — en attente d'autorisation finale."))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('materials:request_detail', pk=pk)


@login_required
def approve_material_request(request, pk):
    """Second/final stage: Directeur Technique/Général (or Directeur de
    Cabinet) authorizes a request the magasinier has already validated."""
    mat_request = get_object_or_404(MaterialRequest, pk=pk)
    if request.method != 'POST':
        return redirect('materials:request_list')
    if not can_act_for_cabinet(request, mat_request.site.cabinet, FINAL_AUTHORIZATION_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('materials:request_detail', pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'reject':
            mat_request.reject(request.user)
            messages.error(request, _("Demande de matériaux rejetée."))
        else:
            mat_request.authorize(request.user)
            if mat_request.expense_id:
                messages.success(request, _(
                    "Demande de matériaux autorisée — dépense EX-%(id)s créée (%(amount)s$), en attente de paiement."
                ) % {'id': mat_request.expense_id, 'amount': mat_request.expense.amount})
            else:
                messages.success(request, _(
                    "Demande de matériaux autorisée. Aucune dépense liée créée automatiquement (coût estimé indisponible) — enregistrez-la manuellement si nécessaire."
                ))
    except ValidationError as e:
        messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('materials:request_detail', pk=pk)


@login_required
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


class MaterialQuickCreateView(QuickCreateView):
    """Backs the "select or add a material" pickers (material request
    items, stock items). Material has no cabinet FK — it's a shared
    catalog across the whole system, matching how it's already used."""
    model = Material
    cabinet_scoped = False

    def build_instance(self, name, request, cabinet, payload):
        unit = (payload.get('unit') or '').strip() or _('unité')
        return Material(name=name, unit=unit)
