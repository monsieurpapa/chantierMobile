"""Views for the Bibliothèque de Prix (price library) and the DQEs built
from it."""
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem, DQE
from .forms import PriceLibraryItemForm, DQEForm, DQELineFormSet
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, add_ambiguous_cabinet_field
from chantiermobile.constants import UserRoles

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
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER]
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
    """Restrict a DQE form's `site` field to the sites the current user can see."""
    if request.user.is_superuser:
        form.fields['site'].queryset = Site.objects.all()
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
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
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CHIEF_ENGINEER]
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


def price_items_data_api(request):
    """API endpoint exposing active price library items (designation, unit, unit_price)
    so the DQE line formset can auto-fill those fields client-side, mirroring
    materials.views.materials_data_api.

    GOTCHA: unlike materials_data_api (which at least requires
    @login_required), this view has no authentication decorator at all —
    there is no app-wide login-required middleware in this project (see
    MIDDLEWARE in chantiermobile/settings.py), so this endpoint is
    reachable by a fully anonymous request. It also queries
    `PriceLibraryItem.objects.filter(is_active=True)` with no cabinet
    filter whatsoever, unlike every other pricing view (which all scope
    through CabinetAccessMixin or an explicit cabinet_roles filter).
    PriceLibraryItem is cabinet-scoped, tenant-specific data (a cabinet's
    own negotiated unit prices — see the model docstring), so this one
    endpoint leaks every cabinet's active price catalog (code,
    designation, unit, unit_price) to anyone who can reach the URL,
    logged in or not."""
    from django.http import JsonResponse

    items = PriceLibraryItem.objects.filter(is_active=True).values('id', 'designation', 'unit', 'unit_price')
    data = {}
    for item in items:
        data[str(item['id'])] = {
            'designation': item['designation'],
            'unit': item['unit'],
            'unit_price': float(item['unit_price'] or 0),
        }
    return JsonResponse(data)
