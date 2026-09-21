from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.dashboard import build_dashboard_context

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_dashboard_context(self.request))
        return context
