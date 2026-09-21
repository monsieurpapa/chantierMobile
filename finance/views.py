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

# Roles that may view the expenses report / export it to PDF — mirrors
# core.dashboard.FINANCIAL_ROLES (the same audience that sees the
# dashboard's money widgets).
EXPENSE_REPORT_ROLES = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER']

class ExpenseListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Expense
    context_object_name = 'expenses'
    template_name = 'finance/expense_list.html'
    paginate_by = 20
    header_title = _("Gestion des dépenses")
    header_subtitle = _("Suivez et approuvez les dépenses du projet")
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'category', 'requester').order_by('-created_at')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_header_actions(self):
        actions = [{
            'label': _("Soumettre une dépense"),
            'url': str(reverse_lazy('finance:expense_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary'
        }]
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=EXPENSE_REPORT_ROLES
        ).exists():
            actions.append({
                'label': _("Rapport"),
                'url': str(reverse_lazy('finance:expense_report')),
                'icon': 'file-alt',
                'class': 'btn-falcon-default'
            })
        return actions

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
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]).exists():
            try:
                expense.approve(request.user, comments=request.POST.get('comments', ''))
                messages.success(request, _("Dépense approuvée."))
            except ValidationError as e:
                messages.error(request, _("Impossible d'approuver la dépense : %(error)s") % {'error': e})
        else:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

@login_required
def reject_expense(request, pk):
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.ACCOUNTANT]).exists():
            if expense.status != ExpenseStatus.PENDING:
                messages.error(request, _("Seule une dépense en attente peut être rejetée."))
            else:
                try:
                    expense.reject(request.user, comments=request.POST.get('comments', ''))
                    messages.success(request, _("Dépense rejetée."))
                except ValidationError as e:
                    messages.error(request, _("Impossible de rejeter la dépense : %(error)s") % {'error': e})
        else:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

@login_required
def mark_expense_paid(request, pk):
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.CASHIER]).exists():
            # Validate expense can be paid
            if not expense.can_be_paid():
                messages.error(request, _("Seules les dépenses approuvées peuvent être payées. Statut actuel : %(status)s.") % {'status': expense.get_status_display()})
            else:
                try:
                    expense.status = ExpenseStatus.PAID
                    expense.full_clean()
                    expense.save()
                    messages.success(request, _("Dépense marquée comme PAYÉE."))
                except ValidationError as e:
                    messages.error(request, _("Erreur lors du paiement de la dépense : %(error)s") % {'error': str(e)})
        else:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
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


@login_required
def site_personnel_data(request):
    """JSON endpoint used by the expense form's "Main d'œuvre" personnel
    picker: given a ?site=<id>, returns the personnel currently assigned to
    that site, so the dropdown only proposes people actually working there
    (mirrors materials.views.materials_data_api's role as a dynamic-select
    data source)."""
    from django.http import JsonResponse
    from personnel.models import Personnel

    site_id = request.GET.get('site')
    if not site_id:
        return JsonResponse({'results': []})

    site_qs = Site.objects.filter(pk=site_id)
    if not request.user.is_superuser:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        site_qs = site_qs.filter(cabinet__id__in=user_cabinet_ids)
    site = site_qs.first()
    if not site:
        return JsonResponse({'results': []})

    personnel = Personnel.objects.filter(assignments__site=site).distinct().order_by('first_name', 'last_name')
    return JsonResponse({
        'results': [{'id': p.id, 'text': p.get_full_name()} for p in personnel]
    })


def _expense_report_queryset(request):
    """Shared filtering for the expense report view and its PDF export:
    cabinet-scoped, optionally filtered by site and by expense_date range."""
    qs = Expense.objects.select_related('site', 'category', 'requester', 'personnel').order_by('-expense_date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

    site_id = request.GET.get('site')
    if site_id:
        qs = qs.filter(site_id=site_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    period = request.GET.get('period')
    today = timezone.localdate()
    if period == 'week':
        qs = qs.filter(expense_date__gte=today - timezone.timedelta(days=7))
    elif period == 'month':
        qs = qs.filter(expense_date__gte=today.replace(day=1))

    return qs


class ExpenseReportView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Filterable expense report (by chantier, by date range/period) with a
    PDF export — the "Rapport" the cashier asked for alongside the
    dépenses form."""
    model = Expense
    template_name = 'finance/expense_report.html'
    context_object_name = 'expenses'
    allowed_roles = EXPENSE_REPORT_ROLES
    header_title = _("Rapport des dépenses")
    header_subtitle = _("Filtrez par chantier, période ou plage de dates et exportez en PDF")
    back_url = reverse_lazy('finance:expense_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Finance"), 'url': str(reverse_lazy('finance:expense_list'))},
            {'title': _("Rapport"), 'url': None},
        ]

    def get_queryset(self):
        return _expense_report_queryset(self.request)

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': f"{reverse_lazy('finance:expense_report_pdf')}?{self.request.GET.urlencode()}",
            'icon': 'file-pdf',
            'class': 'btn-falcon-danger',
        }]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = context['expenses']
        context['total_amount'] = qs.aggregate(total=Sum('amount'))['total'] or 0
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            context['sites'] = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            context['sites'] = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        context['selected_site'] = self.request.GET.get('site', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['period'] = self.request.GET.get('period', '')
        return context


@login_required
def expense_report_pdf(request):
    """PDF export of the same filtered expense report."""
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, role__in=EXPENSE_REPORT_ROLES
    ).exists()):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:expense_report')

    from core.pdf_utils import render_table_report_pdf

    qs = _expense_report_queryset(request)
    rows = [
        (
            e.expense_date.strftime('%d/%m/%Y'),
            e.site.name,
            e.category.name,
            e.get_nature_display(),
            (e.personnel.get_full_name() if e.personnel else '-'),
            e.description[:60],
            f"{e.amount:.2f} $",
            e.get_status_display(),
        )
        for e in qs
    ]
    total = qs.aggregate(total=Sum('amount'))['total'] or 0
    return render_table_report_pdf(
        filename=f"depenses-{timezone.localdate().isoformat()}.pdf",
        title="Rapport des dépenses",
        subtitle=_("%(count)s dépense(s)") % {'count': qs.count()},
        columns=["Date", "Chantier", "Catégorie", "Nature", "Personnel", "Désignation", "Montant", "Statut"],
        rows=rows,
        totals_row=["", "", "", "", "", "Total", f"{total:.2f} $", ""],
        generated_by=request.user.get_full_name() or request.user.username,
    )
