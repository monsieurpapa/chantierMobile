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
    path('api/site-phases/', views.site_phases_data, name='site_phases_data'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/add/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<int:pk>/', views.BudgetDetailView.as_view(), name='budget_detail'),
    path('budgets/<int:pk>/edit/', views.BudgetUpdateView.as_view(), name='budget_update'),

    # Caisses (livre de caisse, prêts, virements)
    path('caisses/', views.CaisseListView.as_view(), name='caisse_list'),
    path('caisses/add/', views.CaisseCreateView.as_view(), name='caisse_create'),
    path('caisses/<int:pk>/', views.CaisseDetailView.as_view(), name='caisse_detail'),
    path('caisses/<int:pk>/edit/', views.CaisseUpdateView.as_view(), name='caisse_update'),
    path('caisses/<int:pk>/transactions/add/', views.CaisseTransactionCreateView.as_view(), name='caisse_transaction_create'),
    path('caisses/transactions/<int:pk>/delete/', views.CaisseTransactionDeleteView.as_view(), name='caisse_transaction_delete'),
    path('caisses/<int:pk>/transfer/', views.caisse_transfer, name='caisse_transfer'),
    path('caisses/report/', views.CaisseReportView.as_view(), name='caisse_report'),
    path('caisses/report/pdf/', views.caisse_report_pdf, name='caisse_report_pdf'),

    # Prêts entre caisses
    path('caisse-loans/', views.CaisseLoanListView.as_view(), name='caisse_loan_list'),
    path('caisse-loans/add/', views.CaisseLoanCreateView.as_view(), name='caisse_loan_create'),
    path('caisse-loans/<int:pk>/repay/', views.caisse_loan_repay, name='caisse_loan_repay'),

    # Listes de paie — "Main d'œuvre" tab (Ouvriers, chantier-scoped)
    path('payroll/', views.PayrollListListView.as_view(), name='payroll_list'),
    path('payroll/add/', views.PayrollListCreateView.as_view(), name='payroll_create'),
    path('payroll/<int:pk>/', views.PayrollListDetailView.as_view(), name='payroll_detail'),
    path('payroll/<int:pk>/items/add/', views.PayrollListItemCreateView.as_view(), name='payroll_item_create'),
    path('payroll/<int:pk>/allocate/', views.PayrollListAllocateView.as_view(), name='payroll_allocate'),
    path('payroll/<int:pk>/submit/', views.payroll_submit, name='payroll_submit'),
    path('payroll/<int:pk>/disburse/', views.payroll_disburse, name='payroll_disburse'),

    # Paie du personnel — "Ingénieurs & Staff" tab (salaire mensuel, hors chantier)
    path('payroll/salaries/', views.SalaryPaymentListView.as_view(), name='salary_payment_list'),
    path('payroll/salaries/add/', views.SalaryPaymentCreateView.as_view(), name='salary_payment_create'),

    # Avenants
    path('avenants/', views.AvenantListView.as_view(), name='avenant_list'),
    path('avenants/add/', views.AvenantCreateView.as_view(), name='avenant_create'),
    path('avenants/<int:pk>/approve/', views.avenant_approve, name='avenant_approve'),
    path('avenants/<int:pk>/reject/', views.avenant_reject, name='avenant_reject'),
]
