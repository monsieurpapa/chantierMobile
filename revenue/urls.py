from django.urls import path
from . import views

app_name = 'revenue'

urlpatterns = [
    # Contracts
    path('contracts/', views.ContractListView.as_view(), name='contract_list'),
    path('site/<uuid:site_id>/contract/add/', views.ContractCreateView.as_view(), name='contract_create'),
    path('contract/<int:pk>/edit/', views.ContractUpdateView.as_view(), name='contract_update'),
    
    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('contract/<int:contract_id>/invoice/add/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoice/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    
    # Payments
    path('invoice/<int:invoice_id>/payment/add/', views.PaymentCreateView.as_view(), name='payment_create'),
]
