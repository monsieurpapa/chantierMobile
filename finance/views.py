from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from .models import (
    Expense, ExpenseApproval, Budget, Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseLoan,
    PayrollList, PayrollListItem, Avenant, SalaryPayment,
)
from .forms import (
    ExpenseForm, ExpensePayForm, BudgetForm, CaisseForm, CaisseTransactionForm, CaisseTransferForm,
    CaisseLoanForm, CaisseLoanRepayForm, PayrollListForm, PayrollListItemForm,
    PayrollDisburseForm, AvenantForm, AvenantDecisionForm, SalaryPaymentForm,
)
from projects.models import Site
from core.mixins import CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet
from chantiermobile.constants import (
    ExpenseStatus, UserRoles, CaisseTransactionType, FINAL_AUTHORIZATION_ROLES, PayrollListStatus,
)

# Roles that may view the expenses report / export it to PDF — mirrors
# core.dashboard.FINANCIAL_ROLES (the same audience that sees the
# dashboard's money widgets).
EXPENSE_REPORT_ROLES = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER']

# Roles that may manage caisses and record ledger movements.
CAISSE_MANAGE_ROLES = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER', 'FINANCIER']
# Salaires mensuels du bureau (ingénieurs/agents administratifs) — same
# audience as caisse management, since disbursing one is a caisse outflow.
SALARY_PAYMENT_ROLES = CAISSE_MANAGE_ROLES

# "L'archi" — whoever prepares/submits a payroll list from worker payment requests.
PAYROLL_PREPARE_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ENGINEER']
# Whoever disburses a submitted payroll list from a caisse.
PAYROLL_DISBURSE_ROLES = ['DIRECTOR', 'ACCOUNTANT', 'CASHIER', 'FINANCIER']
# Whoever may request an avenant (change order).
AVENANT_REQUEST_ROLES = ['DIRECTOR', 'CHIEF_ENGINEER', 'ACCOUNTANT']
# Anyone who may view payroll lists at all (preparers + disbursers) — payroll
# amounts are sensitive, so this isn't LoginRequiredMixin-only like some
# other list views.
PAYROLL_VIEW_ROLES = list(dict.fromkeys(PAYROLL_PREPARE_ROLES + PAYROLL_DISBURSE_ROLES))
AVENANT_VIEW_ROLES = list(dict.fromkeys(AVENANT_REQUEST_ROLES + FINAL_AUTHORIZATION_ROLES))

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.status == ExpenseStatus.APPROVED and can_act_for_cabinet(
            self.request, self.object.site.cabinet, [UserRoles.DIRECTOR, UserRoles.CASHIER]
        ):
            pay_form = ExpensePayForm()
            pay_form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=self.object.site.cabinet)
            context['pay_form'] = pay_form
        return context

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
                form = ExpensePayForm(request.POST)
                form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=expense.site.cabinet)
                if form.is_valid():
                    try:
                        expense.pay(request.user, form.cleaned_data['caisse'])
                        messages.success(request, _("Dépense marquée comme PAYÉE et enregistrée dans le livre de caisse."))
                    except ValidationError as e:
                        messages.error(request, _("Erreur lors du paiement de la dépense : %(error)s") % {'error': str(e)})
                else:
                    messages.error(request, _("Sélectionnez une caisse valide pour effectuer ce paiement."))
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


@login_required
def site_phases_data(request):
    """JSON endpoint used by the expense form's "Étape" picker: given a
    ?site=<id>, returns that site's phases, so they can be loaded as soon
    as a site is picked instead of requiring the form to be saved and
    reopened (the phase field's queryset is otherwise empty on a fresh GET
    — see ExpenseForm.__init__). Mirrors site_personnel_data above."""
    from django.http import JsonResponse
    from projects.models import ProjectPhase

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

    phases = ProjectPhase.objects.filter(site=site).order_by('start_date')
    return JsonResponse({
        'results': [{'id': p.id, 'text': p.name} for p in phases]
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

    phase_id = request.GET.get('phase')
    if phase_id:
        qs = qs.filter(phase_id=phase_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    period = request.GET.get('period')
    today = timezone.localdate()
    if period == 'day':
        qs = qs.filter(expense_date=today)
    elif period == 'week':
        qs = qs.filter(expense_date__gte=today - timezone.timedelta(days=7))
    elif period == 'month':
        qs = qs.filter(expense_date__gte=today.replace(day=1))
    elif period == 'year':
        qs = qs.filter(expense_date__gte=today.replace(month=1, day=1))

    return qs


def _expenses_by_site_rows(request):
    """Per-chantier expense totals for the report's "Dépenses par chantier"
    summary — the answer to "how much has each site spent so far" that used
    to mean calling the accountant. Deliberately ignores the report's own
    'site' filter (that filter narrows the detail table below; this summary
    stays a whole-cabinet overview so a director can see every chantier at
    once) but still respects the date/period filters, so the summary and
    the detail table underneath always describe the same time window.
    Only APPROVED/PAID amounts count, matching Site.total_spent."""
    qs = Expense.objects.filter(status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID])
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)

    period = request.GET.get('period')
    today = timezone.localdate()
    if period == 'day':
        qs = qs.filter(expense_date=today)
    elif period == 'week':
        qs = qs.filter(expense_date__gte=today - timezone.timedelta(days=7))
    elif period == 'month':
        qs = qs.filter(expense_date__gte=today.replace(day=1))
    elif period == 'year':
        qs = qs.filter(expense_date__gte=today.replace(month=1, day=1))

    totals = {
        row['site']: row['total']
        for row in qs.values('site').annotate(total=Sum('amount'))
    }
    if not totals:
        return []

    sites = Site.objects.filter(pk__in=totals.keys()).order_by('name')
    rows = [
        {'site': s, 'total': totals[s.pk]}
        for s in sites
    ]
    rows.sort(key=lambda r: r['total'], reverse=True)
    return rows


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
        context['expenses_by_site'] = _expenses_by_site_rows(self.request)
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            context['sites'] = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            context['sites'] = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        context['selected_site'] = self.request.GET.get('site', '')
        context['selected_phase'] = self.request.GET.get('phase', '')
        context['phases'] = []
        if context['selected_site']:
            from projects.models import ProjectPhase
            context['phases'] = ProjectPhase.objects.filter(site_id=context['selected_site']).order_by('start_date')
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
            e.recipient or '-',
            e.description[:60],
            f"{e.amount:.2f} $",
            e.get_status_display(),
            (str(e.approved_by) if e.approved_by else '-'),
        )
        for e in qs
    ]
    total = qs.aggregate(total=Sum('amount'))['total'] or 0
    by_site = _expenses_by_site_rows(request)
    subtitle_parts = [_("%(count)s dépense(s)") % {'count': qs.count()}]
    if by_site:
        summary = ", ".join(f"{row['site'].name}: {row['total']:.2f} $" for row in by_site)
        subtitle_parts.append(_("Par chantier — %(summary)s") % {'summary': summary})
    return render_table_report_pdf(
        filename=f"depenses-{timezone.localdate().isoformat()}.pdf",
        title="Rapport des dépenses",
        subtitle=" | ".join(str(p) for p in subtitle_parts),
        columns=["Date", "Chantier", "Catégorie", "Nature", "Personnel", "Bénéficiaire", "Désignation", "Montant", "Statut", "Approuvé par"],
        rows=rows,
        totals_row=["", "", "", "", "", "", "Total", f"{total:.2f} $", "", ""],
        generated_by=request.user.get_full_name() or request.user.username,
    )


# ---------------------------------------------------------------------
# Caisse (livre de caisse quotidien, prêts entre caisses, virements)
# ---------------------------------------------------------------------

class CaisseListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    model = Caisse
    template_name = 'finance/caisse_list.html'
    context_object_name = 'caisses'
    header_title = _("Caisses")
    header_subtitle = _("Gérez les caisses et leur solde")

    def get_queryset(self):
        return super().get_queryset().select_related('site')

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=CAISSE_MANAGE_ROLES
        ).exists():
            return [{
                'label': _("Nouvelle caisse"),
                'url': str(reverse_lazy('finance:caisse_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class CaisseCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = Caisse
    form_class = CaisseForm
    template_name = 'finance/caisse_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    success_url = reverse_lazy('finance:caisse_list')
    header_title = _("Nouvelle caisse")
    back_url = reverse_lazy('finance:caisse_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        cabinet = self.get_user_cabinet()
        form.fields['site'].queryset = Site.objects.filter(cabinet=cabinet) if cabinet else Site.objects.none()
        return form

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        messages.success(self.request, _("Caisse créée."))
        return super().form_valid(form)


class CaisseUpdateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, UpdateView):
    """Lets DIRECTOR/ACCOUNTANT edit a caisse's settings after creation —
    in particular, toggling manual_site_entry on for a caisse that serves
    external clients (e.g. the bétonnière) without needing shell access."""
    model = Caisse
    form_class = CaisseForm
    template_name = 'finance/caisse_form.html'
    allowed_roles = ['DIRECTOR', 'ACCOUNTANT']
    header_title = _("Modifier la caisse")

    def get_back_url(self):
        return str(reverse_lazy('finance:caisse_detail', kwargs={'pk': self.object.pk}))

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['site'].queryset = Site.objects.filter(cabinet=self.object.cabinet)
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Caisse mise à jour."))
        return super().form_valid(form)

    def get_success_url(self):
        return str(reverse_lazy('finance:caisse_detail', kwargs={'pk': self.object.pk}))


class CaisseDetailView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """The livre de caisse: chronological ledger with a running balance,
    optionally filtered to a date range (day/week/month/year)."""
    model = Caisse
    template_name = 'finance/caisse_detail.html'
    context_object_name = 'caisse'

    def get_header_title(self):
        return self.object.name

    def get_back_url(self):
        return str(reverse_lazy('finance:caisse_list'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        caisse = self.object
        qs = caisse.transactions.select_related('site', 'phase', 'expense', 'category').order_by('date', 'created_at')

        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        period = self.request.GET.get('period')
        selected_type = self.request.GET.get('type', '')
        selected_category = self.request.GET.get('category', '')
        today = timezone.localdate()
        if period == 'day':
            qs = qs.filter(date=today)
        elif period == 'week':
            qs = qs.filter(date__gte=today - timezone.timedelta(days=7))
        elif period == 'month':
            qs = qs.filter(date__gte=today.replace(day=1))
        elif period == 'year':
            qs = qs.filter(date__gte=today.replace(month=1, day=1))
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        # Running balance across ALL rows in the date range (regardless of
        # the type/category filters below), seeded with the balance carried
        # in from before the range, so "Solde" always reads like a real bank
        # statement. Type/category only narrow which rows are then *shown* —
        # they never change what the displayed balances mean.
        opening = caisse.transactions.filter(date__lt=(qs.first().date if qs.exists() else today)).aggregate(
            entrees=Sum('amount', filter=Q(transaction_type=CaisseTransactionType.ENTREE)),
            sorties=Sum('amount', filter=Q(transaction_type=CaisseTransactionType.SORTIE)),
        )
        running = (opening['entrees'] or 0) - (opening['sorties'] or 0)
        rows = []
        for tx in qs:
            running += tx.amount if tx.transaction_type == CaisseTransactionType.ENTREE else -tx.amount
            if selected_type and tx.transaction_type != selected_type:
                continue
            if selected_category and str(tx.category_id) != selected_category:
                continue
            rows.append({'tx': tx, 'running_balance': running})

        context['ledger_rows'] = rows
        context['opening_balance'] = (opening['entrees'] or 0) - (opening['sorties'] or 0)
        context['closing_balance'] = running
        context['period'] = period or ''
        context['date_from'] = date_from or ''
        context['date_to'] = date_to or ''
        context['selected_type'] = selected_type
        context['selected_category'] = selected_category
        context['categories'] = CaisseTransactionCategory.objects.all()
        context['can_manage'] = can_act_for_cabinet(self.request, caisse.cabinet, CAISSE_MANAGE_ROLES)
        context['other_caisses'] = Caisse.objects.filter(cabinet=caisse.cabinet).exclude(pk=caisse.pk)
        context['transfer_form'] = CaisseTransferForm()
        context['transfer_form'].fields['target_caisse'].queryset = context['other_caisses']
        return context


class CaisseTransactionCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = CaisseTransaction
    form_class = CaisseTransactionForm
    template_name = 'finance/caisse_transaction_form.html'
    allowed_roles = CAISSE_MANAGE_ROLES
    header_title = _("Enregistrer un mouvement de caisse")

    def dispatch(self, request, *args, **kwargs):
        self.caisse = get_object_or_404(Caisse, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.caisse.cabinet

    def get_back_url(self):
        return str(reverse_lazy('finance:caisse_detail', kwargs={'pk': self.caisse.pk}))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['caisse'] = self.caisse
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['caisse'] = self.caisse
        return context

    def form_valid(self, form):
        form.instance.caisse = self.caisse
        form.instance.recorded_by = self.request.user
        messages.success(self.request, _("Mouvement enregistré."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('finance:caisse_detail', kwargs={'pk': self.caisse.pk})


class CaisseTransactionDeleteView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, DeleteView):
    """Soft-deletes a single ledger entry. Caisse.balance is a live
    aggregate over non-deleted transactions, so nothing else needs to be
    reversed or recalculated."""
    model = CaisseTransaction
    allowed_roles = CAISSE_MANAGE_ROLES
    cabinet_lookup_field = 'caisse__cabinet'

    def get_success_url(self):
        return str(reverse_lazy('finance:caisse_detail', kwargs={'pk': self.object.caisse_id}))

    def post(self, request, *args, **kwargs):
        messages.success(request, _("Mouvement supprimé."))
        return self.delete(request, *args, **kwargs)


@login_required
def caisse_transfer(request, pk):
    """Daily remittance from a caisse to another (e.g. to the caisse de
    gestion administrative) — not a loan, no repayment tracked."""
    caisse = get_object_or_404(Caisse, pk=pk)
    if request.method != 'POST':
        return redirect('finance:caisse_detail', pk=pk)
    if not can_act_for_cabinet(request, caisse.cabinet, CAISSE_MANAGE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:caisse_detail', pk=pk)

    form = CaisseTransferForm(request.POST)
    form.fields['target_caisse'].queryset = Caisse.objects.filter(cabinet=caisse.cabinet).exclude(pk=caisse.pk)
    if form.is_valid():
        target = form.cleaned_data['target_caisse']
        amount = form.cleaned_data['amount']
        if amount > caisse.balance:
            messages.error(request, _("Solde insuffisant pour ce transfert."))
        else:
            caisse.transfer_to(target, amount, request.user, description=form.cleaned_data.get('description', ''))
            messages.success(request, _("Transfert de %(amount)s vers %(target)s effectué.") % {'amount': amount, 'target': target})
    else:
        messages.error(request, _("Transfert invalide : %(errors)s") % {'errors': form.errors.as_text()})
    return redirect('finance:caisse_detail', pk=pk)


class CaisseLoanListView(LoginRequiredMixin, PageHeaderMixin, ListView):
    model = CaisseLoan
    template_name = 'finance/caisse_loan_list.html'
    context_object_name = 'loans'
    header_title = _("Prêts entre caisses")
    back_url = reverse_lazy('finance:caisse_list')

    def get_queryset(self):
        qs = CaisseLoan.objects.select_related('lender_caisse', 'borrower_caisse').order_by('-date')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'cabinet_roles') else []
            qs = qs.filter(lender_caisse__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(lender_caisse__cabinet=active_cabinet)
        return qs


class CaisseLoanCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = CaisseLoan
    form_class = CaisseLoanForm
    template_name = 'finance/caisse_loan_form.html'
    allowed_roles = CAISSE_MANAGE_ROLES
    success_url = reverse_lazy('finance:caisse_loan_list')
    header_title = _("Nouveau prêt entre caisses")
    back_url = reverse_lazy('finance:caisse_loan_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            qs = Caisse.objects.filter(cabinet=active_cabinet) if active_cabinet else Caisse.objects.all()
        else:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            qs = Caisse.objects.filter(cabinet__in=cabinets)
        form.fields['lender_caisse'].queryset = qs
        form.fields['borrower_caisse'].queryset = qs
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.disburse(self.request.user)
        messages.success(self.request, _("Prêt de %(amount)s décaissé de %(lender)s vers %(borrower)s.") % {
            'amount': self.object.amount, 'lender': self.object.lender_caisse, 'borrower': self.object.borrower_caisse,
        })
        return response


@login_required
def caisse_loan_repay(request, pk):
    loan = get_object_or_404(CaisseLoan, pk=pk)
    if request.method != 'POST':
        return redirect('finance:caisse_loan_list')
    if not can_act_for_cabinet(request, loan.lender_caisse.cabinet, CAISSE_MANAGE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:caisse_loan_list')

    form = CaisseLoanRepayForm(request.POST)
    if form.is_valid():
        try:
            loan.repay(form.cleaned_data['amount'], request.user)
            messages.success(request, _("Remboursement enregistré."))
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Montant invalide."))
    return redirect('finance:caisse_loan_list')


def _caisse_ledger_queryset(request):
    """Shared filtering for the combined caisse (livre de caisse) report
    and its PDF export — cabinet-scoped, filterable by caisse/site/phase and
    by date range or period (jour/semaine/mois/an)."""
    qs = CaisseTransaction.objects.select_related('caisse', 'site', 'phase', 'category').order_by('-date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(caisse__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.cabinet_roles.values_list('cabinet_id', flat=True)
        qs = qs.filter(caisse__cabinet__id__in=user_cabinet_ids)

    caisse_id = request.GET.get('caisse')
    if caisse_id:
        qs = qs.filter(caisse_id=caisse_id)
    site_id = request.GET.get('site')
    if site_id:
        qs = qs.filter(site_id=site_id)
    phase_id = request.GET.get('phase')
    if phase_id:
        qs = qs.filter(phase_id=phase_id)
    transaction_type = request.GET.get('type')
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)
    category_id = request.GET.get('category')
    if category_id:
        qs = qs.filter(category_id=category_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    period = request.GET.get('period')
    today = timezone.localdate()
    if period == 'day':
        qs = qs.filter(date=today)
    elif period == 'week':
        qs = qs.filter(date__gte=today - timezone.timedelta(days=7))
    elif period == 'month':
        qs = qs.filter(date__gte=today.replace(day=1))
    elif period == 'year':
        qs = qs.filter(date__gte=today.replace(month=1, day=1))

    return qs


class CaisseReportView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Combined entrées/sorties report across caisses — filterable by
    caisse, chantier, étape, and by day/week/month/year/date-range, with
    a PDF export (livre de caisse)."""
    model = CaisseTransaction
    template_name = 'finance/caisse_report.html'
    context_object_name = 'transactions'
    allowed_roles = CAISSE_MANAGE_ROLES
    header_title = _("Rapport de caisse (livre de caisse)")
    back_url = reverse_lazy('finance:caisse_list')

    def get_queryset(self):
        return _caisse_ledger_queryset(self.request)

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': f"{reverse_lazy('finance:caisse_report_pdf')}?{self.request.GET.urlencode()}",
            'icon': 'file-pdf',
            'class': 'btn-falcon-danger',
        }]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = context['transactions']
        context['total_entrees'] = qs.filter(transaction_type=CaisseTransactionType.ENTREE).aggregate(t=Sum('amount'))['t'] or 0
        context['total_sorties'] = qs.filter(transaction_type=CaisseTransactionType.SORTIE).aggregate(t=Sum('amount'))['t'] or 0
        if self.request.user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            context['caisses'] = Caisse.objects.filter(cabinet=active_cabinet) if active_cabinet else Caisse.objects.all()
            context['sites'] = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            context['caisses'] = Caisse.objects.filter(cabinet__id__in=user_cabinet_ids)
            context['sites'] = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        context['selected_caisse'] = self.request.GET.get('caisse', '')
        context['selected_site'] = self.request.GET.get('site', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['period'] = self.request.GET.get('period', '')
        context['selected_type'] = self.request.GET.get('type', '')
        context['selected_category'] = self.request.GET.get('category', '')
        context['categories'] = CaisseTransactionCategory.objects.all()
        return context


@login_required
def caisse_report_pdf(request):
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, role__in=CAISSE_MANAGE_ROLES
    ).exists()):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:caisse_report')

    from core.pdf_utils import render_table_report_pdf

    qs = _caisse_ledger_queryset(request)
    rows = [
        (
            tx.date.strftime('%d/%m/%Y'),
            tx.caisse.name,
            tx.get_transaction_type_display(),
            tx.site.name if tx.site else '-',
            tx.phase.name if tx.phase else '-',
            tx.description[:50],
            f"{tx.amount:.2f} $",
        )
        for tx in qs
    ]
    total_entrees = qs.filter(transaction_type=CaisseTransactionType.ENTREE).aggregate(t=Sum('amount'))['t'] or 0
    total_sorties = qs.filter(transaction_type=CaisseTransactionType.SORTIE).aggregate(t=Sum('amount'))['t'] or 0
    return render_table_report_pdf(
        filename=f"livre-de-caisse-{timezone.localdate().isoformat()}.pdf",
        title="Livre de caisse",
        subtitle=_("%(count)s mouvement(s) — Entrées: %(in)s $ · Sorties: %(out)s $") % {
            'count': qs.count(), 'in': f"{total_entrees:.2f}", 'out': f"{total_sorties:.2f}",
        },
        columns=["Date", "Caisse", "Type", "Chantier", "Étape", "Description", "Montant"],
        rows=rows,
        totals_row=["", "", "", "", "", "Solde net", f"{(total_entrees - total_sorties):.2f} $"],
        generated_by=request.user.get_full_name() or request.user.username,
    )


# ---------------------------------------------------------------------
# Liste de paie (paiement progressif des ouvriers)
# ---------------------------------------------------------------------

class PayrollListListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = PayrollList
    template_name = 'finance/payroll_list_list.html'
    context_object_name = 'payroll_lists'
    allowed_roles = PAYROLL_VIEW_ROLES
    header_title = _("Listes de paie")
    header_subtitle = _("Paiement progressif des ouvriers, par avancement")

    def get_queryset(self):
        qs = PayrollList.objects.select_related('site', 'prepared_by').order_by('-created_at')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'cabinet_roles') else []
            qs = qs.filter(site__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(site__cabinet=active_cabinet)
        return qs

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=PAYROLL_PREPARE_ROLES
        ).exists():
            return [{
                'label': _("Nouvelle liste de paie"),
                'url': str(reverse_lazy('finance:payroll_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class PayrollListCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = PayrollList
    form_class = PayrollListForm
    template_name = 'finance/payroll_list_form.html'
    allowed_roles = PAYROLL_PREPARE_ROLES
    header_title = _("Nouvelle liste de paie")
    back_url = reverse_lazy('finance:payroll_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__in=cabinets)
        return form

    def form_valid(self, form):
        form.instance.prepared_by = self.request.user
        messages.success(self.request, _("Liste de paie créée. Ajoutez maintenant les ouvriers à payer."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('finance:payroll_detail', kwargs={'pk': self.object.pk})


class PayrollListDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    model = PayrollList
    template_name = 'finance/payroll_list_detail.html'
    context_object_name = 'payroll_list'
    allowed_roles = PAYROLL_VIEW_ROLES
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return str(self.object)

    def get_back_url(self):
        return str(reverse_lazy('finance:payroll_list'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_prepare'] = can_act_for_cabinet(self.request, self.object.site.cabinet, PAYROLL_PREPARE_ROLES)
        context['can_disburse'] = can_act_for_cabinet(self.request, self.object.site.cabinet, PAYROLL_DISBURSE_ROLES)
        if context['can_prepare'] and self.object.status == PayrollListStatus.BROUILLON:
            item_form = PayrollListItemForm(site=self.object.site)
            context['item_form'] = item_form
        if context['can_disburse'] and self.object.status == PayrollListStatus.SOUMISE:
            disburse_form = PayrollDisburseForm()
            disburse_form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=self.object.site.cabinet)
            context['disburse_form'] = disburse_form
        return context


class PayrollListItemCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = PayrollListItem
    form_class = PayrollListItemForm
    allowed_roles = PAYROLL_PREPARE_ROLES

    def dispatch(self, request, *args, **kwargs):
        self.payroll_list = get_object_or_404(PayrollList, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.payroll_list.site.cabinet

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['site'] = self.payroll_list.site
        return kwargs

    def form_valid(self, form):
        if self.payroll_list.status != PayrollListStatus.BROUILLON:
            messages.error(self.request, _("Cette liste n'est plus modifiable."))
            return redirect('finance:payroll_detail', pk=self.payroll_list.pk)
        form.instance.payroll_list = self.payroll_list
        messages.success(self.request, _("Ouvrier ajouté à la liste."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Impossible d'ajouter : %(errors)s") % {'errors': form.errors.as_text()})
        return redirect('finance:payroll_detail', pk=self.payroll_list.pk)

    def get_success_url(self):
        return reverse_lazy('finance:payroll_detail', kwargs={'pk': self.payroll_list.pk})


@login_required
def payroll_submit(request, pk):
    payroll_list = get_object_or_404(PayrollList, pk=pk)
    if request.method != 'POST':
        return redirect('finance:payroll_detail', pk=pk)
    if not can_act_for_cabinet(request, payroll_list.site.cabinet, PAYROLL_PREPARE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:payroll_detail', pk=pk)
    try:
        payroll_list.submit(request.user)
        messages.success(request, _("Liste soumise à la caisse."))
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('finance:payroll_detail', pk=pk)


@login_required
def payroll_disburse(request, pk):
    payroll_list = get_object_or_404(PayrollList, pk=pk)
    if request.method != 'POST':
        return redirect('finance:payroll_detail', pk=pk)
    if not can_act_for_cabinet(request, payroll_list.site.cabinet, PAYROLL_DISBURSE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:payroll_detail', pk=pk)
    form = PayrollDisburseForm(request.POST)
    form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=payroll_list.site.cabinet)
    if form.is_valid():
        try:
            payroll_list.disburse(request.user, form.cleaned_data['caisse'])
            messages.success(request, _("Liste de paie décaissée."))
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Sélectionnez une caisse valide."))
    return redirect('finance:payroll_detail', pk=pk)


# ---------------------------------------------------------------------
# Salaires mensuels du bureau (ingénieurs / agents administratifs)
# ---------------------------------------------------------------------

class SalaryPaymentListView(LoginRequiredMixin, CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = SalaryPayment
    context_object_name = 'salary_payments'
    template_name = 'finance/salary_payment_list.html'
    allowed_roles = SALARY_PAYMENT_ROLES
    cabinet_lookup_field = 'personnel__cabinet'
    header_title = _("Salaires du bureau")
    header_subtitle = _("Paiements des salaires mensuels — ingénieurs et agents administratifs")

    def get_queryset(self):
        return super().get_queryset().select_related('personnel', 'caisse', 'paid_by').order_by('-period', 'personnel__last_name')

    def get_header_actions(self):
        return [{
            'label': _("Payer un salaire"),
            'url': str(reverse_lazy('finance:salary_payment_create')),
            'icon': 'plus',
            'class': 'btn-falcon-primary',
        }]


class SalaryPaymentCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    model = SalaryPayment
    form_class = SalaryPaymentForm
    template_name = 'finance/salary_payment_form.html'
    allowed_roles = SALARY_PAYMENT_ROLES
    success_url = reverse_lazy('finance:salary_payment_list')
    header_title = _("Payer un salaire mensuel")
    header_subtitle = _("Enregistrer et décaisser le salaire d'un agent de bureau ou d'un ingénieur")
    back_url = reverse_lazy('finance:salary_payment_list')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Salaires du bureau"), 'url': str(reverse_lazy('finance:salary_payment_list'))},
            {'title': _("Nouveau paiement"), 'url': None},
        ]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['cabinet'] = self.get_user_cabinet()
        return kwargs

    def form_valid(self, form):
        cabinet = self.get_user_cabinet()
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = form.save()
                self.object.disburse(self.request.user)
        except ValidationError as e:
            self.object = None
            form.add_error(None, str(e.message) if hasattr(e, 'message') else str(e))
            return self.form_invalid(form)
        messages.success(self.request, _("Salaire de %(personnel)s payé pour %(period)s.") % {
            'personnel': self.object.personnel, 'period': self.object.period,
        })
        return HttpResponseRedirect(self.get_success_url())


# ---------------------------------------------------------------------
# Avenants (dépassement de budget autorisé -> dette client)
# ---------------------------------------------------------------------

class AvenantListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    model = Avenant
    template_name = 'finance/avenant_list.html'
    context_object_name = 'avenants'
    allowed_roles = AVENANT_VIEW_ROLES
    header_title = _("Avenants")
    header_subtitle = _("Dépenses autorisées au-delà du budget initial")

    def get_queryset(self):
        qs = Avenant.objects.select_related('site', 'requested_by').order_by('-created_at')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'cabinet_roles') else []
            qs = qs.filter(site__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(site__cabinet=active_cabinet)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_decide'] = (
            self.request.user.is_superuser or
            self.request.user.cabinet_roles.filter(role__in=FINAL_AUTHORIZATION_ROLES).exists()
        )
        return context

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, role__in=AVENANT_REQUEST_ROLES
        ).exists():
            return [{
                'label': _("Nouvel avenant"),
                'url': str(reverse_lazy('finance:avenant_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class AvenantCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    model = Avenant
    form_class = AvenantForm
    template_name = 'finance/avenant_form.html'
    allowed_roles = AVENANT_REQUEST_ROLES
    success_url = reverse_lazy('finance:avenant_list')
    header_title = _("Nouvel avenant")
    back_url = reverse_lazy('finance:avenant_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if user.is_superuser:
            active_cabinet = get_session_cabinet(self.request)
            form.fields['site'].queryset = Site.objects.filter(cabinet=active_cabinet) if active_cabinet else Site.objects.all()
        else:
            cabinets = user.cabinet_roles.values_list('cabinet', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__in=cabinets)
        return form

    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        messages.success(self.request, _("Avenant soumis pour autorisation."))
        return super().form_valid(form)


def _avenant_decide(request, pk, approve):
    avenant = get_object_or_404(Avenant, pk=pk)
    if request.method != 'POST':
        return redirect('finance:avenant_list')
    if not can_act_for_cabinet(request, avenant.site.cabinet, FINAL_AUTHORIZATION_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:avenant_list')
    form = AvenantDecisionForm(request.POST)
    notes = form.data.get('notes', '') if form.is_valid() else ''
    try:
        if approve:
            avenant.approve(request.user, notes=notes)
            messages.success(request, _("Avenant autorisé — budget et dette client mis à jour."))
        else:
            avenant.reject(request.user, notes=notes)
            messages.success(request, _("Avenant rejeté."))
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('finance:avenant_list')


def avenant_approve(request, pk):
    return _avenant_decide(request, pk, approve=True)


def avenant_reject(request, pk):
    return _avenant_decide(request, pk, approve=False)
