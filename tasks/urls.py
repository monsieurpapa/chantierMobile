from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.TaskListView.as_view(), name='task_list'),
    path('add/', views.TaskCreateView.as_view(), name='task_create'),
    path('site/<uuid:site_id>/add/', views.TaskCreateView.as_view(), name='task_create_from_site'),
    path('<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_update'),
    path('<int:pk>/demarrer/', views.task_start, name='task_start'),
    path('<int:pk>/terminer/', views.task_complete, name='task_complete'),
    path('<int:pk>/bloquer/', views.task_block, name='task_block'),
    path('<int:pk>/reouvrir/', views.task_reopen, name='task_reopen'),
]
