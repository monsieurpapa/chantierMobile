"""
Global search (item 15, second half, of the Directors/Engineers audit):
the navbar's search box (templates/includes/navbar-top.html) was a Falcon
theme placeholder wired to a client-side widget with no data source, so
it never returned anything — a genuine dead end. There was also no other
way to jump straight to a site, a staff member, a contract or an invoice
by name/number; the only way was to enter each app's list and filter or
scroll by hand.

This module does a simple, cabinet-scoped, case-insensitive substring
search across the handful of entities people actually look up by name:
Sites, Personnel, Contracts and Invoices. It mirrors each entity's own
list view's permission model, which is cabinet membership only — none of
SiteListView / PersonnelListView / ContractListView / InvoiceListView
restricts by role beyond CabinetAccessMixin — so search results never
show more than the matching list page already would.
"""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from accounts.models import Cabinet
from core.mixins import get_session_cabinet

MIN_QUERY_LENGTH = 2
RESULTS_PER_CATEGORY = 8


def _user_cabinet_ids(request):
    """FIXED 2026-10-06: only counts an APPROVED UserCabinetRole (see
    core/mixins.py and docs/security.md) — a PENDING grant no longer
    surfaces another cabinet's records in global search before a
    superadmin approves it."""
    user = request.user
    if user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            return {active_cabinet.pk}
        return set(Cabinet.objects.values_list('pk', flat=True))
    if not hasattr(user, 'cabinet_roles'):
        return set()
    return set(user.approved_cabinet_roles.values_list('cabinet_id', flat=True))


def global_search(request, query):
    """Returns a list of dicts (type_label, icon, title, subtitle, url),
    grouped by entity type, for the given free-text query. Empty or
    too-short queries return an empty list rather than the whole table."""
    query = (query or '').strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    from django.db.models import Q
    from projects.models import Site
    from personnel.models import Personnel
    from revenue.models import Contract, Invoice

    cabinet_ids = _user_cabinet_ids(request)
    if not cabinet_ids:
        return []

    results = []

    sites = Site.objects.filter(
        Q(name__icontains=query) | Q(location__icontains=query),
        cabinet_id__in=cabinet_ids,
    )[:RESULTS_PER_CATEGORY]
    for site in sites:
        results.append({
            'type_label': _('Chantier'), 'icon': 'fa-map-marker-alt', 'badge': 'primary',
            'title': site.name,
            'subtitle': site.location,
            'url': reverse('projects:site_detail', kwargs={'unique_id': site.unique_id}),
        })

    personnel = Personnel.objects.filter(
        Q(first_name__icontains=query) | Q(last_name__icontains=query),
        cabinet_id__in=cabinet_ids,
    )[:RESULTS_PER_CATEGORY]
    for person in personnel:
        results.append({
            'type_label': _('Personnel'), 'icon': 'fa-user', 'badge': 'info',
            'title': person.get_full_name(),
            'subtitle': person.get_trade_display() if person.trade else person.get_category_display(),
            'url': reverse('personnel:personnel_detail', kwargs={'unique_id': person.unique_id}),
        })

    contracts = Contract.objects.filter(
        client_name__icontains=query, site__cabinet_id__in=cabinet_ids,
    ).select_related('site')[:RESULTS_PER_CATEGORY]
    for contract in contracts:
        results.append({
            'type_label': _('Contrat'), 'icon': 'fa-file-contract', 'badge': 'success',
            'title': contract.client_name,
            'subtitle': contract.site.name,
            'url': reverse('revenue:contract_list') + f'#contract-{contract.pk}',
        })

    invoices = Invoice.objects.filter(
        invoice_number__icontains=query, contract__site__cabinet_id__in=cabinet_ids,
    ).select_related('contract', 'contract__site')[:RESULTS_PER_CATEGORY]
    for invoice in invoices:
        results.append({
            'type_label': _('Facture'), 'icon': 'fa-file-invoice-dollar', 'badge': 'warning',
            'title': invoice.invoice_number,
            'subtitle': f"{invoice.contract.client_name} — {invoice.contract.site.name}",
            'url': reverse('revenue:invoice_detail', kwargs={'pk': invoice.pk}),
        })

    return results
