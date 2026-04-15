from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Cabinet, UserCabinetRole, CabinetContextLog

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')

@admin.register(Cabinet)
class CabinetAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'created_at')

@admin.register(UserCabinetRole)
class UserCabinetRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'cabinet', 'role')
    list_filter = ('cabinet', 'role')

@admin.register(CabinetContextLog)
class CabinetContextLogAdmin(admin.ModelAdmin):
    list_display = ('switched_by', 'action', 'cabinet', 'created_at')
    list_filter = ('action', 'cabinet')
    readonly_fields = ('switched_by', 'cabinet', 'action', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
