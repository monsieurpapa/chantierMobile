from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from core.dashboard import build_dashboard_context
from core.approvals import get_pending_approvals

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
