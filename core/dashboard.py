"""
Aggregation logic for the main dashboard (Tableau de Bord).

Every queryset here is scoped to the current user's cabinet(s) using the
same rules as CabinetAccessMixin (core/mixins.py): a superuser sees the
session-selected cabinet, or every cabinet if none is selected; a regular
user sees only the cabinets they hold a UserCabinetRole on.

Kept out of core/views.py so HomeView stays a thin wrapper and this logic
can be unit-tested / reused (e.g. from a future API endpoint) on its own.
"""
import calendar as calendar_module
from datetime import date, timedelta

from django.db.models import Sum, Count, F, Q, DecimalField
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.template.defaultfilters import floatformat
from django.utils import timezone

from core.mixins import get_session_cabinet
from projects.models import Site, ProjectPhase
from finance.models import Expense, CaisseTransaction
from personnel.models import Personnel
from revenue.models import Devis, DevisLine, Invoice, Payment
from procurement.models import PurchaseOrder, StockItem
from tasks.models import Task
from chantiermobile.constants import (
    SiteStatus, ExpenseStatus, DevisStatus, InvoiceStatus,
    TaskStatus, PersonnelType, StatusBadgeClasses, UserRoles, CaisseTransactionType,
)

# Roles that legitimately need to see money on the dashboard (revenue,
# expenses, margin, invoicing, budgets). Everyone else (CHIEF_ENGINEER,
# ENGINEER, WORKER) gets the same operational widgets — sites, tasks,
# stock, personnel — without financial figures. Superusers always pass
# (see can_view_financials below), matching has_role's convention
# elsewhere in the app (accounts/templatetags/rbac_tags.py).
FINANCIAL_ROLES = [UserRoles.DIRECTOR, UserRoles.DIRECTEUR_TECHNIQUE, UserRoles.DIRECTEUR_GENERAL, UserRoles.ACCOUNTANT, UserRoles.CASHIER]


def can_view_financials(request):
    """RBAC gate for the dashboard's financial widgets.

    Kept next to scoped_cabinet_ids as its own testable function rather
    than a template-level check, so the same rule can be asserted in
    tests without rendering HTML.

    FIXED 2026-10-06: only an APPROVED UserCabinetRole counts (see
    core/mixins.py and docs/security.md) — a PENDING financial role no
    longer unlocks the money widgets before a superadmin approves it.
    """
    user = request.user
    if user.is_superuser:
        return True
    return user.approved_cabinet_roles.filter(role__in=FINANCIAL_ROLES).exists()

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
APPROVED_OR_PAID = [ExpenseStatus.APPROVED, ExpenseStatus.PAID]
OPEN_INVOICE = [InvoiceStatus.SENT, InvoiceStatus.OVERDUE]
DECIDED_DEVIS = [DevisStatus.ACCEPTE, DevisStatus.REFUSE, DevisStatus.EXPIRE]

# Falcon's own CSS custom-property palette (static/assets/css/theme.css),
# duplicated here so chart colors match the badge colors used everywhere
# else in the app (StatusBadgeClasses uses the Bootstrap class names for
# the same palette).
COLOR_HEX = {
    'primary': '#2c7be5',
    'secondary': '#748194',
    'success': '#00d27a',
    'info': '#27bcfd',
    'warning': '#f5803e',
    'danger': '#e63757',
}

_FR_MONTHS = ['', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']


def _month_label(d):
    return f"{_FR_MONTHS[d.month]} {d.year}"


def _months_back(d, n):
    """The 1st of the month `n` months before `d`."""
    month = d.month - n
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    return d.replace(year=year, month=month, day=1)


def _pct_change(current, previous):
    """Percent change of current vs previous, or None when not meaningful."""
    if not previous:
        return None
    return float((current - previous) / previous * 100)


def _badge_hex(status_map, key):
    bootstrap_class = status_map.get(key, 'bg-secondary')
    color_name = bootstrap_class.replace('bg-', '')
    return COLOR_HEX.get(color_name, COLOR_HEX['secondary'])


def scoped_cabinet_ids(request):
    """None means "no restriction" (superuser viewing every cabinet).
    Otherwise a list of cabinet ids (possibly empty, for a user with no
    APPROVED cabinet role at all — FIXED 2026-10-06, see
    core/mixins.py and docs/security.md: a PENDING role no longer
    scopes the dashboard into a cabinet it doesn't yet actually grant
    access to)."""
    user = request.user
    if user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            return [active_cabinet.id]
        return None
    return list(user.approved_cabinet_roles.values_list('cabinet_id', flat=True))


def _scope(qs, path, cabinet_ids):
    if cabinet_ids is None:
        return qs
    return qs.filter(**{f'{path}__in': cabinet_ids})


def build_dashboard_context(request):
    """Builds the full template context for the "Tableau de Bord" home
    page: hero KPIs (cash collected, spend, margin, site portfolio),
    secondary chips (pipeline, overdue invoices/tasks, low stock, pending
    expenses), a 6-month cashflow trend, three donut charts (devis, tasks,
    workforce), budget-usage and per-site-expense tables, and a merged
    recent-activity feed — all scoped to the caller's Cabinet(s) via
    scoped_cabinet_ids(). Financial figures are included unconditionally
    here; it's the template's job (gated by `can_view_financials`) to hide
    them from a role that shouldn't see money."""
    cabinet_ids = scoped_cabinet_ids(request)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    prev_month_start = _months_back(today, 1)
    six_months_start = _months_back(today, 5)

    sites = _scope(Site.objects.all(), 'cabinet_id', cabinet_ids)
    personnel = _scope(Personnel.objects.all(), 'cabinet_id', cabinet_ids)
    expenses = _scope(Expense.objects.all(), 'site__cabinet_id', cabinet_ids)
    devis = _scope(Devis.objects.all(), 'site__cabinet_id', cabinet_ids)
    devis_lines = _scope(DevisLine.objects.all(), 'devis__site__cabinet_id', cabinet_ids)
    invoices = _scope(Invoice.objects.all(), 'contract__site__cabinet_id', cabinet_ids)
    payments = _scope(Payment.objects.all(), 'invoice__contract__site__cabinet_id', cabinet_ids)
    purchase_orders = _scope(PurchaseOrder.objects.all(), 'site__cabinet_id', cabinet_ids)
    stock_items = _scope(StockItem.objects.all(), 'site__cabinet_id', cabinet_ids)
    tasks = _scope(Task.objects.all(), 'site__cabinet_id', cabinet_ids)

    approved_expenses = expenses.filter(status__in=APPROVED_OR_PAID)

    # ------------------------------------------------------------------
    # Hero KPIs: cash collected, spend, net margin, site portfolio
    # ------------------------------------------------------------------
    revenue_all = payments.aggregate(t=Sum('amount'))['t'] or 0
    revenue_month = payments.filter(payment_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
    revenue_prev_month = payments.filter(
        payment_date__gte=prev_month_start, payment_date__lt=month_start
    ).aggregate(t=Sum('amount'))['t'] or 0

    expense_all = approved_expenses.aggregate(t=Sum('amount'))['t'] or 0
    expense_month = approved_expenses.filter(expense_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
    expense_prev_month = approved_expenses.filter(
        expense_date__gte=prev_month_start, expense_date__lt=month_start
    ).aggregate(t=Sum('amount'))['t'] or 0

    net_margin = revenue_all - expense_all
    margin_pct = float(net_margin / revenue_all * 100) if revenue_all else None

    site_status_counts = dict(sites.values_list('status').annotate(n=Count('id')))
    total_sites_count = sites.count()
    active_sites_count = site_status_counts.get(SiteStatus.ACTIVE, 0)

    # ------------------------------------------------------------------
    # Secondary KPI chips
    # ------------------------------------------------------------------
    pipeline_devis_qs = devis.filter(status=DevisStatus.ENVOYE)
    pipeline_value = devis_lines.filter(devis__status=DevisStatus.ENVOYE).aggregate(
        t=Sum(F('quantity') * F('unit_price_ht'), output_field=MONEY_FIELD)
    )['t'] or 0
    pipeline_count = pipeline_devis_qs.count()

    decided_count = devis.filter(status__in=DECIDED_DEVIS).count()
    accepted_count = devis.filter(status=DevisStatus.ACCEPTE).count()
    conversion_rate = (accepted_count / decided_count * 100) if decided_count else None

    overdue_invoices_qs = invoices.filter(
        status__in=OPEN_INVOICE, due_date__lt=today
    ).select_related('contract__site').order_by('due_date')
    overdue_invoices_count = overdue_invoices_qs.count()
    overdue_invoices_amount = overdue_invoices_qs.aggregate(t=Sum('amount'))['t'] or 0

    overdue_tasks_qs = tasks.exclude(status=TaskStatus.TERMINEE).filter(
        due_date__lt=today, due_date__isnull=False
    ).select_related('site', 'assigned_to').order_by('due_date')
    overdue_tasks_count = overdue_tasks_qs.count()

    low_stock_qs = stock_items.filter(
        reorder_threshold__isnull=False, quantity_on_hand__lte=F('reorder_threshold')
    ).select_related('site').order_by('quantity_on_hand')
    low_stock_count = low_stock_qs.count()

    pending_expenses_qs = expenses.filter(status=ExpenseStatus.PENDING)
    pending_expenses_count = pending_expenses_qs.count()
    pending_expenses_amount = pending_expenses_qs.aggregate(t=Sum('amount'))['t'] or 0

    # ------------------------------------------------------------------
    # Cash flow trend, last 6 months (Trésorerie)
    # ------------------------------------------------------------------
    revenue_by_month = dict(
        payments.filter(payment_date__gte=six_months_start)
        .annotate(month=TruncMonth('payment_date')).values('month')
        .annotate(total=Sum('amount')).values_list('month', 'total')
    )
    expense_by_month = dict(
        approved_expenses.filter(expense_date__gte=six_months_start)
        .annotate(month=TruncMonth('expense_date')).values('month')
        .annotate(total=Sum('amount')).values_list('month', 'total')
    )
    cashflow_labels, cashflow_revenue, cashflow_expense, cashflow_margin = [], [], [], []
    for i in range(5, -1, -1):
        bucket = _months_back(today, i)
        rev = float(revenue_by_month.get(bucket, 0) or 0)
        exp = float(expense_by_month.get(bucket, 0) or 0)
        cashflow_labels.append(_month_label(bucket))
        cashflow_revenue.append(round(rev, 2))
        cashflow_expense.append(round(exp, 2))
        cashflow_margin.append(round(rev - exp, 2))

    # ------------------------------------------------------------------
    # Devis pipeline by status (donut)
    # ------------------------------------------------------------------
    devis_status_counts = dict(devis.values_list('status').annotate(n=Count('id')))
    devis_chart = [
        {
            'name': str(label),
            'value': devis_status_counts.get(key, 0),
            'color': _badge_hex(StatusBadgeClasses.DEVIS_STATUS, key),
        }
        for key, label in DevisStatus.choices
    ]

    # ------------------------------------------------------------------
    # Budget usage by active site (top 6, reuses Site.budget_usage_percentage)
    # ------------------------------------------------------------------
    budgeted_sites = list(
        sites.filter(status=SiteStatus.ACTIVE, budget__isnull=False).select_related('budget')
    )
    budget_rows = sorted(
        (
            {
                'name': s.name,
                'usage': s.budget_usage_percentage,
                'spent': s.total_spent,
                'total': s.budget.total_amount,
                'url': reverse('projects:site_detail', kwargs={'unique_id': s.unique_id}),
            }
            for s in budgeted_sites
        ),
        key=lambda r: r['usage'],
        reverse=True,
    )[:6]

    # ------------------------------------------------------------------
    # Total expenses per chantier, ALL sites (not just active+budgeted
    # ones like budget_rows above) — what the director used to have to
    # call the accountant for. Sorted by amount spent, so the biggest
    # spenders surface first; links straight into the filterable expense
    # report, pre-filtered to that site, for the "historique en détail".
    # ------------------------------------------------------------------
    site_expense_totals = dict(
        approved_expenses.values('site').annotate(total=Sum('amount')).values_list('site', 'total')
    )
    expenses_by_site_rows = sorted(
        (
            {
                'name': s.name,
                'spent': site_expense_totals[s.id],
                'url': f"{reverse('finance:expense_report')}?site={s.id}",
            }
            for s in sites if s.id in site_expense_totals
        ),
        key=lambda r: r['spent'],
        reverse=True,
    )[:8]

    # ------------------------------------------------------------------
    # Task status distribution (donut)
    # ------------------------------------------------------------------
    task_status_counts = dict(tasks.values_list('status').annotate(n=Count('id')))
    task_chart = [
        {
            'name': str(label),
            'value': task_status_counts.get(key, 0),
            'color': _badge_hex(StatusBadgeClasses.TASK_STATUS, key),
        }
        for key, label in TaskStatus.choices
    ]

    # ------------------------------------------------------------------
    # Workforce mobilized today, by personnel type (donut)
    # ------------------------------------------------------------------
    active_assignment_q = Q(assignments__start_date__lte=today) & (
        Q(assignments__end_date__gte=today) | Q(assignments__end_date__isnull=True)
    )
    mobilized = personnel.filter(active_assignment_q).distinct()
    mobilized_type_counts = dict(mobilized.values_list('personnel_type').annotate(n=Count('id')))
    personnel_chart = [
        {
            'name': str(label),
            'value': mobilized_type_counts.get(key, 0),
            'color': _badge_hex(StatusBadgeClasses.PERSONNEL_TYPE, key),
        }
        for key, label in PersonnelType.choices
    ]
    mobilized_count = mobilized.count()
    total_personnel_count = personnel.count()

    # ------------------------------------------------------------------
    # Recent activity feed — merged from the modules that matter most,
    # already cabinet-scoped above.
    # ------------------------------------------------------------------
    activity = []
    for d in devis.select_related('site').order_by('-updated_at')[:6]:
        activity.append({
            'icon': 'file-invoice-dollar', 'color': _badge_hex(StatusBadgeClasses.DEVIS_STATUS, d.status),
            'title': f"Devis {d.devis_number} — {d.get_status_display()}",
            'subtitle': f"{d.client_name} · {d.site.name}",
            'timestamp': d.updated_at,
            'url': reverse('revenue:devis_detail', kwargs={'pk': d.pk}),
        })
    for inv in invoices.select_related('contract__site').order_by('-updated_at')[:6]:
        activity.append({
            'icon': 'receipt', 'color': _badge_hex(StatusBadgeClasses.INVOICE_STATUS, inv.status),
            'title': f"Facture {inv.invoice_number} — {inv.get_status_display()}",
            'subtitle': f"{inv.contract.site.name}",
            'timestamp': inv.updated_at,
            'url': reverse('revenue:invoice_detail', kwargs={'pk': inv.pk}),
        })
    for po in purchase_orders.select_related('site', 'supplier').order_by('-updated_at')[:6]:
        activity.append({
            'icon': 'truck-loading', 'color': _badge_hex(StatusBadgeClasses.PURCHASE_ORDER_STATUS, po.status),
            'title': f"BC {po.order_number} — {po.get_status_display()}",
            'subtitle': f"{po.supplier.name} · {po.site.name}",
            'timestamp': po.updated_at,
            'url': reverse('procurement:purchase_order_detail', kwargs={'pk': po.pk}),
        })
    for t in tasks.select_related('site').order_by('-updated_at')[:6]:
        activity.append({
            'icon': 'tasks', 'color': _badge_hex(StatusBadgeClasses.TASK_STATUS, t.status),
            'title': f"{t.title} — {t.get_status_display()}",
            'subtitle': t.site.name,
            'timestamp': t.updated_at,
            'url': reverse('tasks:task_detail', kwargs={'pk': t.pk}),
        })
    for e in expenses.select_related('site').order_by('-updated_at')[:6]:
        activity.append({
            'icon': 'money-bill-wave', 'color': _badge_hex(StatusBadgeClasses.EXPENSE_STATUS, e.status),
            'title': f"Dépense ${floatformat(e.amount, '2g')} — {e.get_status_display()}",
            'subtitle': e.site.name,
            'timestamp': e.updated_at,
            'url': reverse('finance:expense_detail', kwargs={'pk': e.pk}),
        })
    activity.sort(key=lambda item: item['timestamp'], reverse=True)
    activity = activity[:8]

    return {
        # Hero KPIs
        'revenue_all': revenue_all,
        'revenue_month': revenue_month,
        'revenue_trend': _pct_change(revenue_month, revenue_prev_month),
        'expense_all': expense_all,
        'expense_month': expense_month,
        'expense_trend': _pct_change(expense_month, expense_prev_month),
        'net_margin': net_margin,
        'margin_pct': margin_pct,
        'total_sites_count': total_sites_count,
        'active_sites_count': active_sites_count,
        'planning_sites_count': site_status_counts.get(SiteStatus.PLANNING, 0),
        'paused_sites_count': site_status_counts.get(SiteStatus.PAUSED, 0),
        'completed_sites_count': site_status_counts.get(SiteStatus.COMPLETED, 0),

        # Secondary chips
        'pipeline_value': pipeline_value,
        'pipeline_count': pipeline_count,
        'conversion_rate': conversion_rate,
        'overdue_invoices_count': overdue_invoices_count,
        'overdue_invoices_amount': overdue_invoices_amount,
        'overdue_tasks_count': overdue_tasks_count,
        'low_stock_count': low_stock_count,
        'pending_expenses_count': pending_expenses_count,
        'pending_expenses_amount': pending_expenses_amount,

        # Watchlists
        'overdue_invoices': overdue_invoices_qs[:5],
        'overdue_tasks': overdue_tasks_qs[:5],
        'low_stock_items': low_stock_qs[:5],

        # Charts (JSON-serializable)
        'cashflow_labels': cashflow_labels,
        'cashflow_revenue': cashflow_revenue,
        'cashflow_expense': cashflow_expense,
        'cashflow_margin': cashflow_margin,
        'devis_chart': devis_chart,
        'task_chart': task_chart,
        'personnel_chart': personnel_chart,
        'budget_rows': budget_rows,
        'expenses_by_site_rows': expenses_by_site_rows,
        'mobilized_count': mobilized_count,
        'total_personnel_count': total_personnel_count,

        # Activity feed
        'activity_items': activity,

        # Viewing scope (used to label the page when a superuser has no
        # active cabinet selected)
        'dashboard_all_cabinets': cabinet_ids is None and request.user.is_superuser,

        # RBAC: whether this user's role(s) may see financial figures
        # (revenue, expenses, margin, invoices, budgets) on the dashboard.
        'can_view_financials': can_view_financials(request),
    }


def build_calendar_context(request):
    """Builds the "Accueil" calendar widget's context (added 2026-10-19,
    meeting-note backlog "Accueil et tableau de bord" — "l'écran
    d'accueil doit afficher la liste des chantiers, avec une vue
    calendrier où chaque date est cliquable"). Also returns the
    "Chantiers" list the client asked for alongside it.

    The client's own note left open whether this calendar should cover
    only caisse movements or also planning tasks, suggesting both could
    "cohabiter... avec un code couleur distinct" — the reasonable default
    taken here is to show both: a caisse net amount (color-coded
    green/red, financial-role-gated via can_view_financials) and a count
    of planning tasks starting that day (operational, shown to everyone,
    reusing the same ProjectPhase.start_date data the Gantt view reads —
    see projects.views.SiteGanttView).

    `request.GET['month']` (format YYYY-MM) picks which month to show;
    defaults to the current month. Each day is a plain link to
    home_day_detail rather than client-side JS, so the whole thing works
    without a calendar JS library (none of this app's templates actually
    wire one up — see FullCalendar being vendored but unused)."""
    cabinet_ids = scoped_cabinet_ids(request)
    today = timezone.localdate()

    month_param = request.GET.get('month', '')
    try:
        year, month = (int(p) for p in month_param.split('-', 1))
        first_of_month = date(year, month, 1)
    except (ValueError, TypeError):
        first_of_month = today.replace(day=1)

    sites = _scope(Site.objects.all(), 'cabinet_id', cabinet_ids).order_by('name')
    sites_list = [
        {
            'name': s.name,
            'status': s.status,
            'status_display': s.get_status_display(),
            'location': s.location,
            'url': reverse('projects:site_detail', kwargs={'unique_id': s.unique_id}),
        }
        for s in sites
    ]

    _, days_in_month = calendar_module.monthrange(first_of_month.year, first_of_month.month)
    month_end = first_of_month.replace(day=days_in_month)

    show_financials = can_view_financials(request)
    caisse_by_day = {}
    if show_financials:
        caisse_qs = _scope(CaisseTransaction.objects.all(), 'caisse__cabinet_id', cabinet_ids).filter(
            date__gte=first_of_month, date__lte=month_end,
        )
        rows = caisse_qs.values('date').annotate(
            entree=Sum('amount', filter=Q(transaction_type=CaisseTransactionType.ENTREE)),
            sortie=Sum('amount', filter=Q(transaction_type=CaisseTransactionType.SORTIE)),
        )
        for row in rows:
            caisse_by_day[row['date']] = (row['entree'] or 0) - (row['sortie'] or 0)

    tasks_qs = _scope(ProjectPhase.objects.all(), 'site__cabinet_id', cabinet_ids).filter(
        start_date__gte=first_of_month, start_date__lte=month_end,
    )
    task_counts_by_day = dict(tasks_qs.values_list('start_date').annotate(n=Count('id')))

    # Calendar.Calendar(firstweekday=0) yields Monday-first weeks, each a
    # list of 7 dates, with days outside first_of_month's month padded in
    # from the previous/next one (never None) — simplest way to always
    # get full weeks for a clean grid.
    cal = calendar_module.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdatescalendar(first_of_month.year, first_of_month.month):
        week_days = []
        for day in week:
            week_days.append({
                'date': day,
                'in_month': day.month == first_of_month.month,
                'is_today': day == today,
                'caisse_net': caisse_by_day.get(day),
                'task_count': task_counts_by_day.get(day, 0),
                'url': reverse('home_day_detail', kwargs={'day': day.isoformat()}),
            })
        weeks.append(week_days)

    prev_month = (first_of_month - timedelta(days=1)).replace(day=1)
    next_month = (month_end + timedelta(days=1))

    return {
        'calendar_sites': sites_list,
        'calendar_weeks': weeks,
        'calendar_month_label': _month_label(first_of_month),
        'calendar_prev_month': prev_month.strftime('%Y-%m'),
        'calendar_next_month': next_month.strftime('%Y-%m'),
        'calendar_current_month': first_of_month.strftime('%Y-%m'),
        'calendar_show_financials': show_financials,
    }


def build_day_detail_context(request, day):
    """Context for the "opérations de ce jour" page a calendar day links
    to — every CaisseTransaction and every ProjectPhase (task) starting
    on `day`, both cabinet-scoped. Financial rows are omitted entirely
    (not just hidden in the template) for a viewer can_view_financials
    doesn't clear, same gating as the calendar widget itself."""
    cabinet_ids = scoped_cabinet_ids(request)

    show_financials = can_view_financials(request)
    caisse_rows = []
    if show_financials:
        caisse_rows = list(
            _scope(CaisseTransaction.objects.all(), 'caisse__cabinet_id', cabinet_ids)
            .filter(date=day).select_related('caisse', 'site', 'category').order_by('-created_at')
        )

    task_rows = list(
        _scope(ProjectPhase.objects.all(), 'site__cabinet_id', cabinet_ids)
        .filter(start_date=day).select_related('site', 'parent_phase').order_by('site__name', 'name')
    )

    return {
        'day': day,
        'caisse_rows': caisse_rows,
        'task_rows': task_rows,
        'can_view_financials': show_financials,
    }
