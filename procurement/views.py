from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement, SupplierCredit
from .forms import (
    SupplierForm, StockItemForm,
    PurchaseOrderForm, PurchaseOrderLineFormSet,
    StockMovementForm, StockTransferForm, TransferProofForm, SupplierCreditForm, SupplierCreditPaymentForm,
)
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from core.quickcreate import QuickCreateView
from projects.models import Site, ProjectPhase
from chantiermobile.constants import PurchaseOrderStatus, UserRoles, CaisseType, StockMovementType, StockReportPeriod

# Mirrors StockItemCreateView/PurchaseOrderCreateView's allowed_roles and
# the has_role gate on the corresponding detail templates. MAGASINIER can
# record stock entries/exits (their core job) but not create/edit the
# StockItem catalog entry itself, nor create purchase orders.
STOCK_ACTION_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'MAGASINIER']
PURCHASE_ORDER_ACTION_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
# La caissière saisit la preuve de virement envoyée par le financier.
TRANSFER_ENTRY_ROLES = ['DIRECTOR', 'CASHIER']
# Le financier (ou un directeur) valide.
TRANSFER_VALIDATE_ROLES = ['DIRECTOR', 'FINANCIER']
CREDIT_MANAGE_ROLES = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER', 'FINANCIER']


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
        context['movement_form'] = StockMovementForm(stock_item=self.object)
        context['transfer_form'] = StockTransferForm(source_site=self.object.site)
        return context


@login_required
def stock_movement_create(request, pk):
    """Record a manual stock movement (entry, exit, or correction) against
    a StockItem — receipts from a PurchaseOrder go through
    PurchaseOrder.receive() instead, and inter-site moves go through
    stock_transfer_create() so both legs of the audit trail are created
    together."""
    stock_item = get_object_or_404(StockItem, pk=pk)
    if request.method == 'POST':
        if not can_act_for_cabinet(request, stock_item.site.cabinet, STOCK_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('procurement:stock_item_detail', pk=pk)
        form = StockMovementForm(request.POST, request.FILES, stock_item=stock_item)
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


@login_required
def stock_transfer_create(request, pk):
    """Transfer stock from this StockItem to the same material at another
    site of the same cabinet — creates the matching StockItem there if it
    doesn't already exist, and both legs of the movement atomically."""
    source = get_object_or_404(StockItem, pk=pk)
    if request.method != 'POST':
        return redirect('procurement:stock_item_detail', pk=pk)
    if not can_act_for_cabinet(request, source.site.cabinet, STOCK_ACTION_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:stock_item_detail', pk=pk)
    form = StockTransferForm(request.POST, source_site=source.site)
    if form.is_valid():
        destination_site = form.cleaned_data['destination_site']
        destination, _created = StockItem.objects.get_or_create(
            site=destination_site, name=source.name,
            defaults={'material': source.material, 'unit': source.unit},
        )
        try:
            source.transfer_to(
                destination, form.cleaned_data['quantity'], request.user,
                motif=form.cleaned_data.get('motif', ''), notes=form.cleaned_data.get('notes', ''),
            )
            messages.success(request, _("Transfert enregistré vers %(site)s.") % {'site': destination_site.name})
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    else:
        messages.error(request, _("Impossible d'enregistrer ce transfert : vérifiez les champs."))
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
        return [
            {
                'label': _("Nouvelle commande"),
                'url': str(reverse_lazy('procurement:purchase_order_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            },
            {
                'label': _("Rapport des achats"),
                'url': str(reverse_lazy('procurement:achats_report')),
                'icon': 'file-alt',
                'class': 'btn-falcon-default'
            },
        ]

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
        if not can_act_for_cabinet(request, po.site.cabinet, PURCHASE_ORDER_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('procurement:purchase_order_detail', pk=pk)
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
        if not can_act_for_cabinet(request, po.site.cabinet, PURCHASE_ORDER_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('procurement:purchase_order_detail', pk=pk)
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
        if not can_act_for_cabinet(request, po.site.cabinet, PURCHASE_ORDER_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('procurement:purchase_order_detail', pk=pk)
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


# Roles that may view the Achats/Caisse report and export it to PDF.
ACHATS_REPORT_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT', 'CASHIER']


def _achats_report_queryset(request):
    """Shared filtering for the achats report view and its PDF export:
    cabinet-scoped, optionally filtered by caisse, site, and order_date
    range/period. A caisse is shared across every chantier of the cabinet
    (it isn't site-scoped), so the site filter narrows the report without
    implying the caisse itself belongs to one site."""
    qs = PurchaseOrder.objects.select_related('site', 'supplier').prefetch_related('lines').order_by('-order_date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

    caisse = request.GET.get('caisse')
    if caisse:
        qs = qs.filter(caisse=caisse)

    site_id = request.GET.get('site')
    if site_id:
        qs = qs.filter(site_id=site_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(order_date__gte=date_from)
    if date_to:
        qs = qs.filter(order_date__lte=date_to)

    period = request.GET.get('period')
    today = timezone.localdate()
    if period == 'week':
        qs = qs.filter(order_date__gte=today - timezone.timedelta(days=7))
    elif period == 'month':
        qs = qs.filter(order_date__gte=today.replace(day=1))

    return qs


class AchatsReportView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Filterable purchases (achats) report — by caisse, by chantier, by
    date range/period — with a PDF export."""
    model = PurchaseOrder
    template_name = 'procurement/achats_report.html'
    context_object_name = 'purchase_orders'
    allowed_roles = ACHATS_REPORT_ROLES
    header_title = _("Rapport des achats")
    header_subtitle = _("Filtrez par caisse, chantier ou période et exportez en PDF")
    back_url = reverse_lazy('procurement:purchase_order_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Achats & Stocks"), 'url': str(reverse_lazy('procurement:purchase_order_list'))},
            {'title': _("Rapport"), 'url': None},
        ]

    def get_queryset(self):
        return _achats_report_queryset(self.request)

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': f"{reverse_lazy('procurement:achats_report_pdf')}?{self.request.GET.urlencode()}",
            'icon': 'file-pdf',
            'class': 'btn-falcon-danger',
        }]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = context['purchase_orders']
        context['total_amount'] = sum((po.total_ht for po in qs), 0)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            context['sites'] = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            context['sites'] = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        context['caisse_choices'] = CaisseType.choices
        context['selected_caisse'] = self.request.GET.get('caisse', '')
        context['selected_site'] = self.request.GET.get('site', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['period'] = self.request.GET.get('period', '')
        return context


@login_required
def achats_report_pdf(request):
    """PDF export of the same filtered achats report."""
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, role__in=ACHATS_REPORT_ROLES
    ).exists()):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:achats_report')

    from core.pdf_utils import render_table_report_pdf

    qs = _achats_report_queryset(request)
    rows = [
        (
            po.order_date.strftime('%d/%m/%Y'),
            po.order_number,
            po.site.name,
            po.supplier.name,
            po.get_caisse_display(),
            f"{po.total_ht:.2f} $",
            po.get_status_display(),
        )
        for po in qs
    ]
    total = sum((po.total_ht for po in qs), 0)
    return render_table_report_pdf(
        filename=f"achats-{timezone.localdate().isoformat()}.pdf",
        title="Rapport des achats",
        subtitle=_("%(count)s commande(s)") % {'count': qs.count()},
        columns=["Date", "N° Commande", "Chantier", "Fournisseur", "Caisse", "Total", "Statut"],
        rows=rows,
        totals_row=["", "", "", "", "Total", f"{total:.2f} $", ""],
        generated_by=request.user.get_full_name() or request.user.username,
    )


# ---------------------------------------------------------------------
# Rapport de stock : mouvements filtrables par chantier/étape/période,
# plus l'état global des stocks — "rapports périodiques
# (journalier/hebdomadaire/mensuel/trimestriel/annuel) filtrés par
# projet/étape" et "un rapport global de stock" du cahier des charges.
# ---------------------------------------------------------------------

STOCK_REPORT_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER', 'MAGASINIER']


def _stock_report_queryset(request):
    qs = StockMovement.objects.select_related('stock_item', 'stock_item__site', 'phase', 'moved_by').order_by('-movement_date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(stock_item__site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(stock_item__site__cabinet__id__in=user_cabinet_ids)

    site_id = request.GET.get('site')
    if site_id:
        qs = qs.filter(stock_item__site_id=site_id)

    phase_id = request.GET.get('phase')
    if phase_id:
        qs = qs.filter(phase_id=phase_id)

    movement_type = request.GET.get('movement_type')
    if movement_type:
        qs = qs.filter(movement_type=movement_type)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(movement_date__gte=date_from)
    if date_to:
        qs = qs.filter(movement_date__lte=date_to)

    today = timezone.localdate()
    period = request.GET.get('period')
    if period == StockReportPeriod.JOURNALIER:
        qs = qs.filter(movement_date=today)
    elif period == StockReportPeriod.HEBDOMADAIRE:
        qs = qs.filter(movement_date__gte=today - timezone.timedelta(days=7))
    elif period == StockReportPeriod.MENSUEL:
        qs = qs.filter(movement_date__gte=today.replace(day=1))
    elif period == StockReportPeriod.TRIMESTRIEL:
        qs = qs.filter(movement_date__gte=today - timezone.timedelta(days=90))
    elif period == StockReportPeriod.ANNUEL:
        qs = qs.filter(movement_date__gte=today.replace(month=1, day=1))

    return qs


def _stock_levels_queryset(request):
    """The global stock state — current quantity_on_hand per StockItem,
    scoped the same way as the movements report."""
    qs = StockItem.objects.select_related('site', 'material').order_by('site__name', 'name')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

    site_id = request.GET.get('site')
    if site_id:
        qs = qs.filter(site_id=site_id)

    return qs


class StockReportView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = StockMovement
    template_name = 'procurement/stock_report.html'
    context_object_name = 'movements'
    allowed_roles = STOCK_REPORT_ROLES
    header_title = _("Rapport de stock")
    header_subtitle = _("État global et mouvements filtrables par chantier, étape et période")
    back_url = reverse_lazy('procurement:stock_item_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Achats & Stocks"), 'url': str(reverse_lazy('procurement:stock_item_list'))},
            {'title': _("Rapport de stock"), 'url': None},
        ]

    def get_queryset(self):
        return _stock_report_queryset(self.request)

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': f"{reverse_lazy('procurement:stock_report_pdf')}?{self.request.GET.urlencode()}",
            'icon': 'file-pdf',
            'class': 'btn-falcon-danger',
        }]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stock_levels'] = _stock_levels_queryset(self.request)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            sites = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            sites = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        context['sites'] = sites
        selected_site = self.request.GET.get('site', '')
        context['selected_site'] = selected_site
        context['phases'] = ProjectPhase.objects.filter(site__in=sites, site_id=selected_site) if selected_site else ProjectPhase.objects.none()
        context['selected_phase'] = self.request.GET.get('phase', '')
        context['movement_type_choices'] = StockMovementType.choices
        context['selected_movement_type'] = self.request.GET.get('movement_type', '')
        context['period_choices'] = StockReportPeriod.choices
        context['selected_period'] = self.request.GET.get('period', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        return context


@login_required
def stock_report_pdf(request):
    """PDF export of the same filtered stock movements report."""
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, role__in=STOCK_REPORT_ROLES
    ).exists()):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:stock_report')

    from core.pdf_utils import render_table_report_pdf

    qs = _stock_report_queryset(request)
    rows = [
        (
            m.movement_date.strftime('%d/%m/%Y'),
            m.stock_item.site.name,
            m.phase.name if m.phase else '-',
            m.stock_item.name,
            m.get_movement_type_display(),
            f"{m.quantity} {m.stock_item.unit}",
            m.motif or '-',
        )
        for m in qs
    ]
    return render_table_report_pdf(
        filename=f"stock-{timezone.localdate().isoformat()}.pdf",
        title="Rapport de stock",
        subtitle=_("%(count)s mouvement(s)") % {'count': qs.count()},
        columns=["Date", "Chantier", "Étape", "Article", "Type", "Quantité", "Motif"],
        rows=rows,
        generated_by=request.user.get_full_name() or request.user.username,
    )


# ---------------------------------------------------------------------
# Achats par virement : la caissière saisit la preuve, le financier valide
# ---------------------------------------------------------------------

@login_required
def purchase_order_submit_transfer_proof(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method != 'POST':
        return redirect('procurement:purchase_order_detail', pk=pk)
    if not can_act_for_cabinet(request, po.site.cabinet, TRANSFER_ENTRY_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:purchase_order_detail', pk=pk)
    form = TransferProofForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            po.submit_transfer_proof(request.user, form.cleaned_data['transfer_proof'])
            messages.success(request, _("Preuve de virement enregistrée — en attente de validation du financier."))
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Fichier invalide."))
    return redirect('procurement:purchase_order_detail', pk=pk)


@login_required
def purchase_order_validate_transfer(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method != 'POST':
        return redirect('procurement:purchase_order_detail', pk=pk)
    if not can_act_for_cabinet(request, po.site.cabinet, TRANSFER_VALIDATE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:purchase_order_detail', pk=pk)
    try:
        po.validate_transfer(request.user)
        messages.success(request, _("Virement validé."))
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('procurement:purchase_order_detail', pk=pk)


# ---------------------------------------------------------------------
# Crédits fournisseurs
# ---------------------------------------------------------------------

class SupplierCreditListView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = SupplierCredit
    template_name = 'procurement/supplier_credit_list.html'
    context_object_name = 'credits'
    allowed_roles = CREDIT_MANAGE_ROLES
    cabinet_lookup_field = 'supplier__cabinet'
    header_title = _("Crédits fournisseurs")
    header_subtitle = _("Achats à crédit et suivi des paiements")

    def get_queryset(self):
        return super().get_queryset().select_related('supplier').order_by('-date')

    def get_context_data(self, **kwargs):
        from finance.models import Caisse
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            context['caisses'] = Caisse.objects.filter(cabinet=active_cabinet) if active_cabinet else Caisse.objects.none()
        else:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            context['caisses'] = Caisse.objects.filter(cabinet__in=cabinets)
        return context

    def get_header_actions(self):
        return [{
            'label': _("Nouveau crédit"),
            'url': str(reverse_lazy('procurement:supplier_credit_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary',
        }]


class SupplierCreditCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = SupplierCredit
    form_class = SupplierCreditForm
    template_name = 'procurement/supplier_credit_form.html'
    allowed_roles = CREDIT_MANAGE_ROLES
    success_url = reverse_lazy('procurement:supplier_credit_list')
    header_title = _("Nouveau crédit fournisseur")
    back_url = reverse_lazy('procurement:supplier_credit_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            supplier_qs = Supplier.objects.filter(cabinet=active_cabinet) if active_cabinet else Supplier.objects.all()
        else:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            supplier_qs = Supplier.objects.filter(cabinet__in=cabinets)
        form.fields['supplier'].queryset = supplier_qs
        form.fields['purchase_order'].queryset = PurchaseOrder.objects.filter(supplier__in=supplier_qs)
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Crédit fournisseur enregistré."))
        return super().form_valid(form)


@login_required
def supplier_credit_repay(request, pk):
    credit = get_object_or_404(SupplierCredit, pk=pk)
    if request.method != 'POST':
        return redirect('procurement:supplier_credit_list')
    if not can_act_for_cabinet(request, credit.supplier.cabinet, CREDIT_MANAGE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:supplier_credit_list')
    form = SupplierCreditPaymentForm(request.POST, cabinet=credit.supplier.cabinet)
    if form.is_valid():
        try:
            credit.record_payment(form.cleaned_data['amount'], request.user, caisse=form.cleaned_data.get('caisse'))
            messages.success(request, _("Paiement enregistré."))
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Montant invalide."))
    return redirect('procurement:supplier_credit_list')


class SupplierQuickCreateView(QuickCreateView):
    """Backs the "select or add a supplier" pickers (purchase orders,
    supplier credits). Only a name is captured — contact details, phone,
    etc. get filled in later from the supplier's own edit screen."""
    model = Supplier

    def build_instance(self, name, request, cabinet, payload):
        return Supplier(cabinet=cabinet, name=name)
