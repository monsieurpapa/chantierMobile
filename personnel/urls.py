from django.urls import path
from . import views

app_name = 'personnel'

urlpatterns = [
    path('staff/', views.PersonnelListView.as_view(), name='personnel_list'),
    path('staff/add/', views.PersonnelCreateView.as_view(), name='personnel_create'),
    path('staff/<uuid:unique_id>/', views.PersonnelDetailView.as_view(), name='personnel_detail'),
    path('staff/<uuid:unique_id>/edit/', views.PersonnelUpdateView.as_view(), name='personnel_update'),
    path('staff/<uuid:unique_id>/delete/', views.PersonnelDeleteView.as_view(), name='personnel_delete'),
    
    # Skills
    path('skills/', views.SkillListView.as_view(), name='skill_list'),
    
    # Assignments
    path('assignments/add/', views.SiteAssignmentCreateView.as_view(), name='assignment_create'),
]
