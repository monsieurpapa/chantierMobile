"""
Per-chantier tracking for the dashboard (2026-10-22): where each chantier
stands (current étape, physical progress) and, for roles that see money,
what it has spent against its budget — in total and étape by étape.

Definitions (kept here, in one place, so the numbers are explainable):

- Budget: the chantier's budget DQE (pricing.services.budget_dqe_for_site:
  the accepted devis's DQE, else the approved DQE) — its lines' total.
  Without one, the finance Budget's total_amount. Without either, none.
- Dépensé: approved or paid expenses on the chantier, plus caisse outflows
  booked to it that are not an expense's payment (direct purchases, pay
  disbursements…). An expense's own caisse payment is not counted twice.
- Avancement of a top-level étape: 100 % once clôturée; else the latest
  progress report filed on it or on one of its sous-étapes; else 0 %.
  Chantier avancement = the mean over its top-level étapes.
- Étape en cours: the first top-level étape, by start date, that is not
  clôturée.
- Santé: % of budget consumed compared to avancement — "Dépassement" when
  over 100 % of budget, "À surveiller" when consumption runs more than 15
  points ahead of avancement, else "Conforme".
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, F, Sum
from django.urls import reverse

from chantiermobile.constants import CaisseTransactionType, ExpenseStatus, PhaseStatus, SiteStatus

MONEY = DecimalField(max_digits=16, decimal_places=2)
WATCH_MARGIN = 15  # points of budget consumption ahead of progress


def _pct(part, whole):
    if not whole:
        return None
    return float(part) / float(whole) * 100


def _health(consumed_pct, progress_pct):
    if consumed_pct is None:
        return None
    if consumed_pct > 100:
        return {'key': 'over', 'label': 'Dépassement', 'css': 'danger'}
    if consumed_pct > (progress_pct or 0) + WATCH_MARGIN:
        return {'key': 'watch', 'label': 'À surveiller', 'css': 'warning'}
    return {'key': 'ok', 'label': 'Conforme', 'css': 'success'}


def _phase_progress(sites):
    """{phase_id: latest percentage} for every top-level étape of `sites`
    (its own reports and its sous-étapes' reports both count)."""
    from projects.models import SiteProgress
    latest = {}
    reports = (SiteProgress.objects.filter(phase__site__in=sites)
               .select_related('phase').order_by('report_date', 'created_at'))
    for r in reports:
        top = r.phase.parent_phase_id or r.phase_id
        latest[top] = r.percentage_complete  # ordered: the last one wins
    return latest


def build_site_tracking(sites, with_money):
    """One row per chantier in `sites` (a queryset), most active first."""
    from finance.models import CaisseTransaction, Expense
    from pricing.models import DQELine
    from pricing.services import budget_dqe_for_site
    from projects.models import ProjectPhase
    from revenue.models import Payment

    sites = list(sites.select_related('budget', 'lead_engineer'))
    if not sites:
        return []
    site_ids = [s.pk for s in sites]
    phases = list(ProjectPhase.objects.filter(site_id__in=site_ids).order_by('start_date', 'pk'))
    top_of = {p.pk: (p.parent_phase_id or p.pk) for p in phases}
    tops_by_site = defaultdict(list)
    for p in phases:
        if p.parent_phase_id is None:
            tops_by_site[p.site_id].append(p)
    progress = _phase_progress(site_ids)

    spent_by_site, spent_by_top = defaultdict(Decimal), defaultdict(Decimal)
    budget_by_top = defaultdict(Decimal)
    budget_total, budget_source, received = {}, {}, defaultdict(Decimal)
    if with_money:
        for row in (Expense.objects.filter(site_id__in=site_ids, status__in=[ExpenseStatus.APPROVED, ExpenseStatus.PAID])
                    .values('site_id', 'phase_id').annotate(t=Sum('amount'))):
            spent_by_site[row['site_id']] += row['t'] or 0
            if row['phase_id'] in top_of:
                spent_by_top[top_of[row['phase_id']]] += row['t'] or 0
        for row in (CaisseTransaction.objects.filter(site_id__in=site_ids, expense__isnull=True,
                                                     transaction_type=CaisseTransactionType.SORTIE)
                    .values('site_id', 'phase_id').annotate(t=Sum('amount'))):
            spent_by_site[row['site_id']] += row['t'] or 0
            if row['phase_id'] in top_of:
                spent_by_top[top_of[row['phase_id']]] += row['t'] or 0
        for row in (Payment.objects.filter(invoice__contract__site_id__in=site_ids)
                    .values('invoice__contract__site_id').annotate(t=Sum('amount'))):
            received[row['invoice__contract__site_id']] = row['t'] or 0
        for site in sites:
            dqe = budget_dqe_for_site(site)
            if dqe is not None:
                lines = DQELine.objects.filter(dqe=dqe)
                budget_total[site.pk] = lines.aggregate(
                    t=Sum(F('quantity') * F('unit_price'), output_field=MONEY))['t'] or Decimal('0')
                budget_source[site.pk] = f'DQE {dqe.reference}'
                for row in lines.values('phase_id').annotate(t=Sum(F('quantity') * F('unit_price'), output_field=MONEY)):
                    if row['phase_id'] in top_of:
                        budget_by_top[top_of[row['phase_id']]] += row['t'] or 0
            elif getattr(site, 'budget', None) is not None:
                budget_total[site.pk] = site.budget.total_amount
                budget_source[site.pk] = 'Budget'

    rows = []
    for site in sites:
        tops = tops_by_site.get(site.pk, [])
        etapes = []
        for p in tops:
            pct = 100 if p.status == PhaseStatus.CLOTUREE else progress.get(p.pk, 0)
            etape = {'name': p.name, 'progress': pct, 'closed': p.status == PhaseStatus.CLOTUREE,
                     'start': p.start_date, 'end': p.end_date}
            if with_money:
                b, s = budget_by_top.get(p.pk), spent_by_top.get(p.pk, Decimal('0'))
                etape.update({'budget': b, 'spent': s, 'consumed': _pct(s, b), 'health': _health(_pct(s, b), pct) if b else None})
            etapes.append(etape)
        current = next((e for e in etapes if not e['closed']), None)
        avancement = round(sum(e['progress'] for e in etapes) / len(etapes)) if etapes else None
        row = {
            'name': site.name,
            'status': site.status,
            'status_display': site.get_status_display(),
            'url': reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}),
            'gantt_url': reverse('projects:site_gantt', kwargs={'unique_id': site.unique_id}),
            'lead_engineer': (site.lead_engineer.get_full_name() or site.lead_engineer.username) if site.lead_engineer else '',
            'current_etape': current,
            'closed_count': sum(1 for e in etapes if e['closed']),
            'etape_count': len(etapes),
            'progress': avancement,
            'etapes': etapes,
        }
        if with_money:
            budget, spent = budget_total.get(site.pk), spent_by_site.get(site.pk, Decimal('0'))
            consumed = _pct(spent, budget)
            row.update({
                'budget': budget, 'budget_source': budget_source.get(site.pk, ''),
                'spent': spent, 'remaining': (budget - spent) if budget else None,
                'consumed': consumed, 'received': received.get(site.pk, Decimal('0')),
                'health': _health(consumed, avancement),
                'overrun': (spent - budget) if budget and spent > budget else None,
            })
        rows.append(row)

    order = {SiteStatus.ACTIVE: 0, SiteStatus.PAUSED: 1, SiteStatus.PLANNING: 2, SiteStatus.COMPLETED: 3, SiteStatus.CANCELLED: 4}
    rows.sort(key=lambda r: (order.get(r['status'], 9), -(r.get('consumed') or 0), r['name']))
    return rows


def portfolio_totals(rows):
    """Totals over the chantiers still running (not completed/cancelled)."""
    live = [r for r in rows if r['status'] not in (SiteStatus.COMPLETED, SiteStatus.CANCELLED)]
    budget = sum((r['budget'] or 0) for r in live if r.get('budget'))
    spent = sum((r['spent'] or 0) for r in live if r.get('budget'))  # spend against a known budget
    all_spent = sum((r.get('spent') or 0) for r in live)
    return {
        'sites': len(live),
        'budget': budget,
        'spent': all_spent,
        'consumed': _pct(spent, budget),
        'remaining': budget - spent if budget else None,
        'overrun': spent - budget if budget and spent > budget else None,
        'received': sum((r.get('received') or 0) for r in live),
        'watch': sum(1 for r in live if r.get('health') and r['health']['key'] != 'ok'),
        'unbudgeted': sum(1 for r in live if not r.get('budget')),
    }
