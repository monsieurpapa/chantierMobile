from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from .models import PriceLibraryItem
from .forms import PriceLibraryItemForm
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
