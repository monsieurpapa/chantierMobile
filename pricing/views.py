from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem, DQE
from .forms import PriceLibraryItemForm, DQEForm, DQELineFormSet
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from chantiermobile.constants import UserRoles


class PriceLibraryItemListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
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
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Ajouter un article"),
                'url': str(reverse_lazy('pricing:price_item_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []


class PriceLibraryItemCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = PriceLibraryItem
    form_class = PriceLibraryItemForm
    template_name = 'pricing/price_item_form.html'
    success_url = reverse_lazy('pricing:price_item_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
    header_title = _("Ajouter un article au catalogue de prix")
    header_subtitle = _("Définir un nouveau prix unitaire réutilisable")
    back_url = reverse_lazy('pricing:price_item_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Bibliothèque de Prix"), 'url': str(reverse_lazy('pricing:price_item_list'))},
            {'title': _("Nouvel article"), 'url': None},
        ]

    def form_valid(self, form):
        from django.contrib import messages
        cabinet = get_session_cabinet(self.request)
        if not cabinet:
            if self.request.user.is_superuser:
                from accounts.models import Cabinet
                cabinet = Cabinet.objects.order_by('created_at').first()
            elif self.request.user.cabinet_roles.exists():
                cabinet = self.request.user.cabinet_roles.first().cabinet
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Article '%(name)s' ajouté à la bibliothèque de prix.") % {'name': form.instance.designation})
        return super().form_valid(form)


class PriceLibraryItemUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = PriceLibraryItem
    form_class = PriceLibraryItemForm
    template_name = 'pricing/price_item_form.html'
    success_url = reverse_lazy('pricing:price_item_list')
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

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
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.CHIEF_ENGINEER]
        ).exists():
            return [{
                'label': _("Nouveau DQE"),
                'url': str(reverse_lazy('pricing:dqe_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []


class DQECreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = DQE
    form_class = DQEForm
    template_name = 'pricing/dqe_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']
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

        cabinet = get_session_cabinet(self.request)
        if not cabinet:
            if self.request.user.is_superuser:
                from accounts.models import Cabinet
                cabinet = Cabinet.objects.order_by('created_at').first()
            elif self.request.user.cabinet_roles.exists():
                cabinet = self.request.user.cabinet_roles.first().cabinet
        form.instance.cabinet = cabinet

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
    model = DQE
    form_class = DQEForm
    template_name = 'pricing/dqe_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER']

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
    materials.views.materials_data_api."""
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
