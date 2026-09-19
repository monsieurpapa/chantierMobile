from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from .models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement
from .forms import (
    SupplierForm, StockItemForm,
    PurchaseOrderForm, PurchaseOrderLineFormSet,
    StockMovementForm,
)
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from projects.models import Site
from chantiermobile.constants import PurchaseOrderStatus, UserRoles


# --- Supplier views ---

class SupplierListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Supplier
    template_name = 'procurement/supplier_list.html'
    context_object_name = 'suppliers'
    cabinet_lookup_field = 'cabinet'
    header_title = _("Fournisseurs")
    header_subtitle = _("Gérez le répertoire des fournisseurs et sous-traitants de matériaux")

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Ajouter un fournisseur"),
                'url': str(reverse_lazy('procurement:supplier_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(cabinet__id__in=user_cabinet_ids)


class SupplierCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'procurement/supplier_form.html'
    success_url = reverse_lazy('procurement:supplier_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = _("Ajouter un fournisseur")
    header_subtitle = _("Enregistrez un nouveau fournisseur pour les commandes d'achats")
    back_url = reverse_lazy('procurement:supplier_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Fournisseurs"), 'url': str(reverse_lazy('procurement:supplier_list'))},
            {'title': _("Nouveau fournisseur"), 'url': None},
        ]

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Fournisseur '%(name)s' ajouté avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)


class SupplierUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'procurement/supplier_form.html'
    success_url = reverse_lazy('procurement:supplier_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'cabinet'

    def get_header_title(self):
        return _("Modifier : %(name)s") % {'name': self.object.name}

    def get_back_url(self):
        return str(reverse_lazy('procurement:supplier_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Fournisseurs"), 'url': str(reverse_lazy('procurement:supplier_list'))},
            {'title': _("Modifier le fournisseur"), 'url': None},
        ]

    def form_valid(self, form):
        messages.success(self.request, _("Fournisseur '%(name)s' mis à jour avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)


# --- Stock item views ---

class StockItemListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = StockItem
    template_name = 'procurement/stock_item_list.html'
    context_object_name = 'stock_items'
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Stocks")
    header_subtitle = _("Suivez les quantités disponibles par chantier")

    def get_header_actions(self):
        return [{
            'label': _("Ajouter un article"),
            'url': str(reverse_lazy('procurement:stock_item_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'material')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(site__cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(site__cabinet__id__in=user_cabinet_ids)


class StockItemCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = StockItem
    form_class = StockItemForm
    template_name = 'procurement/stock_item_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = _("Ajouter un article de stock")
    header_subtitle = _("Suivez un nouvel article pour un chantier")
    back_url = reverse_lazy('procurement:stock_item_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Stocks"), 'url': str(reverse_lazy('procurement:stock_item_list'))},
            {'title': _("Nouvel article"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Article '%(name)s' ajouté au stock avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('procurement:stock_item_detail', kwargs={'pk': self.object.pk})


class StockItemUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = StockItem
    form_class = StockItemForm
    template_name = 'procurement/stock_item_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier : %(name)s") % {'name': self.object.name}

    def get_back_url(self):
        return str(reverse_lazy('procurement:stock_item_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Stocks"), 'url': str(reverse_lazy('procurement:stock_item_list'))},
            {'title': self.object.name, 'url': str(reverse_lazy('procurement:stock_item_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Article '%(name)s' mis à jour avec succès !") % {'name': form.instance.name})
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('procurement:stock_item_detail', kwargs={'pk': self.object.pk})


class StockItemDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = StockItem
    template_name = 'procurement/stock_item_detail.html'
    context_object_name = 'stock_item'
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        return super().get_queryset().select_related('site', 'material').prefetch_related('movements')

    def get_header_title(self):
        return _("Article : %(name)s") % {'name': self.object.name}

    def get_header_subtitle(self):
        return _("Chantier : %(site)s | En stock : %(qty)s %(unit)s") % {
            'site': self.object.site.name,
            'qty': self.object.quantity_on_hand,
            'unit': self.object.unit,
        }

    def get_back_url(self):
        return str(reverse_lazy('procurement:stock_item_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Stocks"), 'url': str(reverse_lazy('procurement:stock_item_list'))},
            {'title': self.object.name, 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['movement_form'] = StockMovementForm()
        return context


@login_required
def stock_movement_create(request, pk):
    """Record a manual stock movement (entry, exit, or correction) against
    a StockItem — receipts from a PurchaseOrder go through
    PurchaseOrder.receive() instead."""
    stock_item = get_object_or_404(StockItem, pk=pk)
    if request.method == 'POST':
        form = StockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.stock_item = stock_item
            movement.moved_by = request.user
            try:
                movement.full_clean()
                movement.save()
                messages.success(request, _("Mouvement de stock enregistré."))
            except ValidationError as e:
                messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
        else:
            messages.error(request, _("Impossible d'enregistrer ce mouvement : vérifiez les champs."))
    return redirect('procurement:stock_item_detail', pk=pk)


# --- Purchase order views ---

class PurchaseOrderListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_list.html'
    context_object_name = 'purchase_orders'
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Bons de commande")
    header_subtitle = _("Gérez les commandes passées auprès des fournisseurs")

    def get_header_actions(self):
        return [{
            'label': _("Nouvelle commande"),
            'url': str(reverse_lazy('procurement:purchase_order_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'supplier').prefetch_related('lines')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(site__cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(site__cabinet__id__in=user_cabinet_ids)


class PurchaseOrderCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'procurement/purchase_order_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
    header_title = _("Créer un bon de commande")
    header_subtitle = _("Commandez des matériaux ou équipements auprès d'un fournisseur")
    back_url = reverse_lazy('procurement:purchase_order_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bons de commande"), 'url': str(reverse_lazy('procurement:purchase_order_list'))},
            {'title': _("Nouvelle commande"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.kwargs.get('site_id')
        if site_id:
            initial['site'] = get_object_or_404(Site, unique_id=site_id)
        return initial

    def _scope_form_querysets(self, form):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            site_qs = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
            supplier_qs = Supplier.objects.filter(cabinet=active_cabinet) if active_cabinet else Supplier.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            site_qs = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
            supplier_qs = Supplier.objects.filter(cabinet__id__in=user_cabinet_ids)
        form.fields['site'].queryset = site_qs
        form.fields['supplier'].queryset = supplier_qs
        return form

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return self._scope_form_querysets(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = PurchaseOrderLineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = PurchaseOrderLineFormSet(instance=self.object)
        # Restrict the stock_item choices on each line form to the same cabinet
        stock_qs = StockItem.objects.all()
        if not self.request.user.is_superuser:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            stock_qs = stock_qs.filter(site__cabinet__id__in=user_cabinet_ids)
        for lform in context['lines_formset'].forms:
            lform.fields['stock_item'].queryset = stock_qs
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("Commande '%(num)s' créée avec %(count)s ligne(s).") % {
                'num': self.object.order_number, 'count': self.object.total_items,
            })
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('procurement:purchase_order_detail', kwargs={'pk': self.object.pk})


class PurchaseOrderUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'procurement/purchase_order_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier la commande : %(num)s") % {'num': self.object.order_number}

    def get_back_url(self):
        return str(reverse_lazy('procurement:purchase_order_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bons de commande"), 'url': str(reverse_lazy('procurement:purchase_order_list'))},
            {'title': self.object.order_number, 'url': str(reverse_lazy('procurement:purchase_order_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def _scope_form_querysets(self, form):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            site_qs = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
            supplier_qs = Supplier.objects.filter(cabinet=active_cabinet) if active_cabinet else Supplier.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            site_qs = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
            supplier_qs = Supplier.objects.filter(cabinet__id__in=user_cabinet_ids)
        form.fields['site'].queryset = site_qs
        form.fields['supplier'].queryset = supplier_qs
        return form

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return self._scope_form_querysets(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = PurchaseOrderLineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = PurchaseOrderLineFormSet(instance=self.object)
        stock_qs = StockItem.objects.all()
        if not self.request.user.is_superuser:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            stock_qs = stock_qs.filter(site__cabinet__id__in=user_cabinet_ids)
        for lform in context['lines_formset'].forms:
            lform.fields['stock_item'].queryset = stock_qs
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("Commande mise à jour avec succès."))
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('procurement:purchase_order_detail', kwargs={'pk': self.object.pk})


class PurchaseOrderDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_detail.html'
    context_object_name = 'purchase_order'
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        return super().get_queryset().select_related('site', 'supplier').prefetch_related('lines__stock_item')

    def get_header_title(self):
        return _("Commande : %(num)s") % {'num': self.object.order_number}

    def get_header_subtitle(self):
        return _("Fournisseur : %(supplier)s | Total : %(total)s | Statut : %(status)s") % {
            'supplier': self.object.supplier.name,
            'total': self.object.total_ht,
            'status': self.object.get_status_display(),
        }

    def get_back_url(self):
        return str(reverse_lazy('procurement:purchase_order_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bons de commande"), 'url': str(reverse_lazy('procurement:purchase_order_list'))},
            {'title': self.object.order_number, 'url': None},
        ]

    def get_header_actions(self):
        actions = []
        if self.object.status == PurchaseOrderStatus.BROUILLON:
            actions.append({
                'label': _("Modifier"),
                'url': str(reverse_lazy('procurement:purchase_order_update', kwargs={'pk': self.object.pk})),
                'icon': 'edit',
                'class': 'btn-falcon-secondary'
            })
        return actions


@login_required
def purchase_order_send(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        if po.status == PurchaseOrderStatus.BROUILLON:
            po.status = PurchaseOrderStatus.ENVOYEE
            try:
                po.full_clean()
                po.save()
                messages.success(request, _("Commande envoyée au fournisseur."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Seule une commande en brouillon peut être envoyée."))
    return redirect('procurement:purchase_order_detail', pk=pk)


@login_required
def purchase_order_receive(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        try:
            po.receive(changed_by=request.user)
            messages.success(request, _("Réception enregistrée pour la commande %(num)s.") % {'num': po.order_number})
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('procurement:purchase_order_detail', pk=pk)


@login_required
def purchase_order_cancel(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        if po.status in [PurchaseOrderStatus.BROUILLON, PurchaseOrderStatus.ENVOYEE]:
            po.status = PurchaseOrderStatus.ANNULEE
            try:
                po.full_clean()
                po.save()
                messages.success(request, _("Commande annulée."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Cette commande ne peut pas être annulée dans son statut actuel."))
    return redirect('procurement:purchase_order_detail', pk=pk)
