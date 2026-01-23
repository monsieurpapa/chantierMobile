from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from projects.models import Site
from finance.models import Expense

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Summary stats for dashboard
        context['recent_sites'] = Site.objects.order_by('-updated_at')[:5]
        context['pending_expenses'] = Expense.objects.filter(status='PENDING').count()
        context['recent_expenses'] = Expense.objects.order_by('-created_at')[:5]
        return context
