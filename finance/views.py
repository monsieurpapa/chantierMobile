from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
    header_title = _("Gestion des dépenses")
    header_subtitle = _("Suivez et approuvez les dépenses du projet")
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'category', 'requester')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_header_actions(self):
        return [{
            'label': _("Soumettre une dépense"),
            'url': str(reverse_lazy('finance:expense_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]

class ExpenseCreateView(LoginRequiredMixin, PageHeaderMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'finance/expense_form.html'
    success_url = reverse_lazy('finance:expense_list')
    header_title = _("Nouvelle demande de dépense")
    header_subtitle = _("Soumettez une nouvelle dépense pour approbation")
    back_url = reverse_lazy('finance:expense_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Finance"), 'url': str(reverse_lazy('finance:expense_list'))},
            {'title': _("Nouvelle demande"), 'url': None},
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
        messages.success(self.request, _("Demande de dépense soumise avec succès !"))
        return super().form_valid(form)

class ExpenseDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    model = Expense
    context_object_name = 'expense'
    template_name = 'finance/expense_detail.html'

    def get_header_title(self):
        return _("Dépense : %(name)s") % {'name': self.object.category.name}

    def get_header_subtitle(self):
        return _("Montant : %(amount)s$ | Chantier : %(site)s") % {'amount': self.object.amount, 'site': self.object.site.name}

    def get_back_url(self):
        return str(reverse_lazy('finance:expense_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Finance"), 'url': str(reverse_lazy('finance:expense_list'))},
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
class BudgetListView(LoginRequiredMixin, CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Budgets des projets")
    header_subtitle = _("Surveillez et gérez les budgets de construction")

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]
        ).exists():
            return [{
                'label': _("Créer un budget"),
                'url': str(reverse_lazy('finance:budget_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class BudgetCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = _("Créer un budget")
    header_subtitle = _("Définissez le plan financier pour un chantier")
    back_url = reverse_lazy('finance:budget_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Budgets"), 'url': str(reverse_lazy('finance:budget_list'))},
            {'title': _("Nouveau budget"), 'url': None},
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
        messages.success(self.request, _("Budget créé pour %(site)s avec succès !") % {'site': form.instance.site.name})
        return super().form_valid(form)

class BudgetDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = Budget
    template_name = 'finance/budget_detail.html'
    context_object_name = 'budget'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT', 'CHIEF_ENGINEER']
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return _("Budget : %(name)s") % {'name': self.object.site.name}

    def get_header_subtitle(self):
        return _("Du %(start)s au %(end)s") % {'start': self.object.start_date, 'end': self.object.end_date}

    def get_back_url(self):
        return str(reverse_lazy('finance:budget_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Budgets"), 'url': str(reverse_lazy('finance:budget_list'))},
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
        today = timezone.localdate()
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
        return _("Modifier le budget : %(name)s") % {'name': self.object.site.name}

    def get_back_url(self):
        return str(reverse_lazy('finance:budget_list'))

    def get_breadcrumb_items(self):
        return [
            {'title': _("Budgets"), 'url': str(reverse_lazy('finance:budget_list'))},
            {'title': self.object.site.name, 'url': None},
            {'title': _("Modifier"), 'url': None},
        ]

    def form_valid(self, form):
        messages.success(self.request, _("Budget mis à jour pour %(site)s avec succès !") % {'site': form.instance.site.name})
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
