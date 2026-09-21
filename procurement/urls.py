from django.urls import path
from . import views

app_name = 'procurement'

urlpatterns = [
    # Suppliers
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_update'),

    # Purchase orders
    path('orders/', views.PurchaseOrderListView.as_view(), name='purchase_order_list'),
    path('orders/add/', views.PurchaseOrderCreateView.as_view(), name='purchase_order_create'),
    path('site/<uuid:site_id>/orders/add/', views.PurchaseOrderCreateView.as_view(), name='purchase_order_create_from_site'),
    path('orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase_order_detail'),
    path('orders/<int:pk>/edit/', views.PurchaseOrderUpdateView.as_view(), name='purchase_order_update'),
    path('orders/<int:pk>/envoyer/', views.purchase_order_send, name='purchase_order_send'),
    path('orders/<int:pk>/receptionner/', views.purchase_order_receive, name='purchase_order_receive'),
    path('orders/<int:pk>/annuler/', views.purchase_order_cancel, name='purchase_order_cancel'),
    path('orders/rapport/', views.AchatsReportView.as_view(), name='achats_report'),
    path('orders/rapport/pdf/', views.achats_report_pdf, name='achats_report_pdf'),
    path('orders/<int:pk>/transfer-proof/', views.purchase_order_submit_transfer_proof, name='purchase_order_submit_transfer_proof'),
    path('orders/<int:pk>/transfer-validate/', views.purchase_order_validate_transfer, name='purchase_order_validate_transfer'),

    # Crédits fournisseurs
    path('credits/', views.SupplierCreditListView.as_view(), name='supplier_credit_list'),
    path('credits/add/', views.SupplierCreditCreateView.as_view(), name='supplier_credit_create'),
    path('credits/<int:pk>/repay/', views.supplier_credit_repay, name='supplier_credit_repay'),

    # Stock
    path('stock/', views.StockItemListView.as_view(), name='stock_item_list'),
    path('stock/add/', views.StockItemCreateView.as_view(), name='stock_item_create'),
    path('stock/<int:pk>/', views.StockItemDetailView.as_view(), name='stock_item_detail'),
    path('stock/<int:pk>/edit/', views.StockItemUpdateView.as_view(), name='stock_item_update'),
    path('stock/<int:pk>/mouvement/', views.stock_movement_create, name='stock_movement_create'),
]
