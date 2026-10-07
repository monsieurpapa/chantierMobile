"""Views for the Bibliothèque de Prix (price library) and the DQEs built
from it."""
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem, DQE, MaterialConsumptionRatio
from .forms import (
    PriceLibraryItemForm, DQEForm, DQELineFormSet,
    MaterialConsumptionRatioForm, CabinetMaterialThresholdForm,
)
from projects.models import Site
from core.mixins import (
    CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin,
    add_ambiguous_cabinet_field, get_session_cabinet,
)
from chantiermobile.constants import UserRoles, ApprovalStatus

# Director-tier (plus CHIEF_ENGINEER, consistent with the rest of this
# module) — who may edit the price library/DQE/ratio catalog and the
# cabinet's material-variance thresholds.
PRICING_ADMIN_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

# Kept as a module-local alias — relocated to core.mixins.add_ambiguous_cabinet_field
# so finance/views.py (SalaryPaymentListCreateView) can reuse it too.
_add_ambiguous_cabinet_field = add_ambiguous_cabinet_field


class PriceLibraryItemListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    """Browse the cabinet's price library. Cabinet-scoped via the
    inherited default `cabinet_lookup_field = 'cabinet'` (PriceLibraryItem
    has a direct cabinet FK, so no override is needed here). Any
    logged-in member of the cabinet can view; "Ajouter" is only shown to
    director-tier/CHIEF_ENGINEER roles."""
    model = PriceLibraryItem
    template_name = 'pricing/price_item_list.html'
    context_object_name = 'price_items'
    paginate_by = 50
    header_title = _("Bibliothèque de Prix")
    header_subtitle = _("Catalogue des prix unitaires réutilisables (main d'œuvre, matériaux, matériel, prestations)")

    def get_queryset(self):
        return super().get_queryset().order_by('item_type', 'code')

    def get_header_actions(self):
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER],
            status=ApprovalStatus.APPROVED,
        ).exists():
            return [{
                'label': _("Ajouter un article"),
                'url': str(reverse_lazy('pricing:price_item_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []


class PriceLibraryItemCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Add a price library item. Director-tier or CHIEF_ENGINEER only
    (allowed_roles below); tagged to the creator's own cabinet in
    form_valid(), with an explicit cabinet picker added for a
    multi-cabinet user who hasn't switched into one (see
    _add_ambiguous_cabinet_field)."""
    model = PriceLibraryItem
    form_class = PriceLibraryItemForm
    template_name = 'pricing/price_item_form.html'
    success_url = reverse_lazy('pricing:price_item_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    header_title = _("Ajouter un article au catalogue de prix")
    header_subtitle = _("Définir un nouveau prix unitaire réutilisable")
    back_url = reverse_lazy('pricing:price_item_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bibliothèque de Prix"), 'url': str(reverse_lazy('pricing:price_item_list'))},
            {'title': _("Nouvel article"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _add_ambiguous_cabinet_field(self, form)
        return form

    def form_valid(self, form):
        # get_user_cabinet() (CabinetAccessMixin) is the single source of
        # truth for the unambiguous cases — the one cabinet for a
        # single-cabinet user, or the resolved cabinet for a superuser.
        # For a multi-cabinet user it used to silently guess
        # (cabinet_roles.first()), which could tag this item to the wrong
        # tenant; now it returns None and _add_ambiguous_cabinet_field
        # (get_form above) adds an explicit, scoped-to-their-own-cabinets
        # 'cabinet' field for them to pick from instead.
        cabinet = self.get_user_cabinet() or form.cleaned_data.get('cabinet')
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Article '%(name)s' ajouté à la bibliothèque de prix.") % {'name': form.instance.designation})
        return super().form_valid(form)


class PriceLibraryItemUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Edit a price library item. Same director-tier/CHIEF_ENGINEER gate
    as PriceLibraryItemCreateView. Note editing `unit_price` here
    re-prices the catalog going forward only — it does not touch
    `unit_price` already copied onto existing DQELine rows."""
    model = PriceLibraryItem
    form_class = PriceLibraryItemForm
    template_name = 'pricing/price_item_form.html'
    success_url = reverse_lazy('pricing:price_item_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

    def get_header_title(self):
        return _("Modifier : %(name)s") % {'name': self.object.designation}

    def get_back_url(self):
        return str(reverse_lazy('pricing:price_item_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bibliothèque de Prix"), 'url': str(reverse_lazy('pricing:price_item_list'))},
            {'title': _("Modifier"), 'url': None},
        ]

    def form_valid(self, form):
        from django.contrib import messages
        messages.success(self.request, _("Article '%(name)s' mis à jour.") % {'name': form.instance.designation})
        return super().form_valid(form)


class PriceLibraryItemDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """View a single price library item. Cabinet-scoped (default
    `cabinet_lookup_field = 'cabinet'`); any logged-in member of the
    cabinet can view."""
    model = PriceLibraryItem
    template_name = 'pricing/price_item_detail.html'
    context_object_name = 'price_item'

    def get_header_title(self):
        return self.object.designation

    def get_header_subtitle(self):
        return _("Code : %(code)s | %(price)s / %(unit)s") % {
            'code': self.object.code,
            'price': self.object.unit_price,
            'unit': self.object.unit,
        }

    def get_back_url(self):
        return str(reverse_lazy('pricing:price_item_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bibliothèque de Prix"), 'url': str(reverse_lazy('pricing:price_item_list'))},
            {'title': self.object.code, 'url': None},
        ]


def _scope_site_queryset(request, form):
    """Restrict a DQE form's `site` field to the sites the current user can see.

    FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now — see
    core/mixins.py and docs/security.md.
    """
    if request.user.is_superuser:
        form.fields['site'].queryset = Site.objects.all()
    else:
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
    return form


class DQEListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    """List the cabinet's DQEs. Cabinet-scoped (default
    `cabinet_lookup_field = 'cabinet'` — DQE has a direct cabinet FK);
    any logged-in member of the cabinet can view. "Nouveau DQE" is only
    shown to director-tier/CHIEF_ENGINEER roles."""
    model = DQE
    template_name = 'pricing/dqe_list.html'
    context_object_name = 'dqes'
    paginate_by = 50
    header_title = _("DQE")
    header_subtitle = _("Détails Quantitatifs Estimatifs — bordereaux de quantités bâtis sur la bibliothèque de prix")

    def get_queryset(self):
        return super().get_queryset().select_related('site').prefetch_related('lines').order_by('-created_at')

    def get_header_actions(self):
        # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now —
        # see core/mixins.py and docs/security.md.
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER],
            status=ApprovalStatus.APPROVED,
        ).exists():
            return [{
                'label': _("Nouveau DQE"),
                'url': str(reverse_lazy('pricing:dqe_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []


class DQECreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Create a DQE with its lines. Director-tier or CHIEF_ENGINEER only
    (allowed_roles below); `site` is scoped to the user's own cabinet(s)
    (_scope_site_queryset), and `cabinet` is resolved/picked the same way
    as PriceLibraryItemCreateView."""
    model = DQE
    form_class = DQEForm
    template_name = 'pricing/dqe_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']
    header_title = _("Nouveau DQE")
    header_subtitle = _("Créer un détail quantitatif estimatif à partir de la bibliothèque de prix")
    back_url = reverse_lazy('pricing:dqe_list')

    def get_success_url(self):
        return reverse_lazy('pricing:dqe_detail', kwargs={'pk': self.object.pk})

    def get_breadcrumb_items(self):
        return [
            {'title': _("DQE"), 'url': str(reverse_lazy('pricing:dqe_list'))},
            {'title': _("Nouveau"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = _scope_site_queryset(self.request, super().get_form(form_class))
        _add_ambiguous_cabinet_field(self, form)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = DQELineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = DQELineFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        # See PriceLibraryItemCreateView.form_valid — get_user_cabinet()
        # (falling back to the form's explicit 'cabinet' field for an
        # ambiguous multi-cabinet user) is the shared, non-guessing
        # resolver for which cabinet a new record belongs to.
        cabinet = self.get_user_cabinet() or form.cleaned_data.get('cabinet')
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet

        context = self.get_context_data()
        lines_formset = context['lines_formset']

        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("DQE '%(ref)s' créé avec %(count)s ligne(s).") % {
                'ref': self.object.reference, 'count': self.object.total_lines
            })
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)


class DQEUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Edit a DQE and its lines. Same director-tier/CHIEF_ENGINEER gate
    as DQECreateView; no status-based restriction — a VALIDATED or
    ARCHIVED DQE can still be edited through this view (the status field
    is just another form field on DQEForm, not state-machine-checked
    anywhere in pricing/models.py)."""
    model = DQE
    form_class = DQEForm
    template_name = 'pricing/dqe_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']

    def get_success_url(self):
        return reverse_lazy('pricing:dqe_detail', kwargs={'pk': self.object.pk})

    def get_header_title(self):
        return _("Modifier : %(ref)s") % {'ref': self.object.reference}

    def get_back_url(self):
        return str(reverse_lazy('pricing:dqe_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("DQE"), 'url': str(reverse_lazy('pricing:dqe_list'))},
            {'title': self.object.reference, 'url': str(reverse_lazy('pricing:dqe_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_form(self, form_class=None):
        return _scope_site_queryset(self.request, super().get_form(form_class))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = DQELineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = DQELineFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("DQE '%(ref)s' mis à jour.") % {'ref': self.object.reference})
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)


class DQEDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """View a single DQE and its lines. Cabinet-scoped; any logged-in
    member of the cabinet can view."""
    model = DQE
    template_name = 'pricing/dqe_detail.html'
    context_object_name = 'dqe'

    def get_queryset(self):
        return super().get_queryset().select_related('site').prefetch_related('lines__price_item')

    def get_header_title(self):
        return self.object.reference

    def get_header_subtitle(self):
        return self.object.title

    def get_back_url(self):
        return str(reverse_lazy('pricing:dqe_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("DQE"), 'url': str(reverse_lazy('pricing:dqe_list'))},
            {'title': self.object.reference, 'url': None},
        ]


@login_required
def price_items_data_api(request):
    """API endpoint exposing active price library items (designation, unit, unit_price)
    so the DQE line formset can auto-fill those fields client-side, mirroring
    materials.views.materials_data_api.

    FIXED 2026-10-06 (previously a tenant-isolation + auth gap — see
    docs/modules/pricing.md's history / git log for the original finding):
    this endpoint used to have no `@login_required` at all and applied no
    cabinet filter, so any anonymous request could read every cabinet's
    price catalog. It now requires login and is scoped exactly like
    `CabinetAccessMixin` would scope `PriceLibraryItemListView` — a
    superuser sees the session-selected cabinet (or every cabinet if none
    is selected), everyone else sees only the cabinet(s) they hold a role
    in. Kept as a plain function (not a CBV) so it stays a drop-in
    replacement for the existing `fetch('/pricing/api/price-items-data/')`
    call in the DQE line formset's JS.
    """
    from django.http import JsonResponse

    # FIXED 2026-10-06: only an APPROVED UserCabinetRole counts now — see
    # core/mixins.py and docs/security.md.
    items = PriceLibraryItem.objects.filter(is_active=True)
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            items = items.filter(cabinet=active_cabinet)
    else:
        cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet', flat=True)
        items = items.filter(cabinet__in=cabinet_ids)

    items = items.values('id', 'designation', 'unit', 'unit_price')
    data = {}
    for item in items:
        data[str(item['id'])] = {
            'designation': item['designation'],
            'unit': item['unit'],
            'unit_price': float(item['unit_price'] or 0),
        }
    return JsonResponse(data)


@login_required
def site_dqes_data_api(request):
    """JSON endpoint used by revenue's Devis form to scope `source_dqe` to
    the picked site, the same way finance:site_phases_data scopes a phase
    picker — the field's queryset is otherwise empty on a fresh GET (see
    DevisForm.__init__)."""
    from django.http import JsonResponse

    site_id = request.GET.get('site')
    if not site_id:
        return JsonResponse({'results': []})

    site_qs = Site.objects.filter(pk=site_id)
    if not request.user.is_superuser:
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
        site_qs = site_qs.filter(cabinet__id__in=user_cabinet_ids)
    site = site_qs.first()
    if not site:
        return JsonResponse({'results': []})

    dqes = DQE.objects.filter(site=site).order_by('-created_at')
    return JsonResponse({
        'results': [{'id': d.id, 'text': f"{d.reference} - {d.title}"} for d in dqes]
    })


@login_required
def material_usage_comparison_api(request):
    """Live red/orange/green comparison badge for one (site, étape,
    matériau), used by both the materials/request_form.html item rows and
    pricing/dqe_form.html's lines (a DQE line check is informational only
    — nothing stops a DQE line from exceeding a devis, since the DQE *is*
    the estimate).

    GET params: site, phase, material (all required ids), quantity
    (defaults to 0 — "what if this row's quantity were added"),
    exclude_item (a MaterialRequestItem pk already counted in the
    cumulative total, to preview an edit to that exact row without
    double-counting it).

    Returns JSON: {ok: true, status, status_label, baseline,
    cumulative_requested, variance_pct} or {ok: false, reason} when the
    inputs don't resolve to a comparable (site, phase, material) —
    callers should hide/neutralize the badge in that case rather than
    treat it as an error."""
    from decimal import Decimal, InvalidOperation
    from django.http import JsonResponse
    from projects.models import ProjectPhase
    from materials.models import Material, MaterialRequestItem
    from pricing.services import compare_material_usage

    site_id = request.GET.get('site')
    phase_id = request.GET.get('phase')
    material_id = request.GET.get('material')
    if not (site_id and phase_id and material_id):
        return JsonResponse({'ok': False, 'reason': 'missing_params'})

    site_qs = Site.objects.filter(pk=site_id)
    if not request.user.is_superuser:
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
        site_qs = site_qs.filter(cabinet__id__in=user_cabinet_ids)
    site = site_qs.first()
    if not site:
        return JsonResponse({'ok': False, 'reason': 'site_not_found'})

    phase = ProjectPhase.objects.filter(pk=phase_id, site=site).first()
    if not phase:
        return JsonResponse({'ok': False, 'reason': 'phase_not_found'})

    material = Material.objects.filter(pk=material_id).first()
    if not material:
        return JsonResponse({'ok': False, 'reason': 'material_not_found'})

    try:
        quantity = Decimal(request.GET.get('quantity') or '0')
    except InvalidOperation:
        quantity = Decimal('0')

    exclude_item = None
    exclude_item_id = request.GET.get('exclude_item')
    if exclude_item_id:
        exclude_item = MaterialRequestItem.objects.filter(pk=exclude_item_id).first()

    result = compare_material_usage(
        site, phase, material,
        exclude_request_item=exclude_item,
        additional_quantity=quantity,
    )
    return JsonResponse({
        'ok': True,
        'status': result['status'],
        'status_label': str(dict(_material_variance_choices())[result['status']]),
        'baseline': float(result['baseline']),
        'cumulative_requested': float(result['cumulative_requested']),
        'variance_pct': float(result['variance_pct']) if result['variance_pct'] is not None else None,
    })


def _material_variance_choices():
    from chantiermobile.constants import MaterialVarianceStatus
    return MaterialVarianceStatus.choices


class MaterialConsumptionRatioListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """The ratio catalog: global defaults (cabinet is null — seeded once
    for every cabinet, see pricing/migrations/0004) plus this cabinet's
    own overrides. Director-tier/CHIEF_ENGINEER only, since a wrong ratio
    here silently skews every WORK_ITEM comparison badge."""
    model = MaterialConsumptionRatio
    template_name = 'pricing/ratio_list.html'
    context_object_name = 'ratios'
    allowed_roles = PRICING_ADMIN_ROLES
    header_title = _("Ratios de consommation matière")
    header_subtitle = _("Nomenclature utilisée pour « exploser » un ouvrage composite (béton, acier...) en quantités de matériaux élémentaires")

    def _cabinet_ids(self):
        if self.request.user.is_superuser:
            cabinet = get_session_cabinet(self.request)
            if cabinet:
                return [cabinet.pk]
            from accounts.models import Cabinet
            return list(Cabinet.objects.values_list('pk', flat=True))
        return list(self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True))

    def get_queryset(self):
        from django.db.models import Q
        cabinet_ids = self._cabinet_ids()
        return MaterialConsumptionRatio.objects.filter(
            Q(cabinet__isnull=True) | Q(cabinet_id__in=cabinet_ids)
        ).select_related('material', 'cabinet').order_by('work_category', 'material__name', 'cabinet_id')

    def get_header_actions(self):
        return [{
            'label': _("Ajouter un ratio"),
            'url': str(reverse_lazy('pricing:ratio_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary',
        }]


class MaterialConsumptionRatioCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Add a cabinet-specific ratio override. Always tagged to the
    acting user's own cabinet — a cabinet can never create or edit a
    global-default (cabinet=None) row through this view; those exist only
    via the seed migration, by design (see MaterialConsumptionRatio's
    docstring)."""
    model = MaterialConsumptionRatio
    form_class = MaterialConsumptionRatioForm
    template_name = 'pricing/ratio_form.html'
    allowed_roles = PRICING_ADMIN_ROLES
    success_url = reverse_lazy('pricing:ratio_list')
    header_title = _("Ajouter un ratio de consommation")
    header_subtitle = _("Définir ou surclasser un ratio matériau pour une catégorie d'ouvrage")
    back_url = reverse_lazy('pricing:ratio_list')

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Ratio ajouté."))
        return super().form_valid(form)


class MaterialConsumptionRatioUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Edit one of this cabinet's own ratio overrides. CabinetAccessMixin's
    default `cabinet_lookup_field = 'cabinet'` naturally excludes
    global-default (cabinet=None) rows from this view's queryset — exactly
    the restriction the class docstring above describes."""
    model = MaterialConsumptionRatio
    form_class = MaterialConsumptionRatioForm
    template_name = 'pricing/ratio_form.html'
    allowed_roles = PRICING_ADMIN_ROLES
    success_url = reverse_lazy('pricing:ratio_list')
    back_url = reverse_lazy('pricing:ratio_list')
    header_title = _("Modifier le ratio")

    def form_valid(self, form):
        messages.success(self.request, _("Ratio mis à jour."))
        return super().form_valid(form)


class CabinetMaterialThresholdSettingsView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, UpdateView):
    """Director-tier-editable cabinet-wide orange/red variance thresholds
    (accounts.Cabinet.material_variance_*_threshold_pct). Not reached via
    a pk in the URL — resolves to the acting user's own cabinet, the same
    way a superuser's session-switched cabinet (or a multi-cabinet user's
    first director-tier cabinet) is resolved elsewhere in this module."""
    form_class = CabinetMaterialThresholdForm
    template_name = 'pricing/cabinet_thresholds_form.html'
    allowed_roles = PRICING_ADMIN_ROLES
    success_url = reverse_lazy('pricing:price_item_list')
    header_title = _("Seuils de dépassement matière")
    header_subtitle = _("Pourcentage de l'estimation du devis au-delà duquel une comparaison matériau passe à l'orange, puis au rouge")

    def get_object(self, queryset=None):
        from django.http import Http404
        from accounts.models import Cabinet
        if self.request.user.is_superuser:
            cabinet = get_session_cabinet(self.request)
            if cabinet:
                return cabinet
            cabinet = Cabinet.objects.order_by('id').first()
            if cabinet:
                return cabinet
            raise Http404(_("Aucun cabinet trouvé."))
        cabinet_ids = list(
            self.request.user.approved_cabinet_roles.filter(
                role__in=PRICING_ADMIN_ROLES,
            ).values_list('cabinet_id', flat=True)
        )
        if not cabinet_ids:
            raise Http404(_("Aucun cabinet trouvé pour cet utilisateur."))
        requested = self.request.GET.get('cabinet')
        if requested and int(requested) in cabinet_ids:
            return Cabinet.objects.get(pk=requested)
        return Cabinet.objects.get(pk=cabinet_ids[0])

    def form_valid(self, form):
        messages.success(self.request, _("Seuils de dépassement mis à jour."))
        return super().form_valid(form)


class DevisComplianceReportView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """Per-étape breakdown of a Site's material-variance comparisons
    against its accepted Devis's source DQE — the "intelligently
    comparing material requests to the original devis and detailed devis
    figures" report from the brainstorm, as a read-only page any member
    of the cabinet can consult (not just the director-tier, mirroring
    DQEDetailView's own any-member-can-view stance; only *editing* the
    ratio catalog/thresholds is director-tier-gated)."""
    model = Site
    template_name = 'pricing/devis_compliance_report.html'
    context_object_name = 'site'
    header_title = _("Conformité devis / état de besoin")

    def get_header_subtitle(self):
        return self.object.name

    def get_back_url(self):
        return str(reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.unique_id}))

    def get_context_data(self, **kwargs):
        from pricing.services import compare_material_usage
        from chantiermobile.constants import DevisStatus
        context = super().get_context_data(**kwargs)
        site = self.object

        devis = site.devis_set.filter(status=DevisStatus.ACCEPTE, source_dqe__isnull=False).first()
        context['devis'] = devis

        rows = []
        if devis:
            dqe = devis.source_dqe
            # Every (phase, material) pair this DQE actually budgets for —
            # a material never requested yet still deserves a row (so a
            # 100%-unspent budget is visible too), but a material neither
            # budgeted for nor requested has nothing to show.
            seen = set()
            for line in dqe.lines.select_related('phase', 'price_item').all():
                if not line.phase_id:
                    continue
                for material_id in line.exploded_requirements().keys():
                    seen.add((line.phase_id, material_id))
            from materials.models import Material, MaterialRequestItem
            requested_pairs = MaterialRequestItem.objects.filter(
                request__site=site, phase__isnull=False, material__isnull=False,
            ).values_list('phase_id', 'material_id').distinct()
            seen.update(requested_pairs)

            materials_by_id = {m.pk: m for m in Material.objects.filter(pk__in=[m for _p, m in seen])}
            from projects.models import ProjectPhase
            phases_by_id = {p.pk: p for p in ProjectPhase.objects.filter(pk__in=[p for p, _m in seen])}

            for phase_id, material_id in sorted(seen, key=lambda t: (phases_by_id[t[0]].name, materials_by_id[t[1]].name)):
                phase = phases_by_id.get(phase_id)
                material = materials_by_id.get(material_id)
                if not phase or not material:
                    continue
                comparison = compare_material_usage(site, phase, material)
                rows.append({'phase': phase, 'material': material, 'comparison': comparison})

        context['rows'] = rows
        context['overage_requests'] = site.material_requests.exclude(overage_justification='').order_by('-updated_at')
        return context
