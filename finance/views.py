from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from decimal import Decimal
from .models import Expense, ExpenseApproval, Budget
from .forms import ExpenseForm, BudgetForm
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet
from chantiermobile.constants import ExpenseStatus, UserRoles

class ExpenseListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Expense
    context_object_name = 'expenses'
    template_name = 'finance/expense_list.html'
    paginate_by = 20
    header_title = "Expense Management"
    header_subtitle = "Track and approve project expenses"
    cabinet_lookup_field = 'site__cabinet'
    
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
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet)
            else:
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
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, "This expense belongs to a different cabinet than your active session.")
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]).exists():
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
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, "This expense belongs to a different cabinet than your active session.")
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.CASHIER]).exists():
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
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]
        ).exists():
            return [{
                'label': 'Create Budget',
                'url': str(reverse_lazy('finance:budget_create')),
                'icon': 'plus',
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

class BudgetCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = "Create Budget"
    header_subtitle = "Set the financial plan for a project site"
    back_url = reverse_lazy('finance:budget_list')

    def get_breadcrumb_items(self):
        return [
            {'title': 'Budgets', 'url': str(reverse_lazy('finance:budget_list'))},
            {'title': 'New Budget', 'url': None},
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

    def form_valid(self, form):
        messages.success(self.request, f"Budget created for {form.instance.site.name} successfully!")
        return super().form_valid(form)

class BudgetDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Budget
    template_name = 'finance/budget_detail.html'
    context_object_name = 'budget'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return f"Budget: {self.object.site.name}"

    def get_header_subtitle(self):
        return f"{self.object.start_date} → {self.object.end_date}"

    def get_back_url(self):
        return str(reverse_lazy('finance:budget_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Budgets', 'url': str(reverse_lazy('finance:budget_list'))},
            {'title': self.object.site.name, 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget = self.object
        total = budget.total_amount
        spent = budget.get_spent_amount()
        remaining = total - Decimal(spent)

        context['spent'] = spent
        context['remaining'] = remaining
        context['usage_pct'] = round(float(spent) / float(total) * 100, 1) if total else 0

        # Spend by category (within budget period)
        category_breakdown = (
            budget.site.expenses
            .filter(
                status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID],
                expense_date__gte=budget.start_date,
                expense_date__lte=budget.end_date,
            )
            .values('category__name')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )
        context['category_breakdown'] = category_breakdown

        # Spend rate forecast: daily burn rate × days remaining
        today = timezone.now().date()
        elapsed_days = max((today - budget.start_date).days, 1)
        total_days = max((budget.end_date - budget.start_date).days, 1)
        remaining_days = max((budget.end_date - today).days, 0)
        daily_burn = float(spent) / elapsed_days
        forecast_total = daily_burn * total_days
        context['daily_burn'] = round(daily_burn, 2)
        context['remaining_days'] = remaining_days
        context['forecast_total'] = round(forecast_total, 2)
        context['forecast_overrun'] = forecast_total > float(total)

        # Recent expenses (all statuses)
        context['recent_expenses'] = (
            budget.site.expenses
            .filter(expense_date__gte=budget.start_date, expense_date__lte=budget.end_date)
            .select_related('category', 'requester')
            .order_by('-expense_date')[:10]
        )
        return context


class BudgetUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return f"Edit Budget: {self.object.site.name}"

    def get_back_url(self):
        return str(reverse_lazy('finance:budget_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': 'Budgets', 'url': str(reverse_lazy('finance:budget_list'))},
            {'title': self.object.site.name, 'url': None},
            {'title': 'Edit', 'url': None},
        ]

    def form_valid(self, form):
        messages.success(self.request, f"Budget for {form.instance.site.name} updated successfully!")
        return super().form_valid(form)

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
