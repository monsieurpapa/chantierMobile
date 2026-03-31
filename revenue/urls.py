from django.urls import path
from . import views

app_name = 'revenue'

urlpatterns = [
    # Contracts
    path('contracts/', views.ContractListView.as_view(), name='contract_list'),
    path('contract/add/', views.ContractCreateView.as_view(), name='contract_create'),
    path('site/<uuid:site_id>/contract/add/', views.ContractCreateView.as_view(), name='contract_create_from_site'),
    path('contract/<int:pk>/edit/', views.ContractUpdateView.as_view(), name='contract_update'),
    
    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoice/add/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('contract/<int:contract_id>/invoice/add/', views.InvoiceCreateView.as_view(), name='invoice_create_from_contract'),
    path('invoice/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    
    # Payments
    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('invoice/<int:invoice_id>/payment/add/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('payment/add/', views.PaymentCreateView.as_view(), name='payment_create_standalone'),
]
