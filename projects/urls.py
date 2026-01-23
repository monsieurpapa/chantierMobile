from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    # Sites
    path('sites/', views.SiteListView.as_view(), name='site_list'),
    path('sites/add/', views.SiteCreateView.as_view(), name='site_create'),
    path('sites/<uuid:unique_id>/', views.SiteDetailView.as_view(), name='site_detail'),
    path('sites/<uuid:unique_id>/edit/', views.SiteUpdateView.as_view(), name='site_update'),
    path('sites/<uuid:unique_id>/delete/', views.SiteDeleteView.as_view(), name='site_delete'),
    
    # Phases
    path('sites/<uuid:site_id>/phases/add/', views.ProjectPhaseCreateView.as_view(), name='phase_create'),
    path('phases/<uuid:unique_id>/edit/', views.ProjectPhaseUpdateView.as_view(), name='phase_update'),
    path('phases/<uuid:unique_id>/delete/', views.ProjectPhaseDeleteView.as_view(), name='phase_delete'),
    
    # Progress
    path('phases/<uuid:phase_id>/progress/add/', views.SiteProgressCreateView.as_view(), name='progress_create'),
]
