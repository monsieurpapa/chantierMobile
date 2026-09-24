from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from core.dashboard import build_dashboard_context
from core.approvals import get_pending_approvals
from core.search import global_search

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request))
        return context


class PendingApprovalsView(LoginRequiredMixin, TemplateView):
    """"Approbations en attente" — a single inbox combining every pending
    Expense, MaterialRequest, Avenant, PlanningSubmission and Leave the
    current user can act on, instead of checking five separate list pages
    by hand (item 12 of the Directors/Engineers audit)."""
    template_name = 'core/pending_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['approvals'] = get_pending_approvals(self.request)
        context['header_title'] = _("Approbations en attente")
        context['header_subtitle'] = _("Tout ce qui attend votre décision, en un seul endroit")
        return context


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    """Item 15 (second half) of the Directors/Engineers audit: the
    navbar's search box was a Falcon theme placeholder with no data
    source behind it. This gives it one, searching cabinet-scoped Sites,
    Personnel, Contracts and Invoices by name/number (see core/search.py
    for why these four and not more)."""
    template_name = 'core/global_search.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '')
        context['query'] = query
        context['results'] = global_search(self.request, query)
        context['header_title'] = _("Recherche")
        context['header_subtitle'] = _("Chantiers, personnel, contrats et factures")
        return context


class NotificationListView(LoginRequiredMixin, TemplateView):
    """Item 13 of the Directors/Engineers audit: nothing surfaced inside
    the app when something needed your decision or when your own request
    was decided — only email (one trigger, revenue/notifications.py) or
    noticing it yourself. This lists every Notification.objects row for
    the current user, newest first, mirroring the pending-approvals
    inbox's full-page pattern (item 12) rather than a JS dropdown."""
    template_name = 'core/notifications_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['notifications'] = self.request.user.notifications.all()[:50]
        context['header_title'] = _("Notifications")
        context['header_subtitle'] = _("Ce qui a changé depuis votre dernière visite")
        return context


@login_required
def notification_open(request, pk):
    """Marks one notification read and follows its link — the normal way
    to click through from the list."""
    notification = get_object_or_404(request.user.notifications, pk=pk)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return redirect(notification.url or reverse_lazy('notifications_list'))


@login_required
def notifications_mark_all_read(request):
    if request.method == 'POST':
        request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect('notifications_list')
