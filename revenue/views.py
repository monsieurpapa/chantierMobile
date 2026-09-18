from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from .models import Contract, Invoice, Payment, Devis, SituationTravaux
from chantiermobile.constants import InvoiceStatus, UserRoles, DevisStatus, SituationStatus
from .forms import (
    ContractForm, InvoiceForm, PaymentForm,
    DevisForm, DevisLineFormSet, SituationTravauxForm, SituationLineFormSet,
)
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from projects.models import Site

class ContractListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Contract
    template_name = 'revenue/contract_list.html'
    context_object_name = 'contracts'
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Contrats clients")
    header_subtitle = _("Gérez les contrats et accords financiers des projets")

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]
        ).exists():
            return [{
                'label': _("Nouveau contrat"),
                'url': str(reverse_lazy('revenue:contract_create')),
                'icon': 'file-contract',
                'class': 'btn-falcon-primary'
            }]
        return []

    def get_queryset(self):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return super().get_queryset().filter(site__cabinet=active_cabinet)
            return super().get_queryset()
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return super().get_queryset().filter(site__cabinet__id__in=user_cabinet_ids)

class ContractCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'revenue/contract_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = _("Définir un nouveau contrat")
    header_subtitle = _("Enregistrez un nouveau contrat client pour un projet")
    back_url = reverse_lazy('revenue:contract_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Revenus"), 'url': str(reverse_lazy('revenue:contract_list'))},
            {'title': _("Nouveau contrat"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.kwargs.get('site_id')
        if site_id:
            initial['site'] = get_object_or_404(Site, unique_id=site_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
            else:
                form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, _("Contrat créé avec succès !"))
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class ContractUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'revenue/contract_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier le contrat : %(name)s") % {'name': self.object.client_name}

    def get_back_url(self):
        return str(reverse_lazy('revenue:contract_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Revenus"), 'url': str(reverse_lazy('revenue:contract_list'))},
            {'title': _("Modifier le contrat"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
            else:
                form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, _("Contrat mis à jour avec succès."))
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class InvoiceListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Invoice
    template_name = 'revenue/invoice_list.html'
    context_object_name = 'invoices'
    cabinet_lookup_field = 'contract__site__cabinet'
    header_title = _("Factures clients")
    header_subtitle = _("Suivez toutes les factures des projets")

    def get_header_actions(self):
        return [{
            'label': _("Nouvelle facture"),
            'url': str(reverse_lazy('revenue:invoice_create')),
            'icon': 'file-invoice-dollar',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return super().get_queryset().filter(contract__site__cabinet=active_cabinet)
            return super().get_queryset()
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return super().get_queryset().filter(contract__site__cabinet__id__in=user_cabinet_ids)

class InvoiceCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'revenue/invoice_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = _("Générer une nouvelle facture")
    header_subtitle = _("Créez un relevé de facturation pour un contrat")
    back_url = reverse_lazy('revenue:invoice_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Factures"), 'url': str(reverse_lazy('revenue:invoice_list'))},
            {'title': _("Nouvelle facture"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        contract_id = self.kwargs.get('contract_id')
        if contract_id:
            initial['contract'] = get_object_or_404(Contract, id=contract_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['contract'].queryset = Contract.objects.filter(site__cabinet=active_cabinet)
            else:
                form.fields['contract'].queryset = Contract.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['contract'].queryset = Contract.objects.filter(site__cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, _("Facture générée avec succès !"))
        return reverse_lazy('revenue:invoice_detail', kwargs={'pk': self.object.pk})

class InvoiceDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Invoice
    cabinet_lookup_field = 'contract__site__cabinet'
    template_name = 'revenue/invoice_detail.html'
    context_object_name = 'invoice'

    def get_header_title(self):
        return _("Facture : %(num)s") % {'num': self.object.invoice_number}

    def get_header_subtitle(self):
        return _("Montant : %(amount)s$ | Statut : %(status)s") % {'amount': self.object.amount, 'status': self.object.get_status_display()}

    def get_back_url(self):
        return str(reverse_lazy('revenue:invoice_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Factures"), 'url': str(reverse_lazy('revenue:invoice_list'))},
            {'title': self.object.invoice_number, 'url': None},
        ]

    def get_header_actions(self):
        actions = []
        if self.object.status != InvoiceStatus.PAID:
            actions.append({
                'label': _("Enregistrer un paiement"),
                'url': str(reverse_lazy('revenue:payment_create', kwargs={'invoice_id': self.object.id})),
                'icon': 'credit-card',
                'class': 'btn-falcon-success'
            })
        return actions

class PaymentListView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Payment
    template_name = 'revenue/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 50
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = _("Historique des paiements")
    header_subtitle = _("Suivez tous les paiements reçus des factures")

    def get_header_actions(self):
        return [{
            'label': _("Nouveau paiement"),
            'url': str(reverse_lazy('revenue:payment_create_standalone')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = Payment.objects.select_related('invoice__contract__site').order_by('-payment_date')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(invoice__contract__site__cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(invoice__contract__site__cabinet__id__in=user_cabinet_ids)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.object_list  # already evaluated by BaseListView.get()
        context['total_amount'] = qs.aggregate(total=Sum('amount'))['total'] or 0
        context['total_count'] = qs.count()
        return context

class PaymentCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'revenue/payment_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER']
    header_title = _("Enregistrer un paiement")
    header_subtitle = _("Enregistrez un paiement reçu contre une facture")
    back_url = reverse_lazy('revenue:invoice_list')

    def get_initial(self):
        initial = super().get_initial()
        invoice_id = self.kwargs.get('invoice_id')
        if invoice_id:
            initial['invoice'] = get_object_or_404(Invoice, id=invoice_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        payable_statuses = [InvoiceStatus.SENT, InvoiceStatus.OVERDUE]
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['invoice'].queryset = Invoice.objects.filter(
                    contract__site__cabinet=active_cabinet,
                    status__in=payable_statuses,
                )
            else:
                form.fields['invoice'].queryset = Invoice.objects.filter(status__in=payable_statuses)
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['invoice'].queryset = Invoice.objects.filter(
                contract__site__cabinet__id__in=user_cabinet_ids,
                status__in=payable_statuses,
            )
        return form

    def form_valid(self, form):
        # Payment.save() auto-marks the invoice PAID once fully covered.
        return super().form_valid(form)

    def get_success_url(self):
        messages.success(self.request, _("Paiement enregistré avec succès."))
        return reverse_lazy('revenue:invoice_detail', kwargs={'pk': self.object.invoice.pk})


# --- Devis views ---

class DevisListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Devis
    template_name = 'revenue/devis_list.html'
    context_object_name = 'devis_list'
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Devis")
    header_subtitle = _("Gérez les devis envoyés aux clients")

    def get_header_actions(self):
        return [{
            'label': _("Nouveau devis"),
            'url': str(reverse_lazy('revenue:devis_create')),
            'icon': 'file-signature',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().select_related('site').prefetch_related('lines')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(site__cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(site__cabinet__id__in=user_cabinet_ids)


class DevisCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Devis
    form_class = DevisForm
    template_name = 'revenue/devis_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
    header_title = _("Créer un devis")
    header_subtitle = _("Préparez un devis détaillé pour un client")
    back_url = reverse_lazy('revenue:devis_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Devis"), 'url': str(reverse_lazy('revenue:devis_list'))},
            {'title': _("Nouveau devis"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.kwargs.get('site_id')
        if site_id:
            initial['site'] = get_object_or_404(Site, unique_id=site_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
            else:
                form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = DevisLineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = DevisLineFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("Devis '%(num)s' créé avec %(count)s ligne(s).") % {
                'num': self.object.devis_number, 'count': self.object.total_items,
            })
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('revenue:devis_detail', kwargs={'pk': self.object.pk})


class DevisUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Devis
    form_class = DevisForm
    template_name = 'revenue/devis_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Modifier le devis : %(num)s") % {'num': self.object.devis_number}

    def get_back_url(self):
        return str(reverse_lazy('revenue:devis_detail', kwargs={'pk': self.object.pk}))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Devis"), 'url': str(reverse_lazy('revenue:devis_list'))},
            {'title': self.object.devis_number, 'url': str(reverse_lazy('revenue:devis_detail', kwargs={'pk': self.object.pk}))},
            {'title': _("Modifier"), 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
            else:
                form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = DevisLineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = DevisLineFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("Devis mis à jour avec succès."))
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('revenue:devis_detail', kwargs={'pk': self.object.pk})


class DevisDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Devis
    cabinet_lookup_field = 'site__cabinet'
    template_name = 'revenue/devis_detail.html'
    context_object_name = 'devis'

    def get_queryset(self):
        return super().get_queryset().select_related('site').prefetch_related('lines')

    def get_header_title(self):
        return _("Devis : %(num)s") % {'num': self.object.devis_number}

    def get_header_subtitle(self):
        return _("Client : %(client)s | Total HT : %(total)s | Statut : %(status)s") % {
            'client': self.object.client_name,
            'total': self.object.total_ht,
            'status': self.object.get_status_display(),
        }

    def get_back_url(self):
        return str(reverse_lazy('revenue:devis_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Devis"), 'url': str(reverse_lazy('revenue:devis_list'))},
            {'title': self.object.devis_number, 'url': None},
        ]

    def get_header_actions(self):
        actions = []
        if self.object.status == DevisStatus.BROUILLON:
            actions.append({
                'label': _("Modifier"),
                'url': str(reverse_lazy('revenue:devis_update', kwargs={'pk': self.object.pk})),
                'icon': 'edit',
                'class': 'btn-falcon-secondary'
            })
        return actions


@login_required
def devis_send(request, pk):
    devis = get_object_or_404(Devis, pk=pk)
    if request.method == 'POST':
        if devis.status == DevisStatus.BROUILLON:
            devis.status = DevisStatus.ENVOYE
            try:
                devis.full_clean()
                devis.save()
                messages.success(request, _("Devis envoyé au client."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Seul un devis en brouillon peut être envoyé."))
    return redirect('revenue:devis_detail', pk=pk)


@login_required
def devis_accept(request, pk):
    devis = get_object_or_404(Devis, pk=pk)
    if request.method == 'POST':
        try:
            contract = devis.accept_and_create_contract(changed_by=request.user)
            messages.success(request, _("Devis accepté — contrat créé pour %(site)s.") % {'site': devis.site.name})
            return redirect('projects:site_detail', unique_id=devis.site.unique_id)
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('revenue:devis_detail', pk=pk)


@login_required
def devis_reject(request, pk):
    devis = get_object_or_404(Devis, pk=pk)
    if request.method == 'POST':
        if devis.status in [DevisStatus.BROUILLON, DevisStatus.ENVOYE]:
            devis.status = DevisStatus.REFUSE
            try:
                devis.full_clean()
                devis.save()
                messages.success(request, _("Devis refusé."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Ce devis ne peut pas être refusé dans son statut actuel."))
    return redirect('revenue:devis_detail', pk=pk)


# --- Situation de travaux views ---

class SituationTravauxListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = SituationTravaux
    template_name = 'revenue/situation_list.html'
    context_object_name = 'situations'
    cabinet_lookup_field = 'contract__site__cabinet'
    header_title = _("Situations de travaux")
    header_subtitle = _("Suivez l'avancement facturable des chantiers sous contrat")

    def get_header_actions(self):
        return [{
            'label': _("Nouvelle situation"),
            'url': str(reverse_lazy('revenue:situation_create')),
            'icon': 'tasks',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        qs = super().get_queryset().select_related('contract__site').prefetch_related('lines')
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                return qs.filter(contract__site__cabinet=active_cabinet)
            return qs
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return qs.filter(contract__site__cabinet__id__in=user_cabinet_ids)


class SituationTravauxCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = SituationTravaux
    form_class = SituationTravauxForm
    template_name = 'revenue/situation_form.html'
    allowed_roles = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
    header_title = _("Nouvelle situation de travaux")
    header_subtitle = _("Déclarez l'avancement cumulé d'un contrat pour une période")
    back_url = reverse_lazy('revenue:situation_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Situations"), 'url': str(reverse_lazy('revenue:situation_list'))},
            {'title': _("Nouvelle situation"), 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        contract_id = self.kwargs.get('contract_id')
        if contract_id:
            initial['contract'] = get_object_or_404(Contract, id=contract_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['contract'].queryset = Contract.objects.filter(site__cabinet=active_cabinet)
            else:
                form.fields['contract'].queryset = Contract.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['contract'].queryset = Contract.objects.filter(site__cabinet__id__in=user_cabinet_ids)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['lines_formset'] = SituationLineFormSet(self.request.POST, instance=self.object)
        else:
            context['lines_formset'] = SituationLineFormSet(instance=self.object)
            contract_id = self.kwargs.get('contract_id') or self.request.GET.get('contract')
            devis_line_field = context['lines_formset'].empty_form.fields.get('devis_line')
            if contract_id and devis_line_field is not None:
                contract = Contract.objects.filter(id=contract_id).first()
                if contract and contract.source_devis:
                    queryset = contract.source_devis.lines.all()
                    devis_line_field.queryset = queryset
                    for form in context['lines_formset'].forms:
                        form.fields['devis_line'].queryset = queryset
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        lines_formset = context['lines_formset']
        # Restrict devis_line choices to the contract's own devis lines before validating.
        contract = form.instance.contract
        if contract and contract.source_devis:
            for lf in lines_formset.forms:
                lf.fields['devis_line'].queryset = contract.source_devis.lines.all()
        if lines_formset.is_valid():
            self.object = form.save()
            lines_formset.instance = self.object
            lines_formset.save()
            messages.success(self.request, _("Situation n°%(num)s créée.") % {'num': self.object.numero})
            return HttpResponseRedirect(self.get_success_url())
        return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('revenue:situation_detail', kwargs={'pk': self.object.pk})


class SituationTravauxDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = SituationTravaux
    cabinet_lookup_field = 'contract__site__cabinet'
    template_name = 'revenue/situation_detail.html'
    context_object_name = 'situation'

    def get_queryset(self):
        return super().get_queryset().select_related('contract__site').prefetch_related('lines__devis_line')

    def get_header_title(self):
        return _("Situation n°%(num)s") % {'num': self.object.numero}

    def get_header_subtitle(self):
        return _("Chantier : %(site)s | Montant période : %(amount)s | Statut : %(status)s") % {
            'site': self.object.contract.site.name,
            'amount': self.object.total_ht_period,
            'status': self.object.get_status_display(),
        }

    def get_back_url(self):
        return str(reverse_lazy('revenue:situation_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Situations"), 'url': str(reverse_lazy('revenue:situation_list'))},
            {'title': f"N°{self.object.numero}", 'url': None},
        ]

    def get_header_actions(self):
        actions = []
        if self.object.status == SituationStatus.VALIDEE:
            actions.append({
                'label': _("Générer la facture"),
                'url': str(reverse_lazy('revenue:situation_generate_invoice', kwargs={'pk': self.object.pk})),
                'icon': 'file-invoice-dollar',
                'class': 'btn-falcon-success'
            })
        return actions


@login_required
def situation_validate(request, pk):
    situation = get_object_or_404(SituationTravaux, pk=pk)
    if request.method == 'POST':
        if situation.status == SituationStatus.BROUILLON:
            situation.status = SituationStatus.VALIDEE
            try:
                situation.full_clean()
                situation.save()
                messages.success(request, _("Situation validée."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Seule une situation en brouillon peut être validée."))
    return redirect('revenue:situation_detail', pk=pk)


@login_required
def situation_generate_invoice(request, pk):
    situation = get_object_or_404(SituationTravaux, pk=pk)
    if request.method == 'POST':
        try:
            invoice = situation.generate_invoice(changed_by=request.user)
            messages.success(request, _("Facture %(num)s générée.") % {'num': invoice.invoice_number})
            return redirect('revenue:invoice_detail', pk=invoice.pk)
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('revenue:situation_detail', pk=pk)
