"""
Superadmin "Journal d'audit": browse, filter and export the history of
actions recorded by core/audit.py (core.AuditLogEntry).

Superuser-only, platform-wide: it deliberately ignores the cabinet a
superadmin may have switched their session into, since the journal is
the place to look *across* cabinets (a cabinet can still be picked in
the filters).
"""
import csv
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from accounts.models import Cabinet
from chantiermobile.constants import AuditAction
from core.audit import TRACKED_APPS
from core.mixins import PageHeaderMixin
from core.models import AuditLogEntry

User = get_user_model()

EXPORT_MAX_ROWS = 100_000


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, _("Vous n'avez pas la permission d'accéder à cette page."))
        return redirect('home')


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def filter_entries(params, qs=None):
    """Apply the journal's GET filters. Shared by the list and the CSV
    export so an export is exactly what the screen shows."""
    if qs is None:
        qs = AuditLogEntry.objects.all()
    qs = qs.select_related('actor', 'content_type', 'cabinet')

    q = (params.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(actor_label__icontains=q) | Q(object_repr__icontains=q) |
            Q(object_id=q) | Q(ip_address__startswith=q) | Q(request_path__icontains=q)
        )
    if params.get('actor', '').isdigit():
        qs = qs.filter(actor_id=int(params['actor']))
    if params.get('action') in AuditAction.values:
        qs = qs.filter(action=params['action'])
    if params.get('model', '').isdigit():
        qs = qs.filter(content_type_id=int(params['model']))
    if params.get('cabinet', '').isdigit():
        qs = qs.filter(cabinet_id=int(params['cabinet']))
    if params.get('object_id'):
        qs = qs.filter(object_id=params['object_id'])

    date_from, date_to = _parse_date(params.get('date_from')), _parse_date(params.get('date_to'))
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)
    return qs.order_by('-timestamp', '-id')


def _model_choices():
    """Content types the journal can hold, labelled by verbose name."""
    choices = []
    for ct in ContentType.objects.filter(app_label__in=TRACKED_APPS):
        model = ct.model_class()
        if model is None:
            continue
        choices.append((ct.pk, str(model._meta.verbose_name).capitalize()))
    return sorted(choices, key=lambda c: c[1].lower())


def object_url(entry):
    """Link to the journaled record's own page when it still exists and the
    model exposes one; None otherwise."""
    if entry.content_type_id is None or not entry.object_id:
        return None
    model = entry.content_type.model_class()
    if model is None:
        return None
    if model is User:
        try:
            return reverse('accounts:admin_user_detail', kwargs={'pk': entry.object_id})
        except NoReverseMatch:
            return None
    if model is Cabinet:
        return reverse('accounts:admin_cabinet_detail', kwargs={'pk': entry.object_id})
    if not hasattr(model, 'get_absolute_url'):
        return None
    obj = model._default_manager.filter(pk=entry.object_id).first()
    if obj is None:
        return None
    try:
        return obj.get_absolute_url()
    except Exception:
        return None


class AuditLogListView(LoginRequiredMixin, SuperuserRequiredMixin, PageHeaderMixin, ListView):
    template_name = 'core/audit_log_list.html'
    context_object_name = 'entries'
    paginate_by = 50
    header_title = _("Journal d'audit")
    header_subtitle = _("Historique daté des actions effectuées dans le système : qui, quoi, quand, d'où")

    def get_breadcrumb_items(self):
        return [
            {'title': _("Administration"), 'url': None},
            {'title': _("Journal d'audit"), 'url': None},
        ]

    def get_header_actions(self):
        query = self.request.GET.copy()
        query.pop('page', None)
        url = reverse('audit_log_export')
        if query:
            url += '?' + query.urlencode()
        return [{
            'label': _("Exporter (CSV)"),
            'url': url,
            'icon': 'file-csv',
            'class': 'btn-falcon-default',
        }]

    def get_queryset(self):
        return filter_entries(self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET
        now = timezone.now()
        today = timezone.localdate()
        all_entries = AuditLogEntry.objects.all()
        context.update({
            'filters': {
                'q': params.get('q', ''),
                'actor': params.get('actor', ''),
                'action': params.get('action', ''),
                'model': params.get('model', ''),
                'cabinet': params.get('cabinet', ''),
                'date_from': params.get('date_from', ''),
                'date_to': params.get('date_to', ''),
                'object_id': params.get('object_id', ''),
            },
            'has_filters': any(params.get(k) for k in (
                'q', 'actor', 'action', 'model', 'cabinet', 'date_from', 'date_to', 'object_id')),
            'action_choices': AuditAction.choices,
            'model_choices': _model_choices(),
            'cabinets': Cabinet.objects.order_by('name'),
            'actors': User.objects.order_by('username'),
            'stats': {
                'today': all_entries.filter(timestamp__date=today).count(),
                'week': all_entries.filter(timestamp__gte=now - timedelta(days=7)).count(),
                'active_users_today': all_entries.filter(
                    timestamp__date=today, actor__isnull=False,
                ).values('actor').distinct().count(),
                'failed_logins_24h': all_entries.filter(
                    action=AuditAction.LOGIN_FAILED, timestamp__gte=now - timedelta(hours=24),
                ).count(),
            },
            'failed_logins_url': reverse('audit_log_list') + '?action=' + AuditAction.LOGIN_FAILED,
            'today_iso': today.isoformat(),
        })
        # Object history mode (?model=…&object_id=…): name the record.
        if context['filters']['model'] and context['filters']['object_id']:
            first = self.object_list.first()
            context['object_history_label'] = first.object_repr if first else context['filters']['object_id']
        return context


class AuditLogDetailView(LoginRequiredMixin, SuperuserRequiredMixin, PageHeaderMixin, DetailView):
    model = AuditLogEntry
    template_name = 'core/audit_log_detail.html'
    context_object_name = 'entry'
    back_url = reverse_lazy('audit_log_list')

    def get_queryset(self):
        return AuditLogEntry.objects.select_related('actor', 'content_type', 'cabinet')

    def get_header_title(self):
        return _("Entrée n° %(pk)s du journal") % {'pk': self.object.pk}

    def get_header_subtitle(self):
        return f"{self.object.get_action_display()} — {self.object.object_repr or ''}".strip(' —')

    def get_breadcrumb_items(self):
        return [
            {'title': _("Administration"), 'url': None},
            {'title': _("Journal d'audit"), 'url': str(reverse_lazy('audit_log_list'))},
            {'title': f"#{self.object.pk}", 'url': None},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entry = self.object
        context['change_rows'] = list(entry.changes.values()) if isinstance(entry.changes, dict) else []
        context['object_url'] = object_url(entry)
        if entry.content_type_id and entry.object_id:
            context['object_history_url'] = (
                reverse('audit_log_list') + f'?model={entry.content_type_id}&object_id={entry.object_id}'
            )
            context['object_history'] = (
                AuditLogEntry.objects
                .filter(content_type_id=entry.content_type_id, object_id=entry.object_id)
                .exclude(pk=entry.pk)
                .select_related('actor')
                .order_by('-timestamp', '-id')[:15]
            )
        if entry.actor_id:
            context['actor_history_url'] = reverse('audit_log_list') + f'?actor={entry.actor_id}'
        return context


class _Echo:
    def write(self, value):
        return value


def _changes_text(changes):
    if not isinstance(changes, dict):
        return ''
    parts = []
    for row in changes.values():
        old, new = row.get('old'), row.get('new')
        if old is None:
            parts.append(f"{row.get('label')}: {new}")
        else:
            parts.append(f"{row.get('label')}: {old} → {new if new is not None else '∅'}")
    return ' | '.join(parts)


class AuditLogExportView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """CSV of the currently filtered journal (semicolon-separated, UTF-8
    with BOM so French Excel opens it with accents intact)."""

    def get(self, request):
        entries = filter_entries(request.GET)[:EXPORT_MAX_ROWS]
        writer = csv.writer(_Echo(), delimiter=';')

        def rows():
            yield '﻿'
            yield writer.writerow([
                'Date', 'Utilisateur', 'Action', 'Type', 'Objet', 'ID objet',
                'Cabinet', 'Modifications', 'Adresse IP', 'Méthode', 'URL',
            ])
            for e in entries.iterator(chunk_size=2000):
                yield writer.writerow([
                    timezone.localtime(e.timestamp).strftime('%d/%m/%Y %H:%M:%S'),
                    e.actor_label,
                    e.get_action_display(),
                    e.model_label,
                    e.object_repr,
                    e.object_id,
                    e.cabinet.name if e.cabinet_id else '',
                    _changes_text(e.changes),
                    e.ip_address or '',
                    e.request_method,
                    e.request_path,
                ])

        stamp = timezone.localtime().strftime('%Y%m%d-%H%M')
        response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="journal-audit-{stamp}.csv"'
        return response
