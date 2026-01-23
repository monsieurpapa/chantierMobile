from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect
from .models import Expense, ExpenseApproval

class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    context_object_name = 'expenses'
    template_name = 'finance/expense_list.html'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('site', 'category', 'requester')
        if not self.request.user.is_staff:
             # Get cabinets where user has a role
            user_cabinet_ids = self.request.user.cabinet_roles.values_list('cabinet_id', flat=True)
            qs = qs.filter(site__cabinet__id__in=user_cabinet_ids)
        return qs.order_by('-created_at')

class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    fields = ['site', 'category', 'amount', 'description', 'receipt_image']
    template_name = 'finance/expense_form.html'
    success_url = reverse_lazy('expense_list')

    def form_valid(self, form):
        form.instance.requester = self.request.user
        return super().form_valid(form)

class ExpenseDetailView(LoginRequiredMixin, DetailView):
    model = Expense
    context_object_name = 'expense'
    template_name = 'finance/expense_detail.html'

def approve_expense(request, pk):
    if request.method == 'POST':
        expense = Expense.objects.get(pk=pk)
        if request.user.is_staff or request.user.cabinet_roles.filter(cabinet=expense.site.cabinet, role__in=['DIRECTOR', 'CHIEF_ENGINEER']).exists():
            expense.approve(request.user, comments=request.POST.get('comments', ''))
        else:
            # Simple fallback for unauthorized access
            pass
        return redirect('expense_detail', pk=pk)
    return redirect('expense_list')
