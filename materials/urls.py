from django.urls import path
from . import views

app_name = 'materials'

urlpatterns = [
    # Catalog
    path('catalog/', views.MaterialListView.as_view(), name='material_list'),
    path('catalog/add/', views.MaterialCreateView.as_view(), name='material_create'),
    path('catalog/<int:pk>/edit/', views.MaterialUpdateView.as_view(), name='material_update'),
    path('catalog/quick-create/', views.MaterialQuickCreateView.as_view(), name='material_quick_create'),

    # Requests
    path('requests/', views.MaterialRequestListView.as_view(), name='request_list'),
    path('requests/add/', views.MaterialRequestCreateView.as_view(), name='request_create'),
    path('requests/<int:pk>/', views.MaterialRequestDetailView.as_view(), name='request_detail'),
    path('requests/<int:pk>/edit/', views.MaterialRequestUpdateView.as_view(), name='request_update'),
    path('requests/<int:pk>/validate/', views.request_validate, name='request_validate'),
    path('requests/<int:pk>/approve/', views.approve_material_request, name='request_approve'),
    
    # API
    path('api/materials-data/', views.materials_data_api, name='materials_data'),
]
