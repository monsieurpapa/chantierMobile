"""
Aggregation for the "Approbations en attente" inbox (item 12 of the
Directors/Engineers audit): before this, there was no single place to see
everything waiting on you — a director had to separately check the
expense list, the material request list, the avenant list, each site's
planning tab, and the leave list, filtering each one down to "pending" by
hand. This module builds one combined, permission-scoped list instead.

Each entry mirrors the exact role/status check its own action view
already enforces (see the comment on each block) — this is a read-only
summary, so it must never show an item the viewer couldn't actually act
on if they clicked through. Kept deliberately duplicated from each app's
own inline role list rather than importing their view modules, to avoid
pulling every app's views into one shared aggregator; if one of those
checks changes, this list should be updated to match.
"""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from accounts.models import Cabinet
from core.mixins import get_session_cabinet
from chantiermobile.constants import (
    ExpenseStatus, MaterialRequestStatus, AvenantStatus, PlanningStatus, ApprovalStatus,
    FINAL_AUTHORIZATION_ROLES,
)

# Mirrors approve_expense/reject_expense in finance/views.py.
EXPENSE_APPROVAL_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'ACCOUNTANT']
# Mirrors MAGASINIER_VALIDATE_ROLES in materials/views.py (request_validate).
MATERIAL_REQUEST_VALIDATE_ROLES = ['MAGASINIER', 'DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL']
# Mirrors FINAL_AUTHORIZATION_ROLES, used as-is by approve_material_request
# and _avenant_decide.
# Mirrors PLANNING_REVIEW_ROLES in projects/views.py.
PLANNING_REVIEW_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER', 'ENGINEER']
# Mirrors HR_ADMIN_ROLES in personnel/views.py (_decide_leave).
LEAVE_DECIDE_ROLES = ['DIRECTOR', 'DIRECTEUR_TECHNIQUE', 'DIRECTEUR_GENERAL', 'CHIEF_ENGINEER']


def _allowed_cabinet_ids(request, roles):
    """Cabinet ids the current user may act on with one of `roles` —
    same superuser/session-cabinet convention as CabinetAccessMixin and
    can_act_for_cabinet (core/mixins.py)."""
    user = request.user
    if user.is_superuser:
        active_cabinet = get_session_cabinet(request)
        if active_cabinet:
            return {active_cabinet.pk}
        return set(Cabinet.objects.values_list('pk', flat=True))
    if not hasattr(user, 'cabinet_roles'):
        return set()
    return set(user.cabinet_roles.filter(role__in=roles).values_list('cabinet_id', flat=True))


def _display_name(user):
    """A human name for `requested_by`, safe against None (Avenant/Expense/
    MaterialRequest's requester FK is nullable) without leaning on the
    template engine's `default` filter, which raises on a chained
    attribute lookup through None rather than treating it as empty."""
    if user is None:
        return ''
    return user.get_full_name() or user.username


def get_pending_approvals(request):
    """Returns a list of dicts, oldest first, each with:
    type, type_label, icon, title, subtitle, site_name, requested_by_name,
    created_at, review_url — ready for the template to render without
    touching a single model."""
    from finance.models import Expense, Avenant
    from materials.models import MaterialRequest
    from projects.models import PlanningSubmission
    from personnel.models import Leave

    items = []

    expense_cabinets = _allowed_cabinet_ids(request, EXPENSE_APPROVAL_ROLES)
    if expense_cabinets:
        for expense in Expense.objects.filter(
            status=ExpenseStatus.PENDING, site__cabinet_id__in=expense_cabinets,
        ).select_related('site', 'category', 'requester').order_by('created_at'):
            items.append({
                'type': 'expense', 'type_label': _('Dépense'), 'icon': 'fa-money-bill-wave', 'badge': 'success',
                'title': f"{expense.category.name} — {expense.amount}",
                'subtitle': expense.description or '',
                'site_name': expense.site.name,
                'requested_by_name': _display_name(expense.requester),
                'created_at': expense.created_at,
                'review_url': reverse('finance:expense_detail', kwargs={'pk': expense.pk}),
            })

    validate_cabinets = _allowed_cabinet_ids(request, MATERIAL_REQUEST_VALIDATE_ROLES)
    authorize_cabinets = _allowed_cabinet_ids(request, FINAL_AUTHORIZATION_ROLES)
    material_request_cabinets = validate_cabinets | authorize_cabinets
    if material_request_cabinets:
        pending_statuses = []
        if validate_cabinets:
            pending_statuses.append(MaterialRequestStatus.PENDING)
        if authorize_cabinets:
            pending_statuses.append(MaterialRequestStatus.VALIDATED)
        for mat_request in MaterialRequest.objects.filter(
            status__in=pending_statuses, site__cabinet_id__in=material_request_cabinets,
        ).select_related('site', 'requested_by').order_by('created_at'):
            cabinet_id = mat_request.site.cabinet_id
            if mat_request.status == MaterialRequestStatus.PENDING and cabinet_id not in validate_cabinets:
                continue
            if mat_request.status == MaterialRequestStatus.VALIDATED and cabinet_id not in authorize_cabinets:
                continue
            items.append({
                'type': 'material_request', 'type_label': _('Demande de matériaux'), 'icon': 'fa-boxes', 'badge': 'info',
                'title': f"REQ-{mat_request.pk} — {mat_request.total_items} article(s)",
                'subtitle': mat_request.get_status_display(),
                'site_name': mat_request.site.name,
                'requested_by_name': _display_name(mat_request.requested_by),
                'created_at': mat_request.created_at,
                'review_url': reverse('materials:request_detail', kwargs={'pk': mat_request.pk}),
            })

    avenant_cabinets = _allowed_cabinet_ids(request, FINAL_AUTHORIZATION_ROLES)
    if avenant_cabinets:
        for avenant in Avenant.objects.filter(
            status=AvenantStatus.PENDING, site__cabinet_id__in=avenant_cabinets,
        ).select_related('site', 'requested_by').order_by('created_at'):
            items.append({
                'type': 'avenant', 'type_label': _('Avenant'), 'icon': 'fa-file-signature', 'badge': 'warning',
                'title': f"+{avenant.amount}",
                'subtitle': avenant.justification,
                'site_name': avenant.site.name,
                'requested_by_name': _display_name(avenant.requested_by),
                'created_at': avenant.created_at,
                'review_url': reverse('finance:avenant_list'),
            })

    planning_cabinets = _allowed_cabinet_ids(request, PLANNING_REVIEW_ROLES)
    if planning_cabinets:
        for submission in PlanningSubmission.objects.filter(
            status=PlanningStatus.SOUMISE, site__cabinet_id__in=planning_cabinets,
        ).exclude(submitted_by=request.user).select_related('site', 'submitted_by').order_by('created_at'):
            items.append({
                'type': 'planning', 'type_label': _('Planification'), 'icon': 'fa-clipboard-list', 'badge': 'primary',
                'title': submission.description[:80],
                'subtitle': '',
                'site_name': submission.site.name,
                'requested_by_name': _display_name(submission.submitted_by),
                'created_at': submission.created_at,
                'review_url': reverse('projects:site_detail', kwargs={'unique_id': submission.site.unique_id}),
            })

    leave_cabinets = _allowed_cabinet_ids(request, LEAVE_DECIDE_ROLES)
    if leave_cabinets:
        for leave in Leave.objects.filter(
            status=ApprovalStatus.PENDING, personnel__cabinet_id__in=leave_cabinets,
        ).select_related('personnel').order_by('created_at'):
            items.append({
                'type': 'leave', 'type_label': _('Congé'), 'icon': 'fa-umbrella-beach', 'badge': 'secondary',
                'title': f"{leave.personnel.get_full_name()} — {leave.get_leave_type_display()}",
                'subtitle': f"{leave.start_date} → {leave.end_date}",
                'site_name': '',
                'requested_by_name': '',
                'created_at': leave.created_at,
                'review_url': reverse('personnel:leave_list'),
            })

    items.sort(key=lambda item: item['created_at'])
    return items
