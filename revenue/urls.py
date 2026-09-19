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

    # Devis
    path('devis/', views.DevisListView.as_view(), name='devis_list'),
    path('devis/add/', views.DevisCreateView.as_view(), name='devis_create'),
    path('site/<uuid:site_id>/devis/add/', views.DevisCreateView.as_view(), name='devis_create_from_site'),
    path('devis/<int:pk>/', views.DevisDetailView.as_view(), name='devis_detail'),
    path('devis/<int:pk>/edit/', views.DevisUpdateView.as_view(), name='devis_update'),
    path('devis/<int:pk>/envoyer/', views.devis_send, name='devis_send'),
    path('devis/<int:pk>/accepter/', views.devis_accept, name='devis_accept'),
    path('devis/<int:pk>/refuser/', views.devis_reject, name='devis_reject'),

    # Situations de travaux
    path('situations/', views.SituationTravauxListView.as_view(), name='situation_list'),
    path('situations/add/', views.SituationTravauxCreateView.as_view(), name='situation_create'),
    path('contract/<int:contract_id>/situation/add/', views.SituationTravauxCreateView.as_view(), name='situation_create_from_contract'),
    path('situations/<int:pk>/', views.SituationTravauxDetailView.as_view(), name='situation_detail'),
    path('situations/<int:pk>/valider/', views.situation_validate, name='situation_validate'),
    path('situations/<int:pk>/facturer/', views.situation_generate_invoice, name='situation_generate_invoice'),
]
