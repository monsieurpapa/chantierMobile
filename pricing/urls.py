"""URL routes for the price library (Bibliothèque de Prix) and DQE."""
from django.urls import path
from . import views

app_name = 'pricing'

urlpatterns = [
    path('', views.PriceLibraryItemListView.as_view(), name='price_item_list'),
    path('add/', views.PriceLibraryItemCreateView.as_view(), name='price_item_create'),
    path('<int:pk>/', views.PriceLibraryItemDetailView.as_view(), name='price_item_detail'),
    path('<int:pk>/edit/', views.PriceLibraryItemUpdateView.as_view(), name='price_item_update'),

    # DQE (Détail Quantitatif Estimatif)
    path('dqe/', views.DQEListView.as_view(), name='dqe_list'),
    path('dqe/add/', views.DQECreateView.as_view(), name='dqe_create'),
    path('dqe/<int:pk>/', views.DQEDetailView.as_view(), name='dqe_detail'),
    path('dqe/<int:pk>/edit/', views.DQEUpdateView.as_view(), name='dqe_update'),

    # Ratios de consommation matière (explosion d'ouvrages composites)
    path('ratios/', views.MaterialConsumptionRatioListView.as_view(), name='ratio_list'),
    path('ratios/add/', views.MaterialConsumptionRatioCreateView.as_view(), name='ratio_create'),
    path('ratios/<int:pk>/edit/', views.MaterialConsumptionRatioUpdateView.as_view(), name='ratio_update'),

    # Seuils de dépassement matière (cabinet)
    path('settings/seuils/', views.CabinetMaterialThresholdSettingsView.as_view(), name='material_thresholds'),

    # Rapport de conformité devis / état de besoin
    path('conformite/<int:pk>/', views.DevisComplianceReportView.as_view(), name='devis_compliance_report'),

    # API
    path('api/price-items-data/', views.price_items_data_api, name='price_items_data'),
    path('api/material-usage-comparison/', views.material_usage_comparison_api, name='material_usage_comparison'),
    path('api/site-dqes-data/', views.site_dqes_data_api, name='site_dqes_data'),
]
