from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import Contract, Invoice, Payment
from .forms import ContractForm, InvoiceForm, PaymentForm
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin
from projects.models import Site

class ContractListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Contract
    template_name = 'revenue/contract_list.html'
    context_object_name = 'contracts'
    header_title = "Revenue: Client Contracts"
    header_subtitle = "Manage project contracts and financial agreements"
    
    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=['DIRECTOR', 'ACCOUNTANT']
        ).exists():
            return [{
                'label': 'New Contract',
                'url': str(reverse_lazy('revenue:contract_create')),
                'icon': 'file-contract',
                'class': 'btn-falcon-primary'
            }]
        return []

    def get_queryset(self):
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return super().get_queryset().filter(site__cabinet__id__in=user_cabinet_ids)

class ContractCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Contract
    form_class = ContractForm
    template_name = 'revenue/contract_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = "Define New Contract"
    header_subtitle = "Register a new client contract for a project"
    back_url = reverse_lazy('revenue:contract_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Revenue', 'url': str(reverse_lazy('revenue:contract_list'))},
            {'title': 'New Contract', 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        site_id = self.kwargs.get('site_id')
        if site_id:
            initial['site'] = get_object_or_404(Site, unique_id=site_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, "Contract created successfully!")
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class ContractUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Contract
    form_class = ContractForm
    template_name = 'revenue/contract_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    
    def get_header_title(self):
        return f"Edit Contract: {self.object.client_name}"

    def get_back_url(self):
        return str(reverse_lazy('revenue:contract_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Revenue', 'url': str(reverse_lazy('revenue:contract_list'))},
            {'title': 'Edit Contract', 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, "Contract updated.")
        return reverse_lazy('projects:site_detail', kwargs={'unique_id': self.object.site.unique_id})

class InvoiceListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Invoice
    template_name = 'revenue/invoice_list.html'
    context_object_name = 'invoices'
    header_title = "Billing: Client Invoices"
    header_subtitle = "Monitor and track all project invoices"

    def get_header_actions(self):
        return [{
            'label': 'New Invoice',
            'url': str(reverse_lazy('revenue:invoice_create')),
            'icon': 'file-invoice-dollar',
            'class': 'btn-falcon-primary'
        }]

    def get_queryset(self):
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return super().get_queryset().filter(contract__site__cabinet__id__in=user_cabinet_ids)

class InvoiceCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'revenue/invoice_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = "Generate New Invoice"
    header_subtitle = "Create a new billing statement for a contract"
    back_url = reverse_lazy('revenue:invoice_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Invoices', 'url': str(reverse_lazy('revenue:invoice_list'))},
            {'title': 'New Generation', 'url': None},
        ]

    def get_initial(self):
        initial = super().get_initial()
        contract_id = self.kwargs.get('contract_id')
        if contract_id:
            initial['contract'] = get_object_or_404(Contract, id=contract_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['contract'].queryset = Contract.objects.filter(site__cabinet__id__in=user_cabinet_ids)
        return form

    def get_success_url(self):
        messages.success(self.request, "Invoice generated successfully!")
        return reverse_lazy('revenue:invoice_detail', kwargs={'pk': self.object.pk})

class InvoiceDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Invoice
    template_name = 'revenue/invoice_detail.html'
    context_object_name = 'invoice'

    def get_header_title(self):
        return f"Invoice: {self.object.invoice_number}"

    def get_header_subtitle(self):
        return f"Amount: ${self.object.amount} | Status: {self.object.status}"

    def get_back_url(self):
        return str(reverse_lazy('revenue:invoice_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Invoices', 'url': str(reverse_lazy('revenue:invoice_list'))},
            {'title': self.object.invoice_number, 'url': None},
        ]

    def get_header_actions(self):
        actions = []
        if self.object.status != 'PAID':
            actions.append({
                'label': 'Record Payment',
                'url': str(reverse_lazy('revenue:payment_create', kwargs={'invoice_id': self.object.id})),
                'icon': 'credit-card',
                'class': 'btn-falcon-success'
            })
        return actions

class PaymentCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'revenue/payment_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER']

    def get_initial(self):
        initial = super().get_initial()
        invoice_id = self.kwargs.get('invoice_id')
        if invoice_id:
            initial['invoice'] = get_object_or_404(Invoice, id=invoice_id)
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        form.fields['invoice'].queryset = Invoice.objects.filter(contract__site__cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        # Update invoice status if amount paid >= invoice amount
        # This is a simple logic, could be more robust
        invoice = self.object.invoice
        total_paid = sum(p.amount for p in invoice.payments.all())
        if total_paid >= invoice.amount:
            invoice.status = 'PAID'
            invoice.save()
        return response

    def get_success_url(self):
        messages.success(self.request, "Payment recorded.")
        return reverse_lazy('revenue:invoice_detail', kwargs={'pk': self.object.invoice.pk})
