from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Superadmin: Cabinet context switcher
    path('switch-cabinet/', views.SwitchCabinetView.as_view(), name='switch_cabinet'),

    # User Profile
    path('profile/update/', views.UserProfileUpdateView.as_view(), name='profile_update'),
    
    # SUPERADMIN: User Management
    path('admin/users/', views.UserListAdminView.as_view(), name='admin_users_list'),
    path('admin/users/create/', views.UserCreateAdminView.as_view(), name='admin_user_create'),
    path('admin/users/<int:pk>/edit/', views.UserEditAdminView.as_view(), name='admin_user_edit'),
    path('admin/users/<int:pk>/delete/', views.UserDeleteAdminView.as_view(), name='admin_user_delete'),
    path('admin/users/<int:pk>/reset-password/', views.UserResetPasswordAdminView.as_view(), name='admin_user_reset_password'),
    path('admin/users/<int:pk>/toggle-active/', views.UserToggleActiveAdminView.as_view(), name='admin_user_toggle_active'),
    path('admin/users/<int:pk>/', views.UserDetailAdminView.as_view(), name='admin_user_detail'),
    path('admin/users/<int:user_id>/assign-cabinet/', views.AssignUserToCabinetView.as_view(), name='assign_user_to_cabinet'),

    # SUPERADMIN: Role Assignments (system-wide)
    path('admin/roles/', views.RoleAssignmentListAdminView.as_view(), name='admin_role_assignments_list'),

    # SUPERADMIN: Cabinet Management
    path('admin/cabinets/', views.CabinetListAdminView.as_view(), name='admin_cabinets_list'),
    path('admin/cabinets/create/', views.CabinetCreateView.as_view(), name='admin_cabinet_create'),
    path('admin/cabinets/<int:pk>/', views.CabinetDetailAdminView.as_view(), name='admin_cabinet_detail'),
    path('admin/cabinets/<int:pk>/edit/', views.CabinetUpdateView.as_view(), name='admin_cabinet_edit'),
    path('admin/cabinets/<int:pk>/delete/', views.CabinetDeleteView.as_view(), name='admin_cabinet_delete'),
    path('admin/cabinets/<int:cabinet_id>/assign-user/', views.AssignUserToCabinetFromDetailView.as_view(), name='admin_assign_user_to_cabinet'),
    path('admin/cabinets/user-role/<int:pk>/edit/', views.CabinetUserRoleUpdateView.as_view(), name='admin_cabinet_user_role_edit'),
    path('admin/cabinets/user-role/<int:pk>/delete/', views.CabinetUserRoleDeleteView.as_view(), name='admin_cabinet_user_role_delete'),
    path('admin/cabinets/user-role/<int:pk>/status/', views.CabinetUserRoleQuickStatusView.as_view(), name='admin_cabinet_user_role_status'),
]
