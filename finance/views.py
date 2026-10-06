"""Views for the finance app: expense submission/approval/payment, budgets,
the Caisse ledger (manual movements, transfers, inter-caisse loans), the
two payroll tracks (PayrollList for ouvriers, SalaryPaymentList for
ingénieurs/staff), and Avenant change-order decisions.

Every state-changing endpoint here is gated either by a class-based view's
`allowed_roles` (RoleRequiredMixin) or by an explicit
`can_act_for_cabinet(request, cabinet, allowed_roles)` call in a
function-based view — see docs/security.md. The role-list constants at the
top of this module (EXPENSE_REPORT_ROLES, CAISSE_MANAGE_ROLES,
PAYROLL_PREPARE_ROLES, etc.) are the single source of truth each view
below references; core/approvals.py keeps its own duplicated copies for the
pending-approvals inbox and must be updated by hand if these change.

FIXED 2026-10-06: every ad-hoc `UserCabinetRole.objects.filter(user=...)`
check below now also filters on `status=ApprovalStatus.APPROVED`, and every
bare reverse-accessor `cabinet_roles` access used for an access-control
decision (as opposed to a purely informational listing) now goes through
`User.approved_cabinet_roles` instead — a PENDING role grant (awaiting a
superadmin's approval) must not already grant access. See core/mixins.py
and docs/security.md.
"""
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, TemplateView
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
from decimal import Decimal, InvalidOperation
from .models import (
    Expense, ExpenseApproval, Budget, Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseLoan,
    PayrollList, PayrollListItem, SalaryPaymentList, SalaryPaymentItem, Avenant,
)
from .forms import (
    ExpenseForm, ExpensePayForm, BudgetForm, CaisseForm, CaisseTransactionForm, CaisseTransferForm,
    CaisseLoanForm, CaisseLoanRepayForm, PayrollListForm, PayrollListItemForm,
    PayrollDisburseForm, SalaryPaymentListForm, SalaryPaymentItemForm, AvenantForm, AvenantDecisionForm,
)
from projects.models import Site
from personnel.models import SiteAssignment
from core.mixins import (
    CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, get_session_cabinet, can_act_for_cabinet,
    add_ambiguous_cabinet_field,
)
from chantiermobile.constants import (
    ApprovalStatus, ExpenseStatus, UserRoles, CaisseTransactionType, FINAL_AUTHORIZATION_ROLES, PayrollListStatus,
    PersonnelPayrollType,
)

# Roles that may view the expenses report / export it to PDF — mirrors
# core.dashboard.FINANCIAL_ROLES (the same audience that sees the
# dashboard's money widgets).
EXPENSE_REPORT_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT', 'CASHIER']

# Roles that may manage caisses and record ledger movements.
CAISSE_MANAGE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT', 'CASHIER', 'FINANCIER']

# "L'archi" — whoever prepares/submits a payroll list from worker payment requests.
PAYROLL_PREPARE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']
# Whoever disburses a submitted payroll list from a caisse.
PAYROLL_DISBURSE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT', 'CASHIER', 'FINANCIER']
# Whoever may request an avenant (change order).
AVENANT_REQUEST_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ACCOUNTANT']
# Anyone who may view payroll lists at all (preparers + disbursers) — payroll
# amounts are sensitive, so this isn't LoginRequiredMixin-only like some
# other list views.
PAYROLL_VIEW_ROLES = list(dict.fromkeys(PAYROLL_PREPARE_ROLES + PAYROLL_DISBURSE_ROLES))
AVENANT_VIEW_ROLES = list(dict.fromkeys(AVENANT_REQUEST_ROLES + FINAL_AUTHORIZATION_ROLES))

class ExpenseListView(LoginRequiredMixin, CabinetAccessMixin, PageHeaderMixin, ListView):
    """Lists expenses for the caller's cabinet(s); open to any authenticated
    user (no allowed_roles) since any role may need to check an expense's
    status, but the "Rapport" PDF-export action is only offered to
    EXPENSE_REPORT_ROLES."""
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
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=EXPENSE_REPORT_ROLES
        ).exists():
            actions.append({
                'label': _("Rapport"),
                'url': str(reverse_lazy('finance:expense_report')),
                'icon': 'file-alt',
                'class': 'btn-falcon-default'
            })
        return actions

class ExpenseCreateView(LoginRequiredMixin, PageHeaderMixin, CreateView):
    """Submits a new expense request (any authenticated user, scoped to
    their own cabinet's sites); always created PENDING, with the requester
    stamped from the logged-in user, then notifies EXPENSE_APPROVAL_ROLES."""
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        form.instance.requester = self.request.user
        from django.contrib import messages
        response = super().form_valid(form)
        from core.approvals import EXPENSE_APPROVAL_ROLES
        from core.notifications import notify_role_holders
        notify_role_holders(
            self.object.site.cabinet, EXPENSE_APPROVAL_ROLES,
            _("Nouvelle dépense à approuver : %(desc)s (%(amount)s $)") % {
                'desc': self.object.description[:60], 'amount': self.object.amount,
            },
            str(reverse_lazy('finance:expense_detail', kwargs={'pk': self.object.pk})),
            exclude_user=self.request.user,
        )
        messages.success(self.request, _("Demande de dépense soumise avec succès !"))
        return response

class ExpenseDetailView(LoginRequiredMixin, PageHeaderMixin, DetailView):
    """Shows one expense; the "mark as paid" form only appears when the
    expense is APPROVED and the viewer passes can_act_for_cabinet() for
    DIRECTOR/DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/CASHIER."""
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.status == ExpenseStatus.APPROVED and can_act_for_cabinet(
            self.request, self.object.site.cabinet, [UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CASHIER]
        ):
            pay_form = ExpensePayForm()
            pay_form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=self.object.site.cabinet)
            context['pay_form'] = pay_form
        return context

@login_required
def approve_expense(request, pk):
    """PENDING -> APPROVED. Role-gated inline (DIRECTOR/DIRECTEUR_TECHNIQUE/
    DIRECTEUR_GENERAL/ACCOUNTANT in the expense's own cabinet, or a
    superuser), and additionally restricted to the session's active cabinet
    when a superuser has one selected. Self-approval is blocked in
    Expense.approve() itself.

    FIXED 2026-10-06: the inline role check now uses approved_cabinet_roles
    (same fix as approve_expense/reject_expense/mark_expense_paid below)."""
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.approved_cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.ACCOUNTANT]).exists():
            try:
                expense.approve(request.user, comments=request.POST.get('comments', ''))
                from core.notifications import notify_user
                notify_user(
                    expense.requester,
                    _("Votre dépense a été approuvée : %(desc)s") % {'desc': expense.description[:60]},
                    str(reverse_lazy('finance:expense_detail', kwargs={'pk': expense.pk})),
                )
                messages.success(request, _("Dépense approuvée."))
            except ValidationError as e:
                messages.error(request, _("Impossible d'approuver la dépense : %(error)s") % {'error': e})
        else:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

@login_required
def reject_expense(request, pk):
    """PENDING -> REJECTED. Same role gate as approve_expense (DIRECTOR/
    DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/ACCOUNTANT or superuser)."""
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.approved_cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.ACCOUNTANT]).exists():
            if expense.status != ExpenseStatus.PENDING:
                messages.error(request, _("Seule une dépense en attente peut être rejetée."))
            else:
                try:
                    expense.reject(request.user, comments=request.POST.get('comments', ''))
                    from core.notifications import notify_user
                    notify_user(
                        expense.requester,
                        _("Votre dépense a été rejetée : %(desc)s") % {'desc': expense.description[:60]},
                        str(reverse_lazy('finance:expense_detail', kwargs={'pk': expense.pk})),
                    )
                    messages.success(request, _("Dépense rejetée."))
                except ValidationError as e:
                    messages.error(request, _("Impossible de rejeter la dépense : %(error)s") % {'error': e})
        else:
            messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:expense_detail', pk=pk)
    return redirect('finance:expense_list')

@login_required
def mark_expense_paid(request, pk):
    """APPROVED -> PAID: records the matching Caisse outflow via
    Expense.pay(). Role-gated to DIRECTOR/DIRECTEUR_TECHNIQUE/
    DIRECTEUR_GENERAL/CASHIER in the expense's cabinet (or superuser)."""
    if request.method == 'POST':
        expense = get_object_or_404(Expense, pk=pk)
        active_cabinet = get_session_cabinet(request)
        if active_cabinet and expense.site.cabinet != active_cabinet:
            messages.error(request, _("Cette dépense appartient à un autre cabinet que votre session active."))
            return redirect('finance:expense_list')
        if request.user.is_superuser or request.user.approved_cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.CASHIER]).exists():
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

# Full, cabinet-wide budget access (every budget in the cabinet). ENGINEER
# is deliberately NOT in this list: a site engineer can see budgets, but
# only for the site(s) they actually lead (see BUDGET_VIEW_ROLES and the
# get_queryset() overrides below) — otherwise any engineer in the cabinet
# could browse every other site's financials.
BUDGET_FULL_ACCESS_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT', 'CHIEF_ENGINEER']
# Who may reach the budget list/detail views at all — full-access roles
# above, plus ENGINEER (queryset-scoped to their own led site(s)).
BUDGET_VIEW_ROLES = BUDGET_FULL_ACCESS_ROLES + ['ENGINEER']


def _scope_budgets_for_viewer(qs, user):
    """Cabinet-wide for a full-access role; otherwise (a plain ENGINEER)
    restricted to budgets of sites where the user is the lead_engineer —
    engineers previously had no way at all to see their own site's
    budget, since BudgetListView/BudgetDetailView excluded ENGINEER
    entirely.

    FIXED 2026-10-06: uses approved_cabinet_roles so a PENDING role grant
    doesn't already count as cabinet-wide budget access."""
    if user.is_superuser:
        return qs
    admin_cabinet_ids = user.approved_cabinet_roles.filter(role__in=BUDGET_FULL_ACCESS_ROLES).values_list('cabinet_id', flat=True)
    return qs.filter(Q(site__cabinet_id__in=admin_cabinet_ids) | Q(site__lead_engineer=user))


class BudgetListView(LoginRequiredMixin, CabinetAccessMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Lists budgets. allowed_roles = BUDGET_VIEW_ROLES (full-access
    director tier + ACCOUNTANT + CHIEF_ENGINEER, plus ENGINEER); the
    queryset is further narrowed for a plain ENGINEER to only the sites
    they lead (see _scope_budgets_for_viewer)."""
    model = Budget
    template_name = 'finance/budget_list.html'
    context_object_name = 'budgets'
    allowed_roles = BUDGET_VIEW_ROLES
    cabinet_lookup_field = 'site__cabinet'
    header_title = _("Budgets des projets")
    header_subtitle = _("Surveillez et gérez les budgets de construction")

    def get_queryset(self):
        return _scope_budgets_for_viewer(super().get_queryset(), self.request.user)

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=[UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.ACCOUNTANT]
        ).exists():
            return [{
                'label': _("Créer un budget"),
                'url': str(reverse_lazy('finance:budget_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary'
            }]
        return []

class BudgetCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Creates a Budget for a site. allowed_roles: DIRECTOR,
    DIRECTEUR_TECHNIQUE, DIRECTEUR_GENERAL, ACCOUNTANT — deliberately not
    CHIEF_ENGINEER or ENGINEER, who may only view budgets."""
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__id__in=user_cabinet_ids)
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Budget créé pour %(site)s avec succès !") % {'site': form.instance.site.name})
        return super().form_valid(form)

class BudgetDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """Budget detail with spend breakdown/forecast. allowed_roles =
    BUDGET_VIEW_ROLES, queryset narrowed for ENGINEER the same way as
    BudgetListView (see _scope_budgets_for_viewer)."""
    model = Budget
    template_name = 'finance/budget_detail.html'
    context_object_name = 'budget'
    allowed_roles = BUDGET_VIEW_ROLES
    cabinet_lookup_field = 'site__cabinet'

    def get_queryset(self):
        return _scope_budgets_for_viewer(super().get_queryset(), self.request.user)

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
    """Edits a Budget. Same allowed_roles as BudgetCreateView (DIRECTOR/
    DIRECTEUR_TECHNIQUE/DIRECTEUR_GENERAL/ACCOUNTANT) — ENGINEER can view
    but not edit."""
    model = Budget
    form_class = BudgetForm
    template_name = 'finance/budget_form.html'
    success_url = reverse_lazy('finance:budget_list')
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
    cabinet-scoped, optionally filtered by site and by expense_date range.

    FIXED 2026-10-06: cabinet scoping now uses approved_cabinet_roles."""
    qs = Expense.objects.select_related('site', 'category', 'requester', 'personnel').order_by('-expense_date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(site__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
    """PDF export of the same filtered expense report. Role-gated to
    EXPENSE_REPORT_ROLES (or superuser) via a direct UserCabinetRole check
    rather than RoleRequiredMixin, since this is a plain function view."""
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, status=ApprovalStatus.APPROVED, role__in=EXPENSE_REPORT_ROLES
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
    """Lists caisses for the caller's cabinet(s); open to any authenticated
    user. The "Nouvelle caisse" action is only offered to
    CAISSE_MANAGE_ROLES."""
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
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=CAISSE_MANAGE_ROLES
        ).exists():
            return [{
                'label': _("Nouvelle caisse"),
                'url': str(reverse_lazy('finance:caisse_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class CaisseCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Creates a Caisse for the current user's cabinet. allowed_roles:
    DIRECTOR, DIRECTEUR_TECHNIQUE, DIRECTEUR_GENERAL, ACCOUNTANT."""
    model = Caisse
    form_class = CaisseForm
    template_name = 'finance/caisse_form.html'
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
    allowed_roles = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
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
    """Manual ledger entry (entrée/sortie) on one caisse, scoped via
    get_role_cabinet() to that caisse's own cabinet. allowed_roles =
    CAISSE_MANAGE_ROLES."""
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
    gestion administrative) — not a loan, no repayment tracked. Role-gated
    to CAISSE_MANAGE_ROLES in the source caisse's cabinet."""
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
    """Lists inter-caisse loans for the caller's cabinet(s); open to any
    authenticated user (no allowed_roles) — creating/repaying a loan is
    separately gated to CAISSE_MANAGE_ROLES.

    FIXED 2026-10-06: cabinet scoping now uses approved_cabinet_roles."""
    model = CaisseLoan
    template_name = 'finance/caisse_loan_list.html'
    context_object_name = 'loans'
    header_title = _("Prêts entre caisses")
    back_url = reverse_lazy('finance:caisse_list')

    def get_queryset(self):
        qs = CaisseLoan.objects.select_related('lender_caisse', 'borrower_caisse').order_by('-date')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
            qs = qs.filter(lender_caisse__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(lender_caisse__cabinet=active_cabinet)
        return qs


class CaisseLoanCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Creates a CaisseLoan and immediately disburses it (see form_valid).
    allowed_roles = CAISSE_MANAGE_ROLES."""
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
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
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
    """Records a (possibly partial) repayment on a CaisseLoan. Role-gated
    to CAISSE_MANAGE_ROLES in the lender caisse's cabinet."""
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
    by date range or period (jour/semaine/mois/an).

    FIXED 2026-10-06: cabinet scoping now uses approved_cabinet_roles."""
    qs = CaisseTransaction.objects.select_related('caisse', 'site', 'phase', 'category').order_by('-date', '-id')
    if request.user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            qs = qs.filter(caisse__cabinet=active_cabinet)
    else:
        user_cabinet_ids = request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
            user_cabinet_ids = self.request.user.approved_cabinet_roles.values_list('cabinet_id', flat=True)
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
    """PDF export of the same filtered livre de caisse. Role-gated to
    CAISSE_MANAGE_ROLES (or superuser), checked directly rather than via
    RoleRequiredMixin since this is a plain function view."""
    from accounts.models import UserCabinetRole
    if not (request.user.is_superuser or UserCabinetRole.objects.filter(
        user=request.user, status=ApprovalStatus.APPROVED, role__in=CAISSE_MANAGE_ROLES
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
    """Lists "Main d'œuvre" payroll lists for the caller's cabinet(s).
    allowed_roles = PAYROLL_VIEW_ROLES (union of preparers and
    disbursers) — payroll amounts are sensitive, so this is role-gated
    unlike most other list views in this module.

    FIXED 2026-10-06: cabinet scoping (and the "Nouvelle liste" action
    check) now uses approved_cabinet_roles."""
    model = PayrollList
    template_name = 'finance/payroll_list_list.html'
    context_object_name = 'payroll_lists'
    allowed_roles = PAYROLL_VIEW_ROLES
    header_title = _("Listes de paie")
    header_subtitle = _("Main d'œuvre — paiement progressif des ouvriers par chantier, par avancement")

    def get_queryset(self):
        qs = PayrollList.objects.select_related('site', 'prepared_by').order_by('-created_at')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
            qs = qs.filter(site__cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(site__cabinet=active_cabinet)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'main_doeuvre'
        return context

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=PAYROLL_PREPARE_ROLES
        ).exists():
            return [{
                'label': _("Nouvelle liste de paie"),
                'url': str(reverse_lazy('finance:payroll_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class PayrollListCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Starts a new BROUILLON PayrollList for a site. allowed_roles =
    PAYROLL_PREPARE_ROLES ("l'archi" who analyzes progress and requests)."""
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
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__in=cabinets)
        return form

    def form_valid(self, form):
        form.instance.prepared_by = self.request.user
        messages.success(self.request, _("Liste de paie créée. Ajoutez maintenant les ouvriers à payer."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('finance:payroll_detail', kwargs={'pk': self.object.pk})


class PayrollListDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """PayrollList detail; allowed_roles = PAYROLL_VIEW_ROLES, with the
    item-add form shown only if can_act_for_cabinet() passes
    PAYROLL_PREPARE_ROLES (and status is BROUILLON) and the disburse form
    shown only if it passes PAYROLL_DISBURSE_ROLES (and status is
    SOUMISE)."""
    model = PayrollList
    template_name = 'finance/payroll_list_detail.html'
    context_object_name = 'payroll_list'
    allowed_roles = PAYROLL_VIEW_ROLES
    cabinet_lookup_field = 'site__cabinet'

    def get_header_title(self):
        return str(self.object)

    def get_back_url(self):
        return str(reverse_lazy('finance:payroll_list'))

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': str(reverse_lazy('finance:payroll_detail_pdf', kwargs={'pk': self.object.pk})),
            'icon': 'file-pdf',
            'class': 'btn-falcon-default',
        }]

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
    """Adds one ouvrier/amount row to a PayrollList, one at a time (the
    older single-item flow — see PayrollListAllocateView for the bulk
    screen). allowed_roles = PAYROLL_PREPARE_ROLES, scoped via
    get_role_cabinet() to the payroll list's own site/cabinet; also refuses
    to add once the list is no longer BROUILLON."""
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


class PayrollListAllocateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, TemplateView):
    """Bulk allocation screen: one row per SiteAssignment (convention) on
    the payroll list's chantier, each with a Montant input the Chef de
    chantier fills in, capped by the convention's remaining balance for
    Ouvriers. Replaces adding items one at a time via
    PayrollListItemCreateView for the common case (that older single-item
    flow is kept working for edge cases / manual entry)."""
    template_name = 'finance/payroll_list_allocate.html'
    allowed_roles = PAYROLL_PREPARE_ROLES

    def dispatch(self, request, *args, **kwargs):
        self.payroll_list = get_object_or_404(PayrollList, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.payroll_list.site.cabinet

    def get_header_title(self):
        return _("Allocation — %(list)s") % {'list': self.payroll_list}

    def get_back_url(self):
        return str(reverse_lazy('finance:payroll_detail', kwargs={'pk': self.payroll_list.pk}))

    def get_rows(self):
        # Main d'œuvre only — Ingénieurs & Staff are paid via SalaryPaymentList
        # (onglet "Ingénieurs & Staff"), not through a chantier's Liste de
        # paie. See PayrollListItem.clean() for the matching model-level guard.
        assignments = SiteAssignment.objects.filter(
            site=self.payroll_list.site,
            personnel__payroll_type=PersonnelPayrollType.OUVRIER,
        ).select_related('personnel').order_by('personnel__last_name', 'personnel__first_name')
        rows = []
        for assignment in assignments:
            personnel = assignment.personnel
            if not personnel.is_eligible:
                continue
            is_capped = assignment.convention_amount is not None
            rows.append({
                'assignment': assignment,
                'personnel': personnel,
                'is_capped': is_capped,
                'remaining': assignment.remaining_convention,
            })
        return rows

    def get(self, request, *args, **kwargs):
        if self.payroll_list.status != PayrollListStatus.BROUILLON:
            messages.error(request, _("Cette liste n'est plus modifiable."))
            return redirect('finance:payroll_detail', pk=self.payroll_list.pk)
        context = self.get_context_data(payroll_list=self.payroll_list, rows=self.get_rows())
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        if self.payroll_list.status != PayrollListStatus.BROUILLON:
            messages.error(request, _("Cette liste n'est plus modifiable."))
            return redirect('finance:payroll_detail', pk=self.payroll_list.pk)

        rows = self.get_rows()
        created_count = 0
        row_errors = []
        for row in rows:
            assignment = row['assignment']
            raw = (request.POST.get(f'amount_{assignment.pk}') or '').strip()
            if not raw:
                continue
            try:
                amount = Decimal(raw)
            except (InvalidOperation, ValueError):
                row_errors.append(_("%(name)s : montant invalide.") % {'name': assignment.personnel})
                continue
            item = PayrollListItem(
                payroll_list=self.payroll_list, personnel=assignment.personnel,
                assignment=assignment, amount=amount,
            )
            try:
                with transaction.atomic():
                    item.full_clean()
                    item.save()
                created_count += 1
            except ValidationError as e:
                message_dict = getattr(e, 'message_dict', None)
                if message_dict:
                    text = '; '.join(msg for msgs in message_dict.values() for msg in msgs)
                else:
                    text = '; '.join(e.messages)
                row_errors.append(f"{assignment.personnel}: {text}")

        if created_count:
            messages.success(request, _("%(n)d paiement(s) ajouté(s) à la liste.") % {'n': created_count})
        for err in row_errors:
            messages.error(request, err)
        if not created_count and not row_errors:
            messages.warning(request, _("Aucun montant saisi."))
        return redirect('finance:payroll_detail', pk=self.payroll_list.pk)


@login_required
def payroll_submit(request, pk):
    """BROUILLON -> SOUMISE (PayrollList.submit()). Role-gated to
    PAYROLL_PREPARE_ROLES in the list's site's cabinet."""
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
    """SOUMISE -> PAYEE (PayrollList.disburse()). Role-gated to
    PAYROLL_DISBURSE_ROLES in the list's site's cabinet — note this role
    set overlaps with PAYROLL_PREPARE_ROLES, so the same person can both
    prepare and disburse a given list (no enforced separation of duties)."""
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
# Paie du personnel — "Ingénieurs & Staff" tab (SalaryPaymentList /
# SalaryPaymentItem): same brouillon -> soumise -> payée workflow as
# PayrollList above ("Main d'œuvre" tab), just cabinet-scoped instead of
# site-scoped, since Ingénieurs & Staff aren't tied to a chantier. Same
# role gates, same "Liste de paie" landing area, switched between via the
# tabs in the templates.
# ---------------------------------------------------------------------

class SalaryPaymentListListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Lists "Ingénieurs & Staff" payment lists for the caller's cabinet(s).
    allowed_roles = PAYROLL_VIEW_ROLES, same sensitivity rationale as
    PayrollListListView.

    FIXED 2026-10-06: same approved_cabinet_roles fix as PayrollListListView."""
    model = SalaryPaymentList
    template_name = 'finance/salary_payment_list.html'
    context_object_name = 'salary_payment_lists'
    allowed_roles = PAYROLL_VIEW_ROLES
    header_title = _("Paie du personnel")
    header_subtitle = _("Ingénieurs & Staff — salaire mensuel fixe, hors chantier")

    def get_queryset(self):
        qs = SalaryPaymentList.objects.select_related('cabinet', 'prepared_by').order_by('-created_at')
        user = self.request.user
        if not user.is_superuser:
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
            qs = qs.filter(cabinet__in=cabinets)
        else:
            active_cabinet = get_session_cabinet(self.request)
            if active_cabinet:
                qs = qs.filter(cabinet=active_cabinet)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'salary_payment'
        return context

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=PAYROLL_PREPARE_ROLES
        ).exists():
            return [{
                'label': _("Nouvelle liste"),
                'url': str(reverse_lazy('finance:salary_payment_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class SalaryPaymentListCreateView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, CreateView):
    """Starts a new BROUILLON SalaryPaymentList. allowed_roles =
    PAYROLL_PREPARE_ROLES; cabinet resolved via get_user_cabinet() or an
    explicit field for a multi-cabinet user (add_ambiguous_cabinet_field)."""
    model = SalaryPaymentList
    form_class = SalaryPaymentListForm
    template_name = 'finance/salary_payment_form.html'
    allowed_roles = PAYROLL_PREPARE_ROLES
    header_title = _("Nouvelle liste — Ingénieurs & Staff")
    back_url = reverse_lazy('finance:salary_payment_list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        add_ambiguous_cabinet_field(self, form)
        return form

    def form_valid(self, form):
        # See PriceLibraryItemCreateView.form_valid (pricing/views.py) — the
        # same get_user_cabinet()-or-explicit-field resolution, shared via
        # core.mixins.add_ambiguous_cabinet_field.
        cabinet = self.get_user_cabinet() or form.cleaned_data.get('cabinet')
        if not cabinet:
            messages.error(self.request, _("Identification du cabinet échouée."))
            return self.form_invalid(form)
        form.instance.cabinet = cabinet
        form.instance.prepared_by = self.request.user
        messages.success(self.request, _("Liste créée. Ajoutez maintenant les agents à payer."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('finance:salary_payment_detail', kwargs={'pk': self.object.pk})


class SalaryPaymentListDetailView(LoginRequiredMixin, RoleRequiredMixin, CabinetAccessMixin, PageHeaderMixin, DetailView):
    """SalaryPaymentList detail; same allowed_roles / can_act_for_cabinet
    pattern as PayrollListDetailView, scoped by cabinet instead of site."""
    model = SalaryPaymentList
    template_name = 'finance/salary_payment_detail.html'
    context_object_name = 'salary_payment_list'
    allowed_roles = PAYROLL_VIEW_ROLES
    cabinet_lookup_field = 'cabinet'

    def get_header_title(self):
        return str(self.object)

    def get_back_url(self):
        return str(reverse_lazy('finance:salary_payment_list'))

    def get_header_actions(self):
        return [{
            'label': _("Exporter en PDF"),
            'url': str(reverse_lazy('finance:salary_payment_detail_pdf', kwargs={'pk': self.object.pk})),
            'icon': 'file-pdf',
            'class': 'btn-falcon-default',
        }]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_prepare'] = can_act_for_cabinet(self.request, self.object.cabinet, PAYROLL_PREPARE_ROLES)
        context['can_disburse'] = can_act_for_cabinet(self.request, self.object.cabinet, PAYROLL_DISBURSE_ROLES)
        if context['can_prepare'] and self.object.status == PayrollListStatus.BROUILLON:
            context['item_form'] = SalaryPaymentItemForm(cabinet=self.object.cabinet)
        if context['can_disburse'] and self.object.status == PayrollListStatus.SOUMISE:
            disburse_form = PayrollDisburseForm()
            disburse_form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=self.object.cabinet)
            context['disburse_form'] = disburse_form
        return context


class SalaryPaymentItemCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Adds one agent/period/amount row to a SalaryPaymentList.
    allowed_roles = PAYROLL_PREPARE_ROLES, scoped via get_role_cabinet() to
    the list's own cabinet; refuses once the list is no longer BROUILLON."""
    model = SalaryPaymentItem
    form_class = SalaryPaymentItemForm
    allowed_roles = PAYROLL_PREPARE_ROLES

    def dispatch(self, request, *args, **kwargs):
        self.salary_payment_list = get_object_or_404(SalaryPaymentList, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_role_cabinet(self):
        return self.salary_payment_list.cabinet

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['cabinet'] = self.salary_payment_list.cabinet
        return kwargs

    def form_valid(self, form):
        if self.salary_payment_list.status != PayrollListStatus.BROUILLON:
            messages.error(self.request, _("Cette liste n'est plus modifiable."))
            return redirect('finance:salary_payment_detail', pk=self.salary_payment_list.pk)
        form.instance.salary_payment_list = self.salary_payment_list
        messages.success(self.request, _("Agent ajouté à la liste."))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("Impossible d'ajouter : %(errors)s") % {'errors': form.errors.as_text()})
        return redirect('finance:salary_payment_detail', pk=self.salary_payment_list.pk)

    def get_success_url(self):
        return reverse_lazy('finance:salary_payment_detail', kwargs={'pk': self.salary_payment_list.pk})


@login_required
def payroll_detail_pdf(request, pk):
    """PDF export of one payroll list — one row per worker, mirroring
    expense_report_pdf's tabular use of render_table_report_pdf rather
    than the single-document key/value layout used for invoices."""
    payroll_list = get_object_or_404(PayrollList, pk=pk)
    if not can_act_for_cabinet(request, payroll_list.site.cabinet, PAYROLL_VIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:payroll_detail', pk=pk)

    from core.pdf_utils import render_table_report_pdf

    items = payroll_list.items.select_related('personnel', 'assignment').order_by('personnel__last_name')
    rows = [
        (
            str(item.personnel),
            (str(item.assignment) if item.assignment else '-'),
            f"{item.amount:.2f} $",
            item.progress_note[:60] if item.progress_note else '-',
        )
        for item in items
    ]
    total = payroll_list.total_amount
    return render_table_report_pdf(
        filename=f"liste-paie-{payroll_list.pk}.pdf",
        title=_("Liste de paie — %(site)s") % {'site': payroll_list.site.name},
        subtitle=_("Statut : %(status)s") % {'status': payroll_list.get_status_display()},
        columns=[_("Ouvrier"), _("Convention"), _("Montant"), _("Avancement / justification")],
        rows=rows,
        totals_row=["", _("Total"), f"{total:.2f} $", ""],
        generated_by=request.user.get_full_name() or request.user.username,
    )


@login_required
def salary_payment_detail_pdf(request, pk):
    """PDF export of one salary payment list — one row per agent, same
    tabular pattern as payroll_detail_pdf."""
    salary_payment_list = get_object_or_404(SalaryPaymentList, pk=pk)
    if not can_act_for_cabinet(request, salary_payment_list.cabinet, PAYROLL_VIEW_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:salary_payment_detail', pk=pk)

    from core.pdf_utils import render_table_report_pdf

    items = salary_payment_list.items.select_related('personnel').order_by('personnel__last_name')
    rows = [
        (
            str(item.personnel),
            item.period,
            f"{item.amount:.2f} $",
            item.notes[:60] if item.notes else '-',
        )
        for item in items
    ]
    total = salary_payment_list.total_amount
    return render_table_report_pdf(
        filename=f"paie-personnel-{salary_payment_list.pk}.pdf",
        title=_("Paie du personnel — %(cabinet)s") % {'cabinet': salary_payment_list.cabinet.name},
        subtitle=_("Statut : %(status)s") % {'status': salary_payment_list.get_status_display()},
        columns=[_("Agent"), _("Période"), _("Montant"), _("Notes")],
        rows=rows,
        totals_row=["", _("Total"), f"{total:.2f} $", ""],
        generated_by=request.user.get_full_name() or request.user.username,
    )


@login_required
def salary_payment_submit(request, pk):
    """BROUILLON -> SOUMISE (SalaryPaymentList.submit()). Role-gated to
    PAYROLL_PREPARE_ROLES in the list's cabinet."""
    salary_payment_list = get_object_or_404(SalaryPaymentList, pk=pk)
    if request.method != 'POST':
        return redirect('finance:salary_payment_detail', pk=pk)
    if not can_act_for_cabinet(request, salary_payment_list.cabinet, PAYROLL_PREPARE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:salary_payment_detail', pk=pk)
    try:
        salary_payment_list.submit(request.user)
        messages.success(request, _("Liste soumise à la caisse."))
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('finance:salary_payment_detail', pk=pk)


@login_required
def salary_payment_disburse(request, pk):
    """SOUMISE -> PAYEE (SalaryPaymentList.disburse()). Role-gated to
    PAYROLL_DISBURSE_ROLES in the list's cabinet; same prepare/disburse
    role overlap caveat as payroll_disburse() above."""
    salary_payment_list = get_object_or_404(SalaryPaymentList, pk=pk)
    if request.method != 'POST':
        return redirect('finance:salary_payment_detail', pk=pk)
    if not can_act_for_cabinet(request, salary_payment_list.cabinet, PAYROLL_DISBURSE_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:salary_payment_detail', pk=pk)
    form = PayrollDisburseForm(request.POST)
    form.fields['caisse'].queryset = Caisse.objects.filter(cabinet=salary_payment_list.cabinet)
    if form.is_valid():
        try:
            salary_payment_list.disburse(request.user, form.cleaned_data['caisse'])
            messages.success(request, _("Paie décaissée."))
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Sélectionnez une caisse valide."))
    return redirect('finance:salary_payment_detail', pk=pk)


# ---------------------------------------------------------------------
# Avenants (dépassement de budget autorisé -> dette client)
# ---------------------------------------------------------------------

class AvenantListView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, ListView):
    """Lists avenants for the caller's cabinet(s). allowed_roles =
    AVENANT_VIEW_ROLES (requesters + final authorizers); `can_decide` in
    context gates the approve/reject buttons to FINAL_AUTHORIZATION_ROLES.

    FIXED 2026-10-06: cabinet scoping, `can_decide`, and the "Nouvel
    avenant" action check all now use approved_cabinet_roles /
    status=ApprovalStatus.APPROVED."""
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
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True) if hasattr(user, 'approved_cabinet_roles') else []
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
            self.request.user.approved_cabinet_roles.filter(role__in=FINAL_AUTHORIZATION_ROLES).exists()
        )
        return context

    def get_header_actions(self):
        from accounts.models import UserCabinetRole
        if self.request.user.is_superuser or UserCabinetRole.objects.filter(
            user=self.request.user, status=ApprovalStatus.APPROVED, role__in=AVENANT_REQUEST_ROLES
        ).exists():
            return [{
                'label': _("Nouvel avenant"),
                'url': str(reverse_lazy('finance:avenant_create')),
                'icon': 'plus',
                'class': 'btn-falcon-primary',
            }]
        return []


class AvenantCreateView(LoginRequiredMixin, RoleRequiredMixin, PageHeaderMixin, CreateView):
    """Submits a new PENDING Avenant. allowed_roles = AVENANT_REQUEST_ROLES
    (DIRECTOR, DIRECTEUR_TECHNIQUE, DIRECTEUR_GENERAL, CHIEF_ENGINEER,
    ACCOUNTANT) — note the three director-tier roles here are the same
    roles that can later decide the request via _avenant_decide() below.
    A director can still request an avenant that another director-tier
    user (or any other FINAL_AUTHORIZATION_ROLES holder) later decides —
    Avenant.approve()/reject() just block that *same* user from deciding
    their *own* request (see Avenant's class docstring in
    finance/models.py)."""
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
            cabinets = user.approved_cabinet_roles.values_list('cabinet', flat=True)
            form.fields['site'].queryset = Site.objects.filter(cabinet__in=cabinets)
        return form

    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        response = super().form_valid(form)
        from core.notifications import notify_role_holders
        notify_role_holders(
            self.object.site.cabinet, FINAL_AUTHORIZATION_ROLES,
            _("Nouvel avenant à autoriser : +%(amount)s $ (%(site)s)") % {
                'amount': self.object.amount, 'site': self.object.site.name,
            },
            str(reverse_lazy('finance:avenant_list')),
            exclude_user=self.request.user,
        )
        messages.success(self.request, _("Avenant soumis pour autorisation."))
        return response


def _avenant_decide(request, pk, approve):
    """Shared implementation of avenant_approve/avenant_reject: PENDING ->
    APPROVED or PENDING -> REJECTED (Avenant.approve()/reject(), which
    themselves now block the requester from deciding their own avenant —
    see Avenant's class docstring in finance/models.py). Role-gated to
    FINAL_AUTHORIZATION_ROLES in the avenant's site's cabinet via
    can_act_for_cabinet()."""
    avenant = get_object_or_404(Avenant, pk=pk)
    if request.method != 'POST':
        return redirect('finance:avenant_list')
    if not can_act_for_cabinet(request, avenant.site.cabinet, FINAL_AUTHORIZATION_ROLES):
        messages.error(request, _("Vous n'avez pas la permission d'effectuer cette action."))
        return redirect('finance:avenant_list')
    form = AvenantDecisionForm(request.POST)
    notes = form.data.get('notes', '') if form.is_valid() else ''
    from core.notifications import notify_user
    try:
        if approve:
            avenant.approve(request.user, notes=notes)
            notify_user(
                avenant.requested_by,
                _("Votre avenant a été autorisé : +%(amount)s $") % {'amount': avenant.amount},
                str(reverse_lazy('finance:avenant_list')),
            )
            messages.success(request, _("Avenant autorisé — budget et dette client mis à jour."))
        else:
            avenant.reject(request.user, notes=notes)
            notify_user(
                avenant.requested_by,
                _("Votre avenant a été rejeté : +%(amount)s $") % {'amount': avenant.amount},
                str(reverse_lazy('finance:avenant_list')),
            )
            messages.success(request, _("Avenant rejeté."))
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('finance:avenant_list')


@login_required
def avenant_approve(request, pk):
    """Thin wrapper around _avenant_decide(approve=True). FIXED
    2026-10-06: added the @login_required decorator every other action
    view in this module already had — it previously still failed closed
    for an anonymous request (can_act_for_cabinet() returns False for an
    unauthenticated user), but relying on that instead of declaring it
    explicitly was an inconsistency waiting to bite a future refactor."""
    return _avenant_decide(request, pk, approve=True)


@login_required
def avenant_reject(request, pk):
    """Thin wrapper around _avenant_decide(approve=False). Same
    @login_required fix as avenant_approve above."""
    return _avenant_decide(request, pk, approve=False)
