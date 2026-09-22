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
    path('phases/<uuid:unique_id>/close/', views.phase_close, name='phase_close'),

    # Progress
    path('phases/<uuid:phase_id>/progress/add/', views.SiteProgressCreateView.as_view(), name='progress_create'),
    path('progress/<uuid:unique_id>/', views.ProgressDetailView.as_view(), name='progress_detail'),
    path('progress/<uuid:unique_id>/photos/add/', views.progress_photo_add, name='progress_photo_add'),
    path('progress/<uuid:unique_id>/comments/add/', views.progress_comment_add, name='progress_comment_add'),

    # Planning submissions
    path('sites/<uuid:site_id>/planning/add/', views.PlanningSubmissionCreateView.as_view(), name='planning_submission_create'),
    path('planning/<int:pk>/approve/', views.planning_submission_approve, name='planning_submission_approve'),
    path('planning/<int:pk>/reject/', views.planning_submission_reject, name='planning_submission_reject'),
]
