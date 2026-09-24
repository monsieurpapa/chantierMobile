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
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from projects.models import Site

# Roles allowed to send/accept/reject a Devis or validate/invoice a
# Situation de travaux — mirrors DevisCreateView/SituationTravauxCreateView's
# allowed_roles and the has_role gate on the corresponding detail templates.
DEVIS_ACTION_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']
# Mirrors InvoiceCreateView/PaymentListView's allowed_roles — sending or
# cancelling an invoice is the same "who can touch billing" circle as
# creating one in the first place.
INVOICE_ACTION_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']

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
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.ACCOUNTANT]
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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

    # No status-driven action (envoyer/annuler/enregistrer un paiement) is
    # added here on purpose: those live in a single, properly role-gated
    # "Actions" card in invoice_detail.html instead — having both a
    # header-level action AND a body-level one showed "Enregistrer un
    # paiement" twice on the same page, and the header version wasn't
    # role-gated (showed to any viewer, including one who'd get redirected
    # on click) nor status-gated correctly (it showed for DRAFT/CANCELLED
    # invoices too, which PaymentCreateView's own queryset never actually
    # accepts). PDF export has none of those problems — it's a read-only
    # action available at any status, to anyone who can already view this
    # page (CabinetAccessMixin), so it's safe as a header action.
    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': str(reverse_lazy('revenue:invoice_pdf', kwargs={'pk': self.object.pk})),
            'icon': 'file-pdf',
            'class': 'btn-falcon-default',
        }]


@login_required
def invoice_pdf(request, pk):
    """PDF export of a single invoice — a document to hand to the client,
    not a multi-row report, so it reuses render_table_report_pdf's layout
    as a simple two-column "field / value" table rather than a list."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if not request.user.is_superuser:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        if invoice.contract.site.cabinet_id not in user_cabinet_ids:
            messages.error(request, _("Vous n'avez pas accès à cette facture."))
            return redirect('revenue:invoice_list')

    from core.pdf_utils import render_table_report_pdf
    contract = invoice.contract
    cabinet = contract.site.cabinet
    payments_total = invoice.payments.aggregate(total=Sum('amount'))['total'] or 0
    rows = [
        (_("Émetteur"), cabinet.name),
        (_("Client"), contract.client_name),
        (_("Chantier"), contract.site.name),
        (_("Numéro de facture"), invoice.invoice_number),
        (_("Date d'émission"), invoice.issued_date.strftime('%d/%m/%Y')),
        (_("Date d'échéance"), invoice.due_date.strftime('%d/%m/%Y')),
        (_("Montant"), f"{invoice.amount:.2f} $"),
        (_("Montant payé"), f"{payments_total:.2f} $"),
        (_("Statut"), invoice.get_status_display()),
    ]
    return render_table_report_pdf(
        filename=f"facture-{invoice.invoice_number}.pdf",
        title=_("Facture %(num)s") % {'num': invoice.invoice_number},
        subtitle=cabinet.address,
        columns=[_("Champ"), _("Valeur")],
        rows=rows,
        generated_by=request.user.get_full_name() or request.user.username,
    )


@login_required
def contract_pdf(request, pk):
    """PDF export of a single contract — same key/value document layout
    as invoice_pdf."""
    contract = get_object_or_404(Contract, pk=pk)
    if not request.user.is_superuser:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        if contract.site.cabinet_id not in user_cabinet_ids:
            messages.error(request, _("Vous n'avez pas accès à ce contrat."))
            return redirect('revenue:contract_list')

    from core.pdf_utils import render_table_report_pdf
    cabinet = contract.site.cabinet
    rows = [
        (_("Émetteur"), cabinet.name),
        (_("Client"), contract.client_name),
        (_("Chantier"), contract.site.name),
        (_("Valeur du contrat"), f"{contract.total_value:.2f} $"),
        (_("Dette avenants"), f"{contract.avenant_debt:.2f} $"),
        (_("Date de signature"), contract.signed_date.strftime('%d/%m/%Y')),
        (_("Total payé à ce jour"), f"{contract.total_paid:.2f} $"),
    ]
    return render_table_report_pdf(
        filename=f"contrat-{contract.pk}-{contract.client_name}.pdf",
        title=_("Contrat — %(client)s") % {'client': contract.client_name},
        subtitle=cabinet.address,
        columns=[_("Champ"), _("Valeur")],
        rows=rows,
        generated_by=request.user.get_full_name() or request.user.username,
    )


class PaymentListView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Payment
    template_name = 'revenue/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 50
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT', 'CASHIER']
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
        response = super().form_valid(form)
        from .notifications import notify_directors_of_payment
        notify_directors_of_payment(self.object, recorded_by=self.request.user)
        return response

    def get_success_url(self):
        messages.success(self.request, _("Paiement enregistré avec succès."))
        return reverse_lazy('revenue:invoice_detail', kwargs={'pk': self.object.invoice.pk})


@login_required
def invoice_send(request, pk):
    """DRAFT → SENT. Without this action (and invoice_cancel below), an
    invoice created as DRAFT — the model's own default, and the only status
    the create form offers since 'status' isn't a user-editable field — had
    no way to ever become payable: PaymentCreateView's own queryset only
    ever offers SENT/OVERDUE invoices, and there was no InvoiceUpdateView
    anywhere to fix a stuck DRAFT. Mirrors devis_send/situation_validate."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        if not can_act_for_cabinet(request, invoice.contract.site.cabinet, INVOICE_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:invoice_detail', pk=pk)
        if invoice.status == InvoiceStatus.DRAFT:
            from core.models import StatusChangeLog
            old_status = invoice.status
            invoice.status = InvoiceStatus.SENT
            try:
                invoice.full_clean()
                invoice.save()
                StatusChangeLog.log(
                    invoice, changed_by=request.user,
                    old_status=old_status, new_status=InvoiceStatus.SENT,
                    note=_('Facture envoyée au client.'),
                )
                messages.success(request, _("Facture envoyée au client."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Seule une facture en brouillon peut être envoyée."))
    return redirect('revenue:invoice_detail', pk=pk)


@login_required
def invoice_cancel(request, pk):
    """DRAFT → CANCELLED — lets a director/accountant kill a mistakenly
    created draft invoice instead of it sitting there forever with no way
    to remove or correct it."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        if not can_act_for_cabinet(request, invoice.contract.site.cabinet, INVOICE_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:invoice_detail', pk=pk)
        if invoice.status == InvoiceStatus.DRAFT:
            from core.models import StatusChangeLog
            old_status = invoice.status
            invoice.status = InvoiceStatus.CANCELLED
            try:
                invoice.full_clean()
                invoice.save()
                StatusChangeLog.log(
                    invoice, changed_by=request.user,
                    old_status=old_status, new_status=InvoiceStatus.CANCELLED,
                    note=_('Facture annulée.'),
                )
                messages.success(request, _("Facture annulée."))
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Seule une facture en brouillon peut être annulée."))
    return redirect('revenue:invoice_detail', pk=pk)


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
                qs = qs.filter(site__cabinet=active_cabinet)
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


class DevisCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Devis
    form_class = DevisForm
    template_name = 'revenue/devis_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']
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
        has_photo = bool(self.request.POST.get('photo-clear') is None and (
            (self.request.FILES.get('photo') if self.request.POST else None)
            or (self.object and getattr(self.object, 'photo', None))
        ))
        if self.request.POST:
            formset = DevisLineFormSet(self.request.POST, instance=self.object)
        else:
            formset = DevisLineFormSet(instance=self.object)
        # A devis attached as a photo doesn't need its line items typed in
        # manually — only require at least one line when there's no photo.
        formset.min_num = 0 if has_photo else 1
        formset.validate_min = not has_photo
        context['lines_formset'] = formset
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']
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
        has_photo = bool(self.request.POST.get('photo-clear') is None and (
            (self.request.FILES.get('photo') if self.request.POST else None)
            or (self.object and getattr(self.object, 'photo', None))
        ))
        if self.request.POST:
            formset = DevisLineFormSet(self.request.POST, instance=self.object)
        else:
            formset = DevisLineFormSet(instance=self.object)
        # A devis attached as a photo doesn't need its line items typed in
        # manually — only require at least one line when there's no photo.
        formset.min_num = 0 if has_photo else 1
        formset.validate_min = not has_photo
        context['lines_formset'] = formset
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
        if not can_act_for_cabinet(request, devis.site.cabinet, DEVIS_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:devis_detail', pk=pk)
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
        if not can_act_for_cabinet(request, devis.site.cabinet, DEVIS_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:devis_detail', pk=pk)
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
        if not can_act_for_cabinet(request, devis.site.cabinet, DEVIS_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:devis_detail', pk=pk)
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']
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
        if not can_act_for_cabinet(request, situation.contract.site.cabinet, DEVIS_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:situation_detail', pk=pk)
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
        if not can_act_for_cabinet(request, situation.contract.site.cabinet, DEVIS_ACTION_ROLES):
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
            return redirect('revenue:situation_detail', pk=pk)
        try:
            invoice = situation.generate_invoice(changed_by=request.user)
            messages.success(request, _("Facture %(num)s générée.") % {'num': invoice.invoice_number})
            return redirect('revenue:invoice_detail', pk=invoice.pk)
        except ValidationError as e:
            messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
    return redirect('revenue:situation_detail', pk=pk)
