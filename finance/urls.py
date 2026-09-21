from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('expenses/', views.ExpenseListView.as_view(), name='expense_list'),
    path('expenses/add/', views.ExpenseCreateView.as_view(), name='expense_create'),
    path('expenses/<int:pk>/', views.ExpenseDetailView.as_view(), name='expense_detail'),
    path('expenses/<int:pk>/approve/', views.approve_expense, name='expense_approve'),
    path('expenses/<int:pk>/reject/', views.reject_expense, name='expense_reject'),
    path('expenses/<int:pk>/pay/', views.mark_expense_paid, name='expense_pay'),
    path('expenses/report/', views.ExpenseReportView.as_view(), name='expense_report'),
    path('expenses/report/pdf/', views.expense_report_pdf, name='expense_report_pdf'),
    path('api/site-personnel/', views.site_personnel_data, name='site_personnel_data'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/add/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/', views.BudgetDetailView.as_view(), name='budget_detail'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),
]
