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

    # API
    path('api/price-items-data/', views.price_items_data_api, name='price_items_data'),
]
