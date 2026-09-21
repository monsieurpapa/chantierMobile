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

    # Dossier (documents)
    path('staff/<uuid:unique_id>/documents/add/', views.PersonnelDocumentCreateView.as_view(), name='document_create'),
    path('documents/<int:pk>/delete/', views.PersonnelDocumentDeleteView.as_view(), name='document_delete'),

    # Congés
    path('leaves/', views.LeaveListView.as_view(), name='leave_list'),
    path('leaves/add/', views.LeaveCreateView.as_view(), name='leave_create'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('leaves/<int:pk>/reject/', views.leave_reject, name='leave_reject'),

    # Jours fériés
    path('holidays/', views.HolidayListView.as_view(), name='holiday_list'),
    path('holidays/add/', views.HolidayCreateView.as_view(), name='holiday_create'),
    path('holidays/<int:pk>/delete/', views.HolidayDeleteView.as_view(), name='holiday_delete'),
]
