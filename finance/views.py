from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import Expense, ExpenseApproval, Budget
from .forms import ExpenseForm, BudgetForm
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin
from chantiermobile.constants import ExpenseStatus

class ExpenseListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Expense
    context_object_name = 'expenses'
    template_name = 'finance/expense_list.html'
    paginate_by = 20
    header_title = "Expense Management"
    header_subtitle = "Track and approve project expenses"
    
    def get_header_actions(self):
        return [{
            'label': 'Request Expense',
            'url': str(reverse_lazy('finance:expense_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

class ExpenseCreateView(LoginRequiredMixin, PageHeaderMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'finance/expense_form.html'
    success_url = reverse_lazy('finance:expense_list')
    header_title = "New Expense Request"
    header_subtitle = "Submit a new expense for approval"
    back_url = reverse_lazy('finance:expense_list')
    
    def get_breadcrumb_items(self):
        return [
            {'title': 'Finance', 'url': str(reverse_lazy('finance:expense_list'))},
            {'title': 'New Request', 'url': None},
        ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        form.instance.requester = self.request.user
        from django.contrib import messages
        messages.success(self.request, "Expense request submitted successfully!")
        return super().form_valid(form)

class ExpenseDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    model = Expense
    context_object_name = 'expense'
    template_name = 'finance/expense_detail.html'

    def get_header_title(self):
        return f"Expense: {self.object.category.name}"

    def get_header_subtitle(self):
        return f"Amount: ${self.object.amount} | Site: {self.object.site.name}"

    def get_back_url(self):
        return str(reverse_lazy('finance:expense_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Finance', 'url': str(reverse_lazy('finance:expense_list'))},
            {'title': f"EX-{self.object.id}", 'url': None},
        ]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)
        return qs

@login_required
def approve_expense(request, pk):
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=['DIRECTOR', 'ACCOUNTANT']).exists():
            try:
                expense.approve(request.user, comments=request.POST.get('comments', ''))
                messages.success(request, "Expense approved.")
            except ValidationError as e:
                messages.error(request, f"Could not approve expense: {e}")
        else:
            messages.error(request, "Unauthorized.")
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

@login_required
def mark_expense_paid(request, pk):
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=['DIRECTOR', 'CASHIER']).exists():
            # Validate expense can be paid
            if not expense.can_be_paid():
                messages.error(request, f"Only approved expenses can be paid. Current status: {expense.status}.")
            else:
                try:
                    expense.status = ExpenseStatus.PAID
                    expense.full_clean()
                    expense.save()
                    messages.success(request, "Expense marked as PAID.")
                except ValidationError as e:
                    messages.error(request, f"Error marking expense as paid: {str(e)}")
        else:
            messages.error(request, "Unauthorized.")
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

# Budget Views
class BudgetListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CHIEF_ENGINEER']
    header_title = "Project Budgets"
    header_subtitle = "Monitor and manage construction budgets"
    
    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=['DIRECTOR', 'ACCOUNTANT']
        ).exists():
            return [{
                'label': 'Create Budget',
                'url': str(reverse_lazy('finance:budget_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

    def get_queryset(self):
        user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        return super().get_queryset().filter(site__cabinet__id__in=user_cabinet_ids)

class BudgetCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        messages.success(self.request, f"Budget created for {form.instance.site.name} successfully!")
        return super().form_valid(form)

class BudgetUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']

    def form_valid(self, form):
        messages.success(self.request, f"Budget for {form.instance.site.name} updated successfully!")
        return super().form_valid(form)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.request.user.is_superuser:
            form.fields['site'].queryset = Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form
