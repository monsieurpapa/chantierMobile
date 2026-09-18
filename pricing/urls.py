from django.urls import path
from . import views

app_name = 'pricing'

urlpatterns = [
    path('', views.PriceLibraryItemListView.as_view(), name='price_item_list'),
    path('add/', views.PriceLibraryItemCreateView.as_view(), name='price_item_create'),
    path('<int:pk>/', views.PriceLibraryItemDetailView.as_view(), name='price_item_detail'),
    path('<int:pk>/edit/', views.PriceLibraryItemUpdateView.as_view(), name='price_item_update'),
]
