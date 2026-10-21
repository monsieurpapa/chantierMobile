"""
Entrées et sorties de stock at a chantier — 2026-10-21.

Only the chantier's Magasinier (UserCabinetRole.site, see core/roles.py)
records, edits or deletes them; everyone with access to the stock report
sees them read-only. Each entrée has a bon de réception (PDF) sent to the
Directeur technique, who puts a visa on it from the movement's page.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView

from chantiermobile.constants import StockMovementType, UserRoles
from core.mixins import PageHeaderMixin, can_act_for_cabinet
from core.notifications import notify_role_holders
from core.roles import is_site_magasinier, magasinier_site_ids
from projects.models import Site

from .forms import StockEntryExitForm
from .models import StockMovement

# Who receives the bons de réception and puts a visa on them. DIRECTOR
# stands in for a cabinet with no Directeur technique (as for
# FINAL_AUTHORIZATION_ROLES).
RECEPTION_VISA_ROLES = [UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTOR]

KINDS = {'entree': StockMovementType.IN, 'sortie': StockMovementType.OUT}


def _visible_movements(request):
    from .views import _stock_report_queryset
    return _stock_report_queryset(request).select_related(
        'supplier', 'reception_visa_by', 'purchase_order_line__purchase_order__supplier', 'stock_item__material',
    )


def notify_reception(movement, actor, edited=False):
    """Tell the Directeur technique (or, without one, the directeur) that a
    bon de réception is waiting for their visa."""
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import ApprovalStatus
    cabinet = movement.site.cabinet
    has_dt = UserCabinetRole.objects.filter(
        cabinet=cabinet, role=UserRoles.DIRECTEUR_TECHNIQUE, status=ApprovalStatus.APPROVED,
    ).exists()
    roles = [UserRoles.DIRECTEUR_TECHNIQUE] if has_dt else [UserRoles.DIRECTOR]
    template = (_("Bon de réception %(ref)s modifié — %(qty)s %(unit)s de %(item)s à %(site)s, à viser.")
                if edited else
                _("Bon de réception %(ref)s — %(qty)s %(unit)s de %(item)s reçus à %(site)s, à viser."))
    notify_role_holders(
        cabinet, roles,
        template % {'ref': movement.reception_number, 'qty': movement.quantity, 'unit': movement.stock_item.unit,
                    'item': movement.stock_item.name, 'site': movement.site.name},
        reverse('procurement:stock_movement_detail', kwargs={'pk': movement.pk}),
        exclude_user=actor,
    )


def _resolve_site(request):
    """The chantier an entrée/sortie is recorded at: ?site=<pk> if the user
    is its Magasinier, else their only chantier."""
    site_ids = magasinier_site_ids(request.user)
    wanted = request.GET.get('site') or request.POST.get('site')
    if wanted:
        try:
            wanted = int(wanted)
        except (TypeError, ValueError):
            wanted = None
        if wanted in site_ids:
            return Site.objects.get(pk=wanted)
    if len(site_ids) == 1:
        return Site.objects.get(pk=next(iter(site_ids)))
    return None


def _form_page(request, form, movement=None):
    is_entry = form.is_entry
    if movement is None:
        title = _("Nouvelle entrée en stock") if is_entry else _("Nouvelle sortie de stock")
    else:
        title = (_("Modifier l'entrée %(ref)s") if is_entry else _("Modifier la sortie %(ref)s")) % {
            'ref': movement.reception_number or f'#{movement.pk}'}
    back = (reverse('procurement:stock_movement_detail', kwargs={'pk': movement.pk}) if movement
            else reverse('procurement:stock_report') + f'?site={form.site.pk}')
    return render(request, 'procurement/stock_movement_form.html', {
        'form': form, 'movement': movement, 'site': form.site, 'is_entry': is_entry,
        'header_title': title,
        'header_subtitle': _("Chantier : %(site)s") % {'site': form.site.name},
        'breadcrumb_items': [
            {'title': _("Rapport de stock"), 'url': reverse('procurement:stock_report') + f'?site={form.site.pk}'},
            {'title': title, 'url': None},
        ],
        'back_url': back, 'header_actions': [],
    })


def _apply_validation_error(form, error):
    if hasattr(error, 'error_dict'):
        for field, errs in error.error_dict.items():
            form.add_error(field if field in form.fields else None, errs)
    else:
        form.add_error(None, error.messages)


@login_required
def stock_movement_create(request, kind):
    """Record an entrée (kind="entree") or a sortie (kind="sortie") at the
    user's chantier. Magasinier of that chantier only."""
    movement_type = KINDS.get(kind)
    if movement_type is None:
        raise Http404
    site = _resolve_site(request)
    if site is None:
        messages.error(request, _("Seul le magasinier d'un chantier peut enregistrer ses entrées et sorties de stock."))
        return redirect('procurement:stock_report')
    if request.method == 'POST':
        form = StockEntryExitForm(request.POST, request.FILES, site=site, movement_type=movement_type)
        if form.is_valid():
            try:
                movement = form.save(commit=False)
                movement.moved_by = request.user
                movement.save_with_stock_update()
            except ValidationError as e:
                _apply_validation_error(form, e)
            else:
                if movement.has_bon_de_reception:
                    notify_reception(movement, request.user)
                    messages.success(request, _("Entrée enregistrée — bon de réception %(ref)s envoyé au Directeur technique.") % {
                        'ref': movement.reception_number})
                else:
                    messages.success(request, _("Sortie enregistrée."))
                return redirect('procurement:stock_movement_detail', pk=movement.pk)
    else:
        initial = {}
        if request.GET.get('stock_item') and movement_type == StockMovementType.OUT:
            initial['stock_item'] = request.GET['stock_item']
        if request.GET.get('material') and movement_type == StockMovementType.IN:
            initial['material'] = request.GET['material']
        form = StockEntryExitForm(site=site, movement_type=movement_type, initial=initial)
    return _form_page(request, form)


def _editable_movement_or_deny(request, pk):
    movement = get_object_or_404(StockMovement.objects.select_related('stock_item__site'), pk=pk)
    if not is_site_magasinier(request.user, movement.site):
        messages.error(request, _("Seul le magasinier de ce chantier peut modifier ses mouvements de stock."))
        return movement, redirect('procurement:stock_movement_detail', pk=pk)
    if not movement.is_manual_entry_or_exit:
        messages.error(request, _("Ce mouvement provient d'une commande, d'un transfert ou d'un ajustement : il ne peut pas être modifié ici."))
        return movement, redirect('procurement:stock_movement_detail', pk=pk)
    return movement, None


@login_required
def stock_movement_update(request, pk):
    movement, denied = _editable_movement_or_deny(request, pk)
    if denied:
        return denied
    if request.method == 'POST':
        form = StockEntryExitForm(request.POST, request.FILES, instance=movement, site=movement.site,
                                  movement_type=movement.movement_type)
        if form.is_valid():
            try:
                movement = form.save(commit=False)
                had_visa = movement.reception_visa_at is not None
                if movement.has_bon_de_reception:
                    # The bon changed: the Directeur technique sees it again.
                    movement.reception_visa_by = None
                    movement.reception_visa_at = None
                movement.save_with_stock_update()
            except ValidationError as e:
                _apply_validation_error(form, e)
            else:
                if movement.has_bon_de_reception:
                    notify_reception(movement, request.user, edited=True)
                    if had_visa:
                        messages.info(request, _("Le visa du Directeur technique a été retiré : le bon modifié lui est renvoyé."))
                messages.success(request, _("Mouvement mis à jour."))
                return redirect('procurement:stock_movement_detail', pk=movement.pk)
    else:
        form = StockEntryExitForm(instance=movement, site=movement.site, movement_type=movement.movement_type)
    return _form_page(request, form, movement)


@login_required
def stock_movement_delete(request, pk):
    movement, denied = _editable_movement_or_deny(request, pk)
    if denied:
        return denied
    if request.method == 'POST':
        site_pk = movement.site.pk
        try:
            movement.remove_with_stock_update()
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('procurement:stock_movement_detail', pk=pk)
        if movement.has_bon_de_reception:
            notify_role_holders(
                movement.site.cabinet, RECEPTION_VISA_ROLES,
                _("Bon de réception %(ref)s supprimé par le magasinier de %(site)s.") % {
                    'ref': movement.reception_number, 'site': movement.site.name},
                reverse('procurement:stock_report') + f'?site={site_pk}', exclude_user=request.user,
            )
        messages.success(request, _("Mouvement supprimé et stock corrigé."))
        return redirect(reverse('procurement:stock_report') + f'?site={site_pk}')
    return render(request, 'procurement/stock_movement_confirm_delete.html', {
        'movement': movement,
        'header_title': _("Supprimer ce mouvement ?"),
        'header_subtitle': str(movement),
        'breadcrumb_items': [
            {'title': _("Rapport de stock"), 'url': reverse('procurement:stock_report')},
            {'title': _("Supprimer"), 'url': None},
        ],
        'back_url': reverse('procurement:stock_movement_detail', kwargs={'pk': pk}),
        'header_actions': [],
    })


class StockMovementDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    """One movement: what, where, who, its bon de réception (entrées) and
    the Directeur technique's visa. Visible to everyone who can see the
    stock report for that chantier; actions only to whoever may take them."""
    model = StockMovement
    template_name = 'procurement/stock_movement_detail.html'
    context_object_name = 'movement'

    def dispatch(self, request, *args, **kwargs):
        from .views import STOCK_REPORT_ROLES
        from accounts.models import UserCabinetRole
        from chantiermobile.constants import ApprovalStatus
        if request.user.is_authenticated and not request.user.is_superuser and not UserCabinetRole.objects.filter(
                user=request.user, role__in=STOCK_REPORT_ROLES, status=ApprovalStatus.APPROVED).exists():
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return _visible_movements(self.request)

    def get_header_title(self):
        m = self.object
        if m.has_bon_de_reception:
            return _("Entrée en stock — %(ref)s") % {'ref': m.reception_number}
        return _("%(type)s — %(item)s") % {'type': m.get_movement_type_display(), 'item': m.stock_item.name}

    def get_header_subtitle(self):
        m = self.object
        return _("%(site)s · %(date)s") % {'site': m.site.name, 'date': m.movement_date.strftime('%d/%m/%Y')}

    def get_back_url(self):
        return reverse('procurement:stock_report') + f'?site={self.object.site.pk}'

    def get_breadcrumb_items(self):
        return [
            {'title': _("Rapport de stock"), 'url': self.get_back_url()},
            {'title': self.object.reception_number or _("Mouvement #%(pk)s") % {'pk': self.object.pk}, 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        m = self.object
        user = self.request.user
        context['can_edit'] = m.is_manual_entry_or_exit and is_site_magasinier(user, m.site)
        context['can_visa'] = (m.has_bon_de_reception and m.reception_visa_at is None
                               and can_act_for_cabinet(self.request, m.site.cabinet, RECEPTION_VISA_ROLES))
        context['is_magasinier'] = is_site_magasinier(user, m.site)
        context['stock_after'] = m.stock_item.quantity_on_hand
        return context


def _movement_for_viewer_or_404(request, pk):
    return get_object_or_404(_visible_movements(request), pk=pk)


@login_required
def bon_de_reception_pdf(request, pk):
    """The bon de réception of an entrée, on the cabinet's letterhead:
    quantities only, signature boxes for the magasinier, the deliverer
    and the Directeur technique (stamped once visé in the app)."""
    from .views import STOCK_REPORT_ROLES
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import ApprovalStatus
    from core.pdf_utils import Signatory, fmt_quantity, person_name, pour_label, render_table_report_pdf
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
            user=request.user, role__in=STOCK_REPORT_ROLES, status=ApprovalStatus.APPROVED).exists()):
        raise PermissionDenied
    m = _movement_for_viewer_or_404(request, pk)
    if not m.has_bon_de_reception:
        raise Http404
    cabinet = m.site.cabinet
    supplier = m.effective_supplier
    po = m.purchase_order
    info = [
        ('Chantier', m.site.name + (f' — {m.site.location}' if getattr(m.site, 'location', '') else '')),
        ('Date de réception', m.movement_date.strftime('%d/%m/%Y')),
        ('Fournisseur', supplier.name if supplier else '—'),
        ('N° bon de livraison', m.delivery_note_ref or '—'),
    ]
    if po is not None:
        info.append(('Bon de commande', po.order_number))
    if m.phase_id:
        info.append(('Étape', m.phase.name))
    info.append(('Réceptionné par', person_name(m.moved_by) or '—'))
    observations = ' '.join(x for x in [m.motif, m.notes] if x) or '—'
    visa = ''
    if m.reception_visa_at:
        visa = (f"Visé dans ChantierMobile le {timezone.localtime(m.reception_visa_at).strftime('%d/%m/%Y')}"
                f" par {person_name(m.reception_visa_by)}")
    return render_table_report_pdf(
        filename=f"bon-de-reception-{m.reception_number}.pdf",
        title=f"BON DE RÉCEPTION N° {m.reception_number}",
        subtitle="Réception de matériaux au chantier",
        info_rows=info,
        columns=['N°', 'Désignation', 'Unité', 'Quantité reçue', 'Observations'],
        rows=[('1', m.stock_item.name, m.stock_item.unit, fmt_quantity(m.quantity), observations)],
        col_widths=[0.06, 0.40, 0.12, 0.16, 0.26],
        signatories=[
            Signatory('Le Magasinier', m.site.name, person_name(m.moved_by)),
            Signatory('Le Livreur / Fournisseur', supplier.name if supplier else ''),
            Signatory('Le Directeur Technique', pour_label(cabinet),
                      person_name(m.reception_visa_by) if m.reception_visa_by_id else '', visa),
        ],
        generated_by=person_name(request.user),
        cabinet=cabinet,
    )


@login_required
def stock_movement_visa(request, pk):
    """The Directeur technique (or directeur) acknowledges a bon de
    réception."""
    m = _movement_for_viewer_or_404(request, pk)
    if request.method != 'POST':
        return redirect('procurement:stock_movement_detail', pk=pk)
    if not m.has_bon_de_reception or not can_act_for_cabinet(request, m.site.cabinet, RECEPTION_VISA_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('procurement:stock_movement_detail', pk=pk)
    if m.reception_visa_at is None:
        m.reception_visa_by = request.user
        m.reception_visa_at = timezone.now()
        m.save(update_fields=['reception_visa_by', 'reception_visa_at', 'updated_at'])
        from core.notifications import notify_user
        notify_user(m.moved_by, _("Bon de réception %(ref)s visé par %(who)s.") % {
            'ref': m.reception_number, 'who': request.user.get_full_name() or request.user.username},
            reverse('procurement:stock_movement_detail', kwargs={'pk': m.pk}))
        messages.success(request, _("Bon de réception visé."))
    return redirect('procurement:stock_movement_detail', pk=pk)
